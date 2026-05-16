"""
watch_and_alert.py — Monitors ShopApp locally and auto-alerts IncidentIQ.

Watches THREE things simultaneously:
  1. GET /metrics  — OTEL telemetry from live traffic
  2. telemetry_metrics.jsonl — raw log file written by ShopApp directly
  3. backend source files — detects if buggy code patterns are present

When anomalies are detected it:
  - Generates test traffic to confirm the error rate
  - Sends the incident + buggy code to IncidentIQ
  - Prints the full RCA + generated fix

Run:
    python scripts/watch_and_alert.py
    python scripts/watch_and_alert.py --auto-fix
"""
import sys
import os
import json
import time
import argparse
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from pathlib import Path
from collections import deque
from datetime import datetime, timezone

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

SHOPAPP_URL    = "http://localhost:8001"
INCIDENTIQ_URL = "http://localhost:8000"
BACKEND_DIR    = Path(__file__).parent.parent / "backend"
METRICS_FILE   = BACKEND_DIR / "telemetry_metrics.jsonl"
POLL_INTERVAL  = 5   # seconds
WINDOW         = 30  # recent metric entries to analyse

# Thresholds
THRESHOLDS = {
    "error_rate_pct":  2.0,
    "latency_p95_ms":  800,
    "latency_avg_ms":  400,
}

# Bug patterns to detect directly in source files
BUG_PATTERNS = {
    "connection_leak":  ("conn = engine.connect()", "conn.close()"),   # present, absent
    "sql_injection":    ("f\"SELECT", None),                           # present = bug
    "sql_injection2":   ("f'SELECT", None),
    "no_timeout":       ("engine.connect()", "timeout"),               # present without timeout
}

_alert_fired   = False
_last_alert_at = 0.0
ALERT_COOLDOWN = 60


# ── Source file bug scanner ───────────────────────────────────────────────────

def scan_source_for_bugs() -> list[str]:
    """
    Directly read the backend route files and look for known bug patterns.
    Returns a list of bug descriptions found.
    """
    bugs = []
    for rel in ["routes/sessions.py", "routes/products.py", "routes/orders.py"]:
        path = BACKEND_DIR / rel
        if not path.exists():
            continue
        code = path.read_text(encoding="utf-8", errors="ignore")

        # Connection leak: raw connection acquired but never closed
        if "conn = engine.connect()" in code and "conn.close()" not in code:
            bugs.append(f"[{rel}] Connection leak — engine.connect() never closed on exception path")

        # SQL injection via f-string
        if 'f"SELECT' in code or "f'SELECT" in code or \
           'f"INSERT' in code or "f'INSERT" in code or \
           'f"UPDATE' in code or "f'UPDATE" in code or \
           'f"DELETE' in code or "f'DELETE" in code:
            bugs.append(f"[{rel}] SQL injection risk — f-string interpolation in SQL query")

        # Hardcoded secrets
        import re
        if re.search(r'(password|secret|key)\s*=\s*["\'][^"\']{6,}["\']', code, re.IGNORECASE):
            bugs.append(f"[{rel}] Hardcoded secret detected")

        # Missing finally block for connection cleanup
        if "engine.connect()" in code and "finally:" not in code:
            bugs.append(f"[{rel}] Missing finally block — connection may leak on error")

    return bugs


# ── Traffic generator ─────────────────────────────────────────────────────────

def generate_probe_traffic(n: int = 10) -> dict:
    """
    Hit ShopApp endpoints to generate real telemetry.
    Returns stats about what happened.
    """
    client = httpx.Client(base_url=SHOPAPP_URL, timeout=5)
    errors = 0
    latencies = []

    for _ in range(n):
        for endpoint in ["/products", "/products?category=Electronics", "/sessions/1",
                         "/orders"]:
            try:
                import time as _t
                t0 = _t.perf_counter()
                r = client.get(endpoint)
                ms = (_t.perf_counter() - t0) * 1000
                latencies.append(ms)
                if r.status_code >= 500:
                    errors += 1
            except Exception:
                errors += 1
        time.sleep(0.1)

    client.close()
    total = n * 4
    return {
        "total": total,
        "errors": errors,
        "error_rate_pct": round(errors / total * 100, 2) if total else 0,
        "avg_latency_ms": round(sum(latencies) / len(latencies), 1) if latencies else 0,
        "p95_latency_ms": round(sorted(latencies)[int(len(latencies) * 0.95)], 1) if latencies else 0,
    }


# ── Metrics file reader ───────────────────────────────────────────────────────

def read_metrics_file(n: int = WINDOW) -> list[dict]:
    """Read the last n entries from the OTEL metrics JSONL file."""
    if not METRICS_FILE.exists():
        return []
    try:
        lines = METRICS_FILE.read_text(encoding="utf-8").splitlines()
        entries = []
        for line in lines:
            line = line.strip()
            if line:
                try:
                    entries.append(json.loads(line))
                except Exception:
                    pass
        return entries[-n:]
    except Exception:
        return []


def compute_stats(metrics: list[dict]) -> dict:
    requests = [m for m in metrics if m.get("type") == "request"]
    if not requests:
        return {}
    total     = len(requests)
    errors    = sum(1 for m in requests if m.get("is_error"))
    latencies = [m["latency_ms"] for m in requests if "latency_ms" in m]
    error_rate = errors / total * 100 if total else 0
    avg_lat    = sum(latencies) / len(latencies) if latencies else 0
    sorted_lat = sorted(latencies)
    p95_lat    = sorted_lat[int(len(sorted_lat) * 0.95)] if sorted_lat else 0
    error_paths = {}
    for m in requests:
        if m.get("is_error"):
            p = m.get("path", "unknown")
            error_paths[p] = error_paths.get(p, 0) + 1
    return {
        "total_requests": total,
        "error_count":    errors,
        "error_rate_pct": round(error_rate, 2),
        "avg_latency_ms": round(avg_lat, 2),
        "p95_latency_ms": round(p95_lat, 2),
        "error_paths":    error_paths,
    }


def is_anomalous(stats: dict) -> tuple[bool, list[str]]:
    reasons = []
    if stats.get("error_rate_pct", 0) >= THRESHOLDS["error_rate_pct"]:
        reasons.append(f"Error rate {stats['error_rate_pct']}% >= {THRESHOLDS['error_rate_pct']}%")
    if stats.get("p95_latency_ms", 0) >= THRESHOLDS["latency_p95_ms"]:
        reasons.append(f"p95 latency {stats['p95_latency_ms']}ms >= {THRESHOLDS['latency_p95_ms']}ms")
    return bool(reasons), reasons


# ── IncidentIQ sender ─────────────────────────────────────────────────────────

def send_to_incidentiq(stats: dict, reasons: list[str],
                       source_bugs: list[str], source_files: dict) -> dict:
    log_lines = [
        f"ERROR rate spike: {stats.get('error_rate_pct', 0)}% of requests returning 5xx",
        f"WARN  p95 latency: {stats.get('p95_latency_ms', 0)}ms",
    ]
    for bug in source_bugs:
        log_lines.append(f"ERROR Source scan: {bug}")
    for path, count in stats.get("error_paths", {}).items():
        log_lines.append(f"ERROR {count} errors on endpoint: {path}")

    payload = {
        "service": "shopapp",
        "description": (
            f"ShopApp anomaly detected locally. "
            f"Reasons: {'; '.join(reasons or ['Source code bugs detected'])}. "
            f"Error rate: {stats.get('error_rate_pct', 0)}%, "
            f"p95 latency: {stats.get('p95_latency_ms', 0)}ms."
        ),
        "severity": "p1" if stats.get("error_rate_pct", 0) > 5 or len(source_bugs) > 2 else "p2",
        "telemetry": {
            "error_rate_percent": stats.get("error_rate_pct", 0),
            "latency_p99_ms":     stats.get("p95_latency_ms", 0),
            "latency_p50_ms":     stats.get("avg_latency_ms", 0),
            "total_requests":     stats.get("total_requests", 0),
        },
        "logs": log_lines,
        "deployment_history": [
            {"version": "v1.0.0", "timestamp": "2026-05-15T09:00:00Z",
             "author": "senior-dev", "description": "Initial clean release"},
            {"version": "v1.1.0", "timestamp": datetime.now(timezone.utc).isoformat(),
             "author": "developer", "description": "Add session caching and product search"},
        ],
        "code_context": source_files,
    }

    resp = httpx.post(f"{INCIDENTIQ_URL}/api/incident/investigate",
                      json=payload, timeout=180.0)
    resp.raise_for_status()
    return resp.json()


def read_source_files() -> dict:
    files = {}
    for rel in ["routes/sessions.py", "routes/products.py", "routes/orders.py"]:
        p = BACKEND_DIR / rel
        if p.exists():
            files[f"backend/{rel}"] = p.read_text(encoding="utf-8", errors="ignore")
    return files


def print_result(result: dict):
    sep = "─" * 65
    print(f"\n{sep}")
    print(f"  🤖 IncidentIQ Analysis Complete")
    print(sep)
    print(f"  Incident  : {result.get('incident_id', 'N/A')}")
    print(f"  State     : {result.get('state', '').replace('WorkflowState.', '')}")
    print(f"  Anomalies : {result.get('anomalies_detected', 0)}")
    rca = result.get("rca", {})
    if rca and rca.get("top_hypothesis"):
        conf = rca.get("confidence", 0)
        print(f"\n  Root Cause ({conf*100:.0f}% confidence):")
        print(f"  → {rca['top_hypothesis']}")
        for m in rca.get("mitigations", [])[:3]:
            print(f"    • {m}")
    pr = result.get("pull_request")
    if pr:
        print(f"\n  Generated PR : {pr.get('title')}")
        print(f"  Branch       : {pr.get('branch')}")
    if result.get("requires_human_approval"):
        print(f"\n  ⚠️  Human approval required")
    print(f"\n  Dashboard → http://localhost:3000")
    print(sep + "\n")


def auto_fix():
    import shutil
    fixed = []
    for rel in ["routes/sessions.py", "routes/products.py", "routes/orders.py"]:
        bak = BACKEND_DIR / (rel + ".bak")
        dst = BACKEND_DIR / rel
        if bak.exists():
            shutil.copy2(bak, dst)
            bak.unlink()
            fixed.append(rel)
    if fixed:
        print(f"  ✅ Auto-fixed: {', '.join(fixed)}")
        print("  Backend will hot-reload in ~2 seconds.")
    else:
        print("  No .bak files found — already clean.")


# ── Main loop ─────────────────────────────────────────────────────────────────

def main(auto_fix_flag: bool):
    global _last_alert_at

    print("=" * 65)
    print("  ShopApp → IncidentIQ Local Watcher")
    print(f"  Watching: {SHOPAPP_URL}  +  {METRICS_FILE.name}  +  source files")
    print(f"  Thresholds: error≥{THRESHOLDS['error_rate_pct']}% | "
          f"p95≥{THRESHOLDS['latency_p95_ms']}ms | any source bug")
    if auto_fix_flag:
        print("  Auto-fix: ENABLED")
    print("=" * 65)
    print("  Watching... (Ctrl+C to stop)\n")

    # Check IncidentIQ is reachable
    try:
        httpx.get(f"{INCIDENTIQ_URL}/health", timeout=3)
    except Exception:
        print(f"  ⚠️  IncidentIQ not reachable at {INCIDENTIQ_URL}")
        print("  Start it: uvicorn backend.main:app --port 8000 --reload")
        print("  Continuing anyway — will retry on each alert...\n")

    while True:
        ts = datetime.now().strftime("%H:%M:%S")

        # ── 1. Scan source files for bugs directly ────────────────────────────
        source_bugs = scan_source_for_bugs()

        # ── 2. Read metrics file ──────────────────────────────────────────────
        metrics = read_metrics_file()
        stats   = compute_stats(metrics)

        # ── 3. If no metrics yet, generate probe traffic ──────────────────────
        if not stats and source_bugs:
            print(f"  [{ts}] 🔍 Source bugs detected — generating probe traffic...")
            try:
                stats = generate_probe_traffic(n=5)
                print(f"  [{ts}]    Probe: {stats['total']} reqs, "
                      f"{stats['error_rate_pct']}% errors, "
                      f"p95={stats['p95_latency_ms']}ms")
            except Exception as e:
                print(f"  [{ts}] ⚠️  ShopApp not reachable: {e}")
                time.sleep(POLL_INTERVAL)
                continue

        # ── 4. Determine if anomalous ─────────────────────────────────────────
        metric_anomalous, metric_reasons = is_anomalous(stats) if stats else (False, [])
        bug_anomalous = len(source_bugs) > 0

        anomalous = metric_anomalous or bug_anomalous
        reasons   = metric_reasons + (["Source code bugs detected"] if bug_anomalous else [])

        # ── 5. Status line ────────────────────────────────────────────────────
        status_icon = "🔴" if anomalous else "🟢"
        bug_icon    = f" | 🐛 {len(source_bugs)} bugs in source" if source_bugs else ""
        if stats:
            print(f"  [{ts}] {status_icon} "
                  f"reqs={stats.get('total_requests',0)} "
                  f"errors={stats.get('error_rate_pct',0)}% "
                  f"p95={stats.get('p95_latency_ms',0)}ms"
                  f"{bug_icon}")
        else:
            print(f"  [{ts}] {status_icon} No traffic yet{bug_icon}")

        # ── 6. Alert if anomalous and cooldown passed ─────────────────────────
        now        = time.time()
        cooldown_ok = (now - _last_alert_at) > ALERT_COOLDOWN

        if anomalous and cooldown_ok:
            _last_alert_at = now
            print(f"\n  🚨 ANOMALY DETECTED:")
            for r in reasons:
                print(f"     • {r}")
            if source_bugs:
                print(f"\n  🐛 Bugs found in source:")
                for b in source_bugs:
                    print(f"     • {b}")

            # Generate more traffic to get solid stats if needed
            if not stats or stats.get("total_requests", 0) < 20:
                print(f"\n  📡 Generating traffic to confirm error rate...")
                try:
                    stats = generate_probe_traffic(n=10)
                    print(f"     {stats['total']} requests → "
                          f"{stats['error_rate_pct']}% errors, "
                          f"p95={stats['p95_latency_ms']}ms")
                except Exception as e:
                    print(f"     ShopApp not reachable: {e}")

            print(f"\n  📡 Sending to IncidentIQ for analysis...")
            source_files = read_source_files()
            try:
                result = send_to_incidentiq(stats or {}, reasons, source_bugs, source_files)
                print_result(result)
                if auto_fix_flag:
                    print("  🔧 Auto-fix triggered...")
                    auto_fix()
            except httpx.ConnectError:
                print(f"  ❌ Cannot reach IncidentIQ at {INCIDENTIQ_URL}")
                print("     Start it: uvicorn backend.main:app --port 8000 --reload")
            except Exception as e:
                print(f"  ❌ IncidentIQ error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShopApp local watcher → IncidentIQ")
    parser.add_argument("--auto-fix", action="store_true",
                        help="Automatically restore .bak files when bugs are detected")
    args = parser.parse_args()
    try:
        main(args.auto_fix)
    except KeyboardInterrupt:
        print("\n  Watcher stopped.")
