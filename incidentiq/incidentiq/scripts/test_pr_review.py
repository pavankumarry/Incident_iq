"""
IncidentIQ - PR Review Demo (no GitHub needed)
Simulates a PR with a buggy code change and runs the full AI review pipeline.

Demonstrates:
  - Qwen3 Coder (P3) reviewing the diff for bugs
  - DeepSeek V3 (P2) validating the risk
  - OTEL correlation showing live service metrics
  - Auto-generated GitHub review comment

Run: python scripts/test_pr_review.py
"""
import os, sys, json
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import logging
logging.basicConfig(level=logging.WARNING)

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.integrations.github_webhook import PRContext, PRFile, pr_analyzer


# ── Simulated PR with intentional bugs ───────────────────────────────────────
# This mimics what happens when YOU push a real PR to GitHub.
# The agent will catch these issues automatically.

BUGGY_DIFF = """\
diff --git a/payment_service/session_manager.py b/payment_service/session_manager.py
index a1b2c3d..e4f5g6h 100644
--- a/payment_service/session_manager.py
+++ b/payment_service/session_manager.py
@@ -1,12 +1,28 @@
+import os
+
 def get_session(user_id):
-    conn = pool.get_connection()
+    # BUG 1: connection never released on exception path (resource leak)
+    conn = pool.get_connection()
     try:
-        result = conn.execute('SELECT * FROM sessions WHERE user_id = %s', user_id)
+        # BUG 2: SQL injection - f-string instead of parameterized query
+        result = conn.execute(f'SELECT * FROM sessions WHERE user_id = {user_id}')
         return result.fetchone()
     except Exception as e:
         logger.error(f'Session fetch failed: {e}')
         raise
+    # connection never released here ^
+
+def update_session(user_id, data):
+    # BUG 3: hardcoded secret
+    db_password = "prod_secret_123"
+    conn = pool.get_connection()
+    # BUG 4: no timeout on DB operation (can block forever)
+    conn.execute(f"UPDATE sessions SET data='{data}' WHERE user_id={user_id}")
+    conn.commit()
+    # BUG 5: connection not released in finally block
+
+def delete_all_sessions():
+    # BUG 6: dangerous operation with no authorization check
+    conn = pool.get_connection()
+    conn.execute("DELETE FROM sessions")
+    conn.commit()
"""

CLEAN_DIFF = """\
diff --git a/order_service/utils.py b/order_service/utils.py
index 1234567..abcdefg 100644
--- a/order_service/utils.py
+++ b/order_service/utils.py
@@ -5,6 +5,10 @@
 def format_order_id(order_id: int) -> str:
-    return str(order_id)
+    \"\"\"Format order ID with zero-padding for display.\"\"\"
+    if not isinstance(order_id, int) or order_id < 0:
+        raise ValueError(f"Invalid order_id: {order_id}")
+    return f"ORD-{order_id:08d}"
"""


def section(title):
    print(f"\n{'─'*65}")
    print(f"  {title}")
    print(f"{'─'*65}")


def run_review(label: str, pr: PRContext):
    print(f"\n{'='*65}")
    print(f"  🔍 Analyzing: {label}")
    print(f"  PR #{pr.pr_number}: {pr.pr_title}")
    print(f"  Author: {pr.author}  |  Branch: {pr.head_branch} → {pr.base_branch}")
    print(f"{'='*65}")

    result = pr_analyzer.analyze(pr)

    section(f"Risk Assessment")
    risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}.get(result.risk_level, "⚪")
    print(f"  Risk Level     : {risk_emoji} {result.risk_level.upper()}")
    print(f"  Recommendation : {result.recommendation}")
    print(f"  Confidence     : {result.confidence:.0%}")
    print(f"  Bugs Found     : {len(result.bugs_found)}")
    print(f"  Security Issues: {len(result.security_issues)}")
    print(f"  Perf Concerns  : {len(result.performance_concerns)}")

    if result.bugs_found:
        section("Bugs Detected")
        for b in result.bugs_found:
            sev = b.get("severity", "?")
            sev_emoji = {"critical": "🚨", "high": "🔴", "medium": "🟡", "low": "🟢"}.get(sev, "⚪")
            print(f"  {sev_emoji} [{sev.upper()}] {b.get('file', '?')}")
            print(f"     Issue : {b.get('description', '')}")
            print(f"     Fix   : {b.get('fix', '')}")
            print()

    if result.security_issues:
        section("Security Issues")
        for s in result.security_issues:
            print(f"  🔒 {s}")

    if result.performance_concerns:
        section("Performance Concerns")
        for p in result.performance_concerns:
            print(f"  ⚡ {p}")

    section("OTEL Correlation")
    otel = result.otel_correlation
    print(f"  Affected: {otel.get('affected', False)}")
    print(f"  Reason  : {otel.get('reason', 'N/A')}")

    section("Generated GitHub Review Comment (preview)")
    # Show first 60 lines of the review
    preview_lines = result.review_body.split("\n")[:60]
    for line in preview_lines:
        print(f"  {line}")
    if len(result.review_body.split("\n")) > 60:
        print(f"  ... [{len(result.review_body.split(chr(10))) - 60} more lines]")

    if result.triggered_incident:
        section("⚠️  INCIDENT TRIGGERED")
        print("  Critical bugs detected — full RCA workflow would be triggered.")
        print("  In production: creates incident, pages on-call, starts investigation.")

    return result


def main():
    print("\n" + "="*65)
    print("  IncidentIQ — PR Review Demo")
    print("  Shows what happens when YOU push a PR with bugs")
    print("="*65)

    # ── Test 1: Buggy PR (should REQUEST_CHANGES) ─────────────────────────────
    buggy_pr = PRContext(
        pr_number=42,
        pr_title="Add session caching and update session management",
        pr_url="https://github.com/pavankumarry/incidentiq/pull/42",
        author="developer",
        base_branch="main",
        head_branch="feature/session-caching",
        repo_full_name="pavankumarry/incidentiq",
        description="Adds session caching layer and updates session CRUD operations.",
        files=[
            PRFile(
                filename="payment_service/session_manager.py",
                status="modified",
                additions=16,
                deletions=3,
                patch=BUGGY_DIFF,
            )
        ],
    )

    result1 = run_review("BUGGY PR (should catch issues)", buggy_pr)

    # ── Test 2: Clean PR (should APPROVE) ─────────────────────────────────────
    clean_pr = PRContext(
        pr_number=43,
        pr_title="Improve order ID formatting with validation",
        pr_url="https://github.com/pavankumarry/incidentiq/pull/43",
        author="developer",
        base_branch="main",
        head_branch="fix/order-id-format",
        repo_full_name="pavankumarry/incidentiq",
        description="Adds input validation and consistent formatting to order IDs.",
        files=[
            PRFile(
                filename="order_service/utils.py",
                status="modified",
                additions=4,
                deletions=1,
                patch=CLEAN_DIFF,
            )
        ],
    )

    result2 = run_review("CLEAN PR (should approve)", clean_pr)

    # ── Summary ───────────────────────────────────────────────────────────────
    print("\n" + "="*65)
    print("  📊 Summary")
    print("="*65)
    print(f"  PR #42 (buggy) : {result1.recommendation} — {result1.risk_level.upper()} risk, "
          f"{len(result1.bugs_found)} bugs, confidence {result1.confidence:.0%}")
    print(f"  PR #43 (clean) : {result2.recommendation} — {result2.risk_level.upper()} risk, "
          f"{len(result2.bugs_found)} bugs, confidence {result2.confidence:.0%}")
    print()
    print("  To connect to a REAL GitHub repo:")
    print("  1. Set GITHUB_TOKEN and GITHUB_WEBHOOK_SECRET in .env")
    print("  2. Run: python scripts/setup_webhook.py")
    print("  3. Push any PR — IncidentIQ will auto-review it")
    print()
    print("  Manual trigger via API:")
    print('  POST http://localhost:8000/api/pr/analyze')
    print('  {"repo_owner": "you", "repo_name": "repo", "pr_number": 42}')
    print()


if __name__ == "__main__":
    main()
