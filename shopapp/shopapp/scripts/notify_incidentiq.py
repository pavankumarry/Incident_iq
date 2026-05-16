"""
notify_incidentiq.py — Send buggy code directly to IncidentIQ for analysis.

Requires:
  - IncidentIQ running at http://localhost:8000
  - Bugs already introduced via: python scripts/introduce_bug.py

Run from the project root:
    python scripts/notify_incidentiq.py
"""

import json
import sys
import os
import warnings
warnings.filterwarnings("ignore", category=DeprecationWarning)
from datetime import datetime, timezone

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

BACKEND = os.path.join(os.path.dirname(__file__), "..", "backend")
INCIDENTIQ_URL = "http://localhost:8000"

# ---------------------------------------------------------------------------
# Read the (potentially buggy) route files
# ---------------------------------------------------------------------------
buggy_code: dict[str, str] = {}
for rel in ["routes/sessions.py", "routes/products.py", "routes/orders.py"]:
    path = os.path.join(BACKEND, rel)
    try:
        with open(path, encoding="utf-8") as fh:
            buggy_code[f"backend/{rel}"] = fh.read()
    except FileNotFoundError:
        print(f"Warning: {path} not found — skipping.")

if not buggy_code:
    print("No files found. Make sure you are running from the project root.")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Build the incident payload
# ---------------------------------------------------------------------------
payload = {
    "service": "shopapp",
    "description": (
        "Developer introduced bugs in session management and SQL queries. "
        "Symptoms: connection pool exhaustion, slow queries, unhandled exceptions."
    ),
    "severity": "p1",
    "telemetry": {
        "latency_p99_ms": 450,
        "error_rate_percent": 2.1,
        "cpu_percent": 55,
        "active_connections": 98,
        "connection_pool_exhausted": True,
    },
    "logs": [
        "ERROR Connection pool exhausted after 30s — QueuePool limit of size 5 overflow 10 reached",
        "WARN  Slow query detected: 890ms on GET /sessions/42",
        "ERROR Unhandled exception in session handler: NoneType has no attribute 'fetchone'",
        "WARN  SQL query contains user-supplied string interpolation (possible injection)",
        "ERROR TimeoutError: engine.connect() blocked for >30s with no timeout configured",
    ],
    "deployment_history": [
        {
            "version": "v1.0.0",
            "timestamp": "2026-05-15T09:00:00Z",
            "author": "senior-dev",
            "description": "Initial release — clean, parameterized queries, DI-managed connections",
        },
        {
            "version": "v1.1.0",
            "timestamp": "2026-05-16T10:00:00Z",
            "author": "developer",
            "description": "Add session caching and product search endpoint",
        },
    ],
    "code_context": buggy_code,
}

# ---------------------------------------------------------------------------
# Send to IncidentIQ
# ---------------------------------------------------------------------------
print("Sending incident to IncidentIQ at", INCIDENTIQ_URL)
print(f"  Files included: {list(buggy_code.keys())}")
print()

try:
    response = httpx.post(
        f"{INCIDENTIQ_URL}/api/incident/investigate",
        json=payload,
        timeout=60.0,
    )
    response.raise_for_status()
    print("Response from IncidentIQ:")
    print(json.dumps(response.json(), indent=2))
except httpx.ConnectError:
    print(f"Could not connect to IncidentIQ at {INCIDENTIQ_URL}.")
    print("Make sure IncidentIQ is running: cd ../incidentiq && uvicorn backend.main:app --port 8000")
    sys.exit(1)
except httpx.HTTPStatusError as exc:
    print(f"HTTP error {exc.response.status_code}: {exc.response.text}")
    sys.exit(1)
