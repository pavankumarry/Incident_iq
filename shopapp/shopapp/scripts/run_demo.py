"""
run_demo.py — Full end-to-end IncidentIQ demo using ShopApp.

Steps:
  1. Verify ShopApp is healthy
  2. Generate clean traffic (should be green)
  3. Introduce bugs into the backend
  4. Generate traffic that triggers errors
  5. Send telemetry + buggy code to IncidentIQ
  6. Print the RCA, generated PR, and fix suggestions
  7. Restore clean files

Run:
    python scripts/run_demo.py
"""
import sys
import os
import time
import json
import shutil
import warnings
from pathlib import Path
from datetime import datetime, timezone

# Silence deprecation warnings in demo output
warnings.filterwarnings("ignore", category=DeprecationWarning)

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

SHOPAPP_URL    = "http://localhost:8001"
INCIDENTIQ_URL = "http://localhost:8000"
BACKEND_DIR    = Path(__file__).parent.parent / "backend"


def sep(title=""):
    line = "─" * 65
    if title:
        print(f"\n{line}\n  {title}\n{line}")
    else:
        print(line)


def check_service(url: str, name: str) -> bool:
    try:
        r = httpx.get(f"{url}/health", timeout=5)
        if r.status_code == 200:
            print(f"  ✅ {name} is running at {url}")
            return True
    except Exception:
        pass
    print(f"  ❌ {name} is NOT running at {url}")
    return False


def generate_traffic(n: int = 20, expect_errors: bool = False):
    """Hit ShopApp endpoints to generate telemetry."""
    client = httpx.Client(base_url=SHOPAPP_URL, timeout=5)
    errors = 0
    for i in range(n):
        try:
            # Products list
            r = client.get("/products")
            if r.status_code >= 500:
                errors += 1

            # Category filter (injection target when buggy)
            r = client.get("/products?category=Electronics")
            if r.status_code >= 500:
                errors += 1

            # Session lookup (connection leak target when buggy)
            r = client.get("/sessions/1")
            if r.status_code >= 500:
                errors += 1

            # Order creation (timeout target when buggy)
            r = client.post("/orders", json={
                "user_id": 1,
                "items": [{"product_id": 1, "quantity": 1}]
            })
            if r.status_code >= 500:
                errors += 1

        except Exception:
            errors += 1

        time.sleep(0.1)

    client.close()
    total = n * 4
    rate = errors / total * 100
    print(f"  Traffic: {total} requests, {errors} errors ({rate:.1f}% error rate)")
    return {"total": total, "errors": errors, "error_rate_pct": round(rate, 2)}


def introduce_bugs():
    """Write buggy versions of the route files."""
    # Import and run the existing introduce_bug script
    sys.path.insert(0, str(Path(__file__).parent))
    import introduce_bug
    introduce_bug.main()


def restore_clean():
    """Restore .bak files."""
    fixed = []
    for rel in ["routes/sessions.py", "routes/products.py", "routes/orders.py"]:
        bak = BACKEND_DIR / (rel + ".bak")
        dst = BACKEND_DIR / rel
        if bak.exists():
            shutil.copy2(bak, dst)
            bak.unlink()
            fixed.append(rel)
    if fixed:
        print(f"  ✅ Restored: {', '.join(fixed)}")
    else:
        print("  Already clean.")


def read_source_files() -> dict:
    files = {}
    for rel in ["routes/sessions.py", "routes/products.py", "routes/orders.py"]:
        p = BACKEND_DIR / rel
        if p.exists():
            files[f"backend/{rel}"] = p.read_text(encoding="utf-8")
    return files


def send_to_incidentiq(traffic_stats: dict, source_files: dict) -> dict:
    payload = {
        "service": "shopapp",
        "description": (
            "ShopApp experiencing elevated error rate and latency after v1.1.0 deployment. "
            "Connection pool exhaustion, SQL injection risk, and missing timeouts detected."
        ),
        "severity": "p1",
        "telemetry": {
            "error_rate_percent": traffic_stats["error_rate_pct"],
            "latency_p99_ms": 890,
            "latency_p50_ms": 420,
            "active_db_connections": 98,
            "total_requests": traffic_stats["total"],
        },
        "logs": [
            "ERROR QueuePool limit of size 5 overflow 10 reached — connection pool exhausted",
            "WARN  Slow query on GET /sessions/1: 890ms",
            "ERROR Unhandled exception: NoneType has no attribute 'fetchone'",
            "WARN  f-string SQL interpolation detected in products.py — injection risk",
            "ERROR TimeoutError: engine.connect() blocked >30s — no timeout configured",
            f"ERROR {traffic_stats['errors']} requests returned 5xx in last 2 minutes",
        ],
        "deployment_history": [
            {
                "version": "v1.0.0",
                "timestamp": "2026-05-15T09:00:00Z",
                "author": "senior-dev",
                "description": "Initial release — clean parameterized queries, DI-managed connections",
            },
            {
                "version": "v1.1.0",
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "author": "developer",
                "description": "Add session caching and product search endpoint",
            },
        ],
        "code_context": source_files,
    }

    print("  Sending to IncidentIQ...")
    resp = httpx.post(
        f"{INCIDENTIQ_URL}/api/incident/investigate",
        json=payload,
        timeout=180.0,
    )
    resp.raise_for_status()
    return resp.json()


def print_incidentiq_result(result: dict):
    sep("🤖 IncidentIQ Analysis")

    print(f"  Incident ID : {result.get('incident_id')}")
    print(f"  Workflow    : {result.get('workflow_id')}")
    print(f"  State       : {result.get('state','').replace('WorkflowState.','')}")
    print(f"  Anomalies   : {result.get('anomalies_detected', 0)} detected")

    rca = result.get("rca", {})
    if rca:
        conf = rca.get("confidence", 0)
        print(f"\n  Root Cause ({conf*100:.0f}% confidence):")
        print(f"  → {rca.get('top_hypothesis', 'N/A')}")

        similar = rca.get("similar_incidents", 0)
        if similar:
            print(f"\n  Similar historical incidents found: {similar}")

        mitigations = rca.get("mitigations", [])
        if mitigations:
            print(f"\n  Recommended Mitigations:")
            for m in mitigations[:3]:
                print(f"    • {m}")

    pr = result.get("pull_request")
    if pr:
        print(f"\n  Generated Pull Request:")
        print(f"    Title  : {pr.get('title')}")
        print(f"    Branch : {pr.get('branch')}")
        conf = pr.get("confidence", 0)
        print(f"    Conf   : {conf*100:.0f}%")

    if result.get("requires_human_approval"):
        print(f"\n  ⚠️  Human approval required before merging the PR")

    # Show first 10 reasoning log entries
    log = result.get("reasoning_log", [])
    if log:
        print(f"\n  Reasoning Log (first 10 steps):")
        for entry in log[:10]:
            print(f"    {entry}")
        if len(log) > 10:
            print(f"    ... ({len(log) - 10} more entries)")


def main():
    print("\n" + "=" * 65)
    print("  ShopApp × IncidentIQ — End-to-End Demo")
    print("  Demonstrates: introduce bug → detect → RCA → fix")
    print("=" * 65)

    # ── Step 1: Check services ────────────────────────────────────────────────
    sep("Step 1: Checking services")
    shopapp_ok    = check_service(SHOPAPP_URL, "ShopApp backend")
    incidentiq_ok = check_service(INCIDENTIQ_URL, "IncidentIQ")

    if not shopapp_ok:
        print("\n  Start ShopApp: uvicorn main:app --port 8001 --reload")
        print("  (run from shopapp/backend/)")
        sys.exit(1)
    if not incidentiq_ok:
        print("\n  Start IncidentIQ: uvicorn backend.main:app --port 8000 --reload")
        print("  (run from incidentiq/ with PYTHONPATH=.)")
        sys.exit(1)

    # ── Step 2: Clean traffic ─────────────────────────────────────────────────
    sep("Step 2: Generating clean traffic (v1.0.0)")
    print("  Running 20 requests against the clean backend...")
    clean_stats = generate_traffic(n=20)
    if clean_stats["error_rate_pct"] < 2:
        print("  ✅ Clean — no anomalies")
    else:
        print(f"  ⚠️  Unexpected errors: {clean_stats['error_rate_pct']}%")

    # ── Step 3: Introduce bugs ────────────────────────────────────────────────
    sep("Step 3: Introducing bugs (simulating bad PR merge)")
    introduce_bugs()
    print("\n  Waiting 3s for uvicorn to hot-reload...")
    time.sleep(3)

    # ── Step 4: Buggy traffic ─────────────────────────────────────────────────
    sep("Step 4: Generating traffic against buggy backend")
    print("  Running 20 requests — expect errors...")
    buggy_stats = generate_traffic(n=20, expect_errors=True)

    # ── Step 5: Send to IncidentIQ ────────────────────────────────────────────
    sep("Step 5: Sending incident + code to IncidentIQ")
    source_files = read_source_files()
    print(f"  Files: {list(source_files.keys())}")

    try:
        result = send_to_incidentiq(buggy_stats, source_files)
        print("  ✅ IncidentIQ responded")
    except httpx.ConnectError:
        print(f"  ❌ Cannot reach IncidentIQ at {INCIDENTIQ_URL}")
        sys.exit(1)
    except Exception as e:
        print(f"  ❌ Error: {e}")
        sys.exit(1)

    # ── Step 6: Print results ─────────────────────────────────────────────────
    print_incidentiq_result(result)

    # ── Step 7: Restore clean files ───────────────────────────────────────────
    sep("Step 7: Restoring clean backend files")
    restore_clean()
    print("  Waiting 3s for uvicorn to hot-reload...")
    time.sleep(3)

    # ── Step 8: Verify recovery ───────────────────────────────────────────────
    sep("Step 8: Verifying recovery")
    recovery_stats = generate_traffic(n=10)
    if recovery_stats["error_rate_pct"] < 2:
        print("  ✅ Service recovered — error rate back to normal")
    else:
        print(f"  ⚠️  Still seeing errors: {recovery_stats['error_rate_pct']}%")

    # ── Done ──────────────────────────────────────────────────────────────────
    sep("Demo Complete")
    print(f"  Clean traffic  : {clean_stats['error_rate_pct']}% errors")
    print(f"  Buggy traffic  : {buggy_stats['error_rate_pct']}% errors")
    print(f"  After fix      : {recovery_stats['error_rate_pct']}% errors")
    print()
    print(f"  ShopApp UI     : http://localhost:3001")
    print(f"  IncidentIQ UI  : http://localhost:3000")
    print(f"  IncidentIQ API : http://localhost:8000/docs")
    print()


if __name__ == "__main__":
    main()
