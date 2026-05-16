"""
watch_and_alert.py — Continuously monitors ShopApp telemetry.
When anomalies are detected (after bugs are introduced), automatically
sends the incident + buggy code to IncidentIQ for analysis and fix generation.

Run in a separate terminal:
    python scripts/watch_and_alert.py

Workflow:
  1. Polls GET http://localhost:8001/metrics every 5 seconds
  2. Detects error spikes, latency increases, connection pool issues
  3. Reads the current backend source files
  4. POSTs to IncidentIQ /api/incident/investigate
  5. Prints the RCA + generated fix to the terminal
  6. Optionally auto-applies the fix (--auto-fix flag)
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
POLL_INTERVAL  = 5   # seconds
WINDOW         = 20  # number of recent metrics to analyse

# Thresholds that trigger an alert
THRESHOLDS = {
    "error_rate_pct":  2.0,   # % of requests that are 5xx
    "latency_p95_ms":  800,   # ms
    "latency_avg_ms":  400,   # ms
}

# Track whether we already fired an alert (avoid spam)
_alert_fired = False
_last_alert_at = 0.0
ALERT_COOLDOWN = 60  # seconds between repeated alerts


def read_source_files() -> dict[str, str]:
    """Read the current (possibly buggy) backend route files."""
    files = {}
    for rel in ["routes/sessions.py", "routes/products.py", "routes/orders.py"]:
        path = BACKEND_DIR / rel
        if path.exists():
            files[f"backend/{rel}"] = path.read_text(encoding="utf-8")
    return files


def compute_stats(metrics: list[dict]) -> dict:
    """Compute aggregate stats from a window of metric entries."""
    if not metrics:
        return {}

    requests = [m for m in metrics if m.get("type") == "request"]
    if not requests:
        return {}

    total      = len(requests)
    errors     = sum(1 for m in requests if m.get("is_error"))
    latencies  = [m["latency_ms"] for m in requests if "latency_ms" in m]

    error_rate = (errors / total * 100) if total else 0
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
    """Return (anomalous, reasons) based on current stats."""
    reasons = []
    if stats.get("error_rate_pct", 0) >= THRESHOLDS["error_rate_pct"]:
        reasons.append(
            f"Error rate {stats['error_rate_pct']}% ≥ threshold {THRESHOLDS['error_rate_pct']}%"
        )
    if stats.get("p95_latency_ms", 0) >= THRESHOLDS["latency_p95_ms"]:
        reasons.append(
            f"p95 latency {stats['p95_latency_ms']}ms ≥ threshold {THRESHOLDS['latency_p95_ms']}ms"
        )
    if stats.get("avg_latency_ms", 0) >= THRESHOLDS["latency_avg_ms"]:
        reasons.append(
            f"Avg latency {stats['avg_latency_ms']}ms ≥ threshold {THRESHOLDS['latency_avg_ms']}ms"
        )
    return bool(reasons), reasons


def send_to_incidentiq(stats: dict, reasons: list[str], source_files: dict) -> dict:
    """POST the incident to IncidentIQ and return the analysis result."""
    error_paths = stats.get("error_paths", {})
    log_lines = [
        f"ERROR rate spike: {stats['error_rate_pct']}% of requests returning 5xx",
        f"WARN  p95 latency: {stats['p95_latency_ms']}ms (threshold: {THRESHOLDS['latency_p95_ms']}ms)",
    ]
    for path, count in error_paths.items():
        log_lines.append(f"ERROR {count} errors on endpoint: {path}")

    # Add common bug signatures if present in source
    for fname, code in source_files.items():
        if "conn = engine.connect()" in code and "conn.close()" not in code:
            log_lines.append("ERROR Connection pool exhausted — raw connections never released")
        if "f\"SELECT" in code or "f'SELECT" in code:
            log_lines.append("WARN  SQL injection risk — f-string interpolation in query")

    payload = {
        "service": "shopapp",
        "description": (
            f"ShopApp anomaly detected. Reasons: {'; '.join(reasons)}. "
            f"Error rate: {stats['error_rate_pct']}%, "
            f"p95 latency: {stats['p95_latency_ms']}ms."
        ),
        "severity": "p1" if stats.get("error_rate_pct", 0) > 5 else "p2",
        "telemetry": {
            "error_rate_percent": stats["error_rate_pct"],
            "latency_p99_ms":     stats["p95_latency_ms"],
            "latency_p50_ms":     stats["avg_latency_ms"],
            "total_requests":     stats["total_requests"],
        },
        "logs": log_lines,
        "deployment_history": [
            {
                "version": "v1.0.0",
                "timestamp": "2026-05-15T09:00:00Z",
                "author": "senior-dev",
                "description": "Initial clean release",
            },
            {
                "version": "v1.1.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "author": "developer",
                "description": "Add session caching and product search",
            },
        ],
        "code_context": source_files,
    }

    resp = httpx.post(
        f"{INCIDENTIQ_URL}/api/incident/investigate",
        json=payload,
        timeout=120.0,
    )
    resp.raise_for_status()
    return resp.json()


def print_result(result: dict):
    """Pretty-print the IncidentIQ analysis result."""
    sep = "─" * 65
    print(f"\n{sep}")
    print(f"  🤖 IncidentIQ Analysis Complete")
    print(sep)
    print(f"  Incident  : {result.get('incident_id', 'N/A')}")
    print(f"  State     : {result.get('state', 'N/A').replace('WorkflowState.', '')}")
    print(f"  Anomalies : {result.get('anomalies_detected', 0)}")

    rca = result.get("rca", {})
    if rca:
        conf = rca.get("confidence", 0)
        print(f"\n  Root Cause ({conf*100:.0f}% confidence):")
        print(f"  → {rca.get('top_hypothesis', 'N/A')}")

        mitigations = rca.get("mitigations", [])
        if mitigations:
            print(f"\n  Immediate Mitigations:")
            for m in mitigations[:3]:
                print(f"    • {m}")

    pr = result.get("pull_request")
    if pr:
        print(f"\n  Generated PR:")
        print(f"    Title  : {pr.get('title', 'N/A')}")
        print(f"    Branch : {pr.get('branch', 'N/A')}")
        conf = pr.get("confidence", 0)
        print(f"    Conf   : {conf*100:.0f}%")

    if result.get("requires_human_approval"):
        print(f"\n  ⚠️  Human approval required before deployment")

    print(f"\n  Full reasoning log: http://localhost:8000/docs")
    print(sep + "\n")


def auto_fix():
    """Restore clean files from .bak backups."""
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


def main(auto_fix_flag: bool):
    global _alert_fired, _last_alert_at

    print("=" * 65)
    print("  ShopApp → IncidentIQ Watcher")
    print(f"  Polling {SHOPAPP_URL}/metrics every {POLL_INTERVAL}s")
    print(f"  Thresholds: error≥{THRESHOLDS['error_rate_pct']}% | "
          f"p95≥{THRESHOLDS['latency_p95_ms']}ms")
    if auto_fix_flag:
        print("  Auto-fix: ENABLED (will restore .bak files on alert)")
    print("=" * 65)
    print("  Watching... (Ctrl+C to stop)\n")

    recent: deque = deque(maxlen=WINDOW)

    while True:
        try:
            resp = httpx.get(f"{SHOPAPP_URL}/metrics", timeout=5)
            if resp.status_code == 200:
                metrics = resp.json()
                recent.extend(metrics[-WINDOW:])
        except Exception as e:
            print(f"  ⚠️  Cannot reach ShopApp ({e}) — retrying...")
            time.sleep(POLL_INTERVAL)
            continue

        stats = compute_stats(list(recent))
        if not stats:
            print(f"  [{datetime.now().strftime('%H:%M:%S')}] No requests yet — waiting...")
            time.sleep(POLL_INTERVAL)
            continue

        anomalous, reasons = is_anomalous(stats)
        now = time.time()
        cooldown_ok = (now - _last_alert_at) > ALERT_COOLDOWN

        status_icon = "🔴" if anomalous else "🟢"
        print(
            f"  [{datetime.now().strftime('%H:%M:%S')}] {status_icon} "
            f"reqs={stats['total_requests']} "
            f"errors={stats['error_rate_pct']}% "
            f"p95={stats['p95_latency_ms']}ms "
            f"avg={stats['avg_latency_ms']}ms"
        )

        if anomalous and cooldown_ok:
            _last_alert_at = now
            print(f"\n  🚨 ANOMALY DETECTED:")
            for r in reasons:
                print(f"     • {r}")
            print(f"\n  📡 Sending to IncidentIQ for analysis...")

            source_files = read_source_files()
            try:
                result = send_to_incidentiq(stats, reasons, source_files)
                print_result(result)

                if auto_fix_flag:
                    print("  🔧 Auto-fix triggered...")
                    auto_fix()

            except httpx.ConnectError:
                print(f"  ❌ Cannot reach IncidentIQ at {INCIDENTIQ_URL}")
                print("     Start it: cd ../incidentiq && uvicorn backend.main:app --port 8000")
            except Exception as e:
                print(f"  ❌ IncidentIQ error: {e}")

        time.sleep(POLL_INTERVAL)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="ShopApp → IncidentIQ watcher")
    parser.add_argument("--auto-fix", action="store_true",
                        help="Automatically restore clean files when bugs are detected")
    args = parser.parse_args()
    try:
        main(args.auto_fix)
    except KeyboardInterrupt:
        print("\n  Watcher stopped.")
