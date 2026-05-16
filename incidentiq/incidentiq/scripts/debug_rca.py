"""Debug RCA agent directly."""
import os, sys, logging
logging.basicConfig(level=logging.ERROR)  # only show errors

from pathlib import Path
for line in (Path(__file__).parent.parent / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.agents.rca_agent import rca_agent

print("Running RCA agent...")
try:
    r = rca_agent.investigate(
        incident_id="TEST-001",
        service="shopapp",
        description="Connection pool exhausted, 25% error rate after v1.1.0 deployment",
        telemetry={"error_rate_percent": 25, "latency_p99_ms": 890},
        logs=["ERROR connection pool exhausted", "WARN SQL injection risk in products.py"],
        deployment_history=[{
            "version": "v1.1.0",
            "timestamp": "2026-05-16T10:00:00Z",
            "author": "dev",
            "description": "Add session caching"
        }],
    )
    print(f"Top hypothesis : {r.top_hypothesis.hypothesis}")
    print(f"Confidence     : {r.top_hypothesis.confidence:.0%}")
    print(f"Category       : {r.top_hypothesis.category}")
    print(f"Reasoning log  :")
    for entry in r.reasoning_log:
        print(f"  {entry}")
except Exception as e:
    import traceback
    print(f"FAILED: {e}")
    traceback.print_exc()
