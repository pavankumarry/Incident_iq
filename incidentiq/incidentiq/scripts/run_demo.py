"""
IncidentIQ - Full End-to-End Demo
Runs the hackathon demo scenario directly against Bedrock (no HTTP server needed).

Scenario: Payment service latency spike → RCA → Code fix → PR generation

Run: python scripts/run_demo.py
"""
import os
import sys
import json
import logging
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

logging.basicConfig(level=logging.WARNING)  # suppress INFO noise during demo

# ── Demo inputs ───────────────────────────────────────────────────────────────
SERVICE     = "payment-service"
SEVERITY    = "p1"
DESCRIPTION = (
    "Payment service API latency spiked to 8.2s p99 (normal: 120ms). "
    "Users experiencing checkout timeouts. Error rate at 3.2%."
)
TELEMETRY = {
    "latency_p99_ms": 8200,
    "latency_p50_ms": 1400,
    "error_rate_percent": 3.2,
    "cpu_percent": 45,
    "memory_mb": 512,
    "active_db_connections": 98,
    "requests_per_second": 340,
    "incident_start": "2026-05-16T10:00:00Z",
}
LOGS = [
    "2026-05-16T10:00:01Z ERROR Connection pool exhausted: timeout waiting for connection",
    "2026-05-16T10:00:02Z WARN  Slow query: SELECT * FROM sessions WHERE user_id=? (4.2s)",
    "2026-05-16T10:00:03Z ERROR Connection pool exhausted: timeout waiting for connection",
    "2026-05-16T10:00:05Z WARN  Redis connection timeout after 5000ms",
    "2026-05-16T10:00:07Z ERROR Payment processing failed: upstream timeout",
    "2026-05-16T10:00:09Z ERROR Connection pool exhausted: timeout waiting for connection",
]
DEPLOYMENTS = [
    {"version": "v2.4.0", "timestamp": "2026-05-16T08:30:00Z",
     "author": "alice@company.com", "description": "Add session caching layer"},
    {"version": "v2.4.1", "timestamp": "2026-05-16T09:45:00Z",
     "author": "bob@company.com",   "description": "Fix session handler exception path"},
]
CODE_CONTEXT = {
    "payment_service/session_manager.py": (
        "def get_session(user_id):\n"
        "    conn = pool.get_connection()\n"
        "    try:\n"
        "        result = conn.execute(\n"
        "            'SELECT * FROM sessions WHERE user_id = %s', user_id\n"
        "        )\n"
        "        return result.fetchone()\n"
        "    except Exception as e:\n"
        "        logger.error(f'Session fetch failed: {e}')\n"
        "        raise\n"
        "    # BUG: connection never released on exception path\n"
    )
}


def section(title: str):
    print(f"\n{'─'*62}")
    print(f"  {title}")
    print(f"{'─'*62}")


def main():
    print("\n" + "="*62)
    print("  IncidentIQ — End-to-End Demo")
    print("  Scenario: Payment service latency spike")
    print("="*62)

    from backend.agents.orchestrator import orchestrator

    section("🚀 Running 13-step autonomous investigation workflow...")
    print(f"  Service   : {SERVICE}")
    print(f"  Severity  : {SEVERITY.upper()}")
    print(f"  Incident  : {DESCRIPTION[:70]}...")

    workflow = orchestrator.run_full_workflow(
        service=SERVICE,
        description=DESCRIPTION,
        telemetry=TELEMETRY,
        logs=LOGS,
        deployment_history=DEPLOYMENTS,
        severity=SEVERITY,
        code_context=CODE_CONTEXT,
    )

    # ── Reasoning Log ─────────────────────────────────────────────────────────
    section("📋 Reasoning Log")
    for entry in workflow.reasoning_log:
        print(f"  {entry}")

    # ── Anomalies ─────────────────────────────────────────────────────────────
    section(f"🔍 Anomalies Detected: {len(workflow.anomalies)}")
    for a in workflow.anomalies:
        print(f"  [{a.severity.upper()}] {a.anomaly_type} — {a.description}")
        print(f"         Confidence: {a.confidence:.0%} | Action: {a.recommended_action[:60]}")

    # ── RCA Report ────────────────────────────────────────────────────────────
    if workflow.rca_report:
        rca = workflow.rca_report
        section("🧠 Root Cause Analysis")
        print(f"  Top Hypothesis  : {rca.top_hypothesis.hypothesis}")
        print(f"  Confidence      : {rca.top_hypothesis.confidence:.0%}")
        print(f"  Category        : {rca.top_hypothesis.category}")
        print(f"  Evidence        : {', '.join(rca.top_hypothesis.evidence[:3])}")

        if rca.similar_incidents:
            print(f"\n  Similar Historical Incidents:")
            for r in rca.similar_incidents[:3]:
                print(f"    • {r.incident.incident_id} ({r.similarity_score:.0%}) — {r.incident.title}")

        if rca.deployment_correlation:
            print(f"\n  Deployment Correlation: {rca.deployment_correlation}")

        print(f"\n  Recommended Mitigations:")
        for m in rca.recommended_mitigations[:3]:
            print(f"    → {m}")

        print(f"\n  Prevention Recommendations:")
        for p in rca.prevention_recommendations[:3]:
            print(f"    → {p}")

    # ── Pull Request ──────────────────────────────────────────────────────────
    if workflow.pull_request:
        pr = workflow.pull_request
        section("📦 Generated Pull Request")
        print(f"  Title      : {pr.title}")
        print(f"  Branch     : {pr.branch_name}")
        print(f"  Confidence : {pr.confidence:.0%}")
        print(f"\n  Problem    : {pr.problem_summary[:120]}")
        print(f"\n  Fix        : {pr.fix_explanation[:120]}")
        print(f"\n  Risk       : {pr.risk_analysis[:120]}")
        print(f"\n  Rollback   : {pr.rollback_strategy[:120]}")
        print(f"\n  Impact     : {pr.expected_impact[:120]}")
        print(f"\n  Validation :")
        for k, v in pr.validation_results.items():
            if k != "summary":
                print(f"    {k}: {v}")

        if pr.code_fixes:
            print(f"\n  Code Fixes ({len(pr.code_fixes)}):")
            for fix in pr.code_fixes:
                print(f"    📄 {fix.file_path} (risk={fix.risk_level})")
                print(f"       {fix.explanation[:100]}")

    # ── Approval Status ───────────────────────────────────────────────────────
    section("🔐 Guardrail Status")
    if workflow.requires_human_approval:
        print("  ⚠️  Human approval REQUIRED before deployment")
        print("  →  POST /api/approval  {workflow_id, approved, approver}")
    else:
        print("  ✅  No approval required for this action")

    # ── Summary ───────────────────────────────────────────────────────────────
    section("✅ Demo Complete")
    summary = orchestrator.format_workflow_summary(workflow)
    print(f"  Workflow ID      : {summary['workflow_id']}")
    print(f"  Incident ID      : {summary['incident_id']}")
    print(f"  Final State      : {summary['state']}")
    print(f"  Anomalies        : {summary['anomalies_detected']}")
    if summary.get("rca"):
        print(f"  RCA Confidence   : {summary['rca']['confidence']:.0%}" if summary['rca']['confidence'] else "  RCA Confidence   : N/A")
        print(f"  Similar Incidents: {summary['rca']['similar_incidents']}")
    if summary.get("pull_request"):
        print(f"  PR Title         : {summary['pull_request']['title']}")
    print(f"\n  API Docs → http://localhost:8000/docs")
    print(f"  Demo API → POST http://localhost:8000/api/demo/run\n")


if __name__ == "__main__":
    main()
