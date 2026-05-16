"""
IncidentIQ - GitHub Webhook Handler
Listens for PR events from GitHub. When a PR is opened/updated:
  1. Fetches the diff
  2. Runs static bug analysis via Qwen3 Coder (P3)
  3. Correlates with live OpenTelemetry signals for the affected service
  4. Posts a detailed review comment back to the PR
  5. If bugs are critical, triggers the full RCA workflow

Flow:
  GitHub PR event
      → /api/github/webhook  (this file)
      → PRAnalyzer.analyze()
          → fetch diff from GitHub API
          → detect affected service from changed files
          → pull live OTEL metrics for that service
          → Qwen3 Coder reviews the diff
          → DeepSeek V3 validates the risk
          → post review comment to PR
          → if high risk → trigger incident workflow
"""
import hashlib
import hmac
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Optional

import httpx
from fastapi import APIRouter, BackgroundTasks, Header, HTTPException, Request

from backend.bedrock.model_router import TaskType, model_router
from backend.config import config
from backend.integrations.otel_collector import otel_collector
from backend.validators.guardrail import guardrail, ActionType

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/github", tags=["GitHub"])


# ── Data models ───────────────────────────────────────────────────────────────

@dataclass
class PRFile:
    filename: str
    status: str          # added | modified | removed
    additions: int
    deletions: int
    patch: str           # the actual diff


@dataclass
class PRContext:
    pr_number: int
    pr_title: str
    pr_url: str
    author: str
    base_branch: str
    head_branch: str
    repo_full_name: str
    files: list[PRFile] = field(default_factory=list)
    description: str = ""


@dataclass
class PRReviewResult:
    pr_number: int
    risk_level: str          # "low" | "medium" | "high" | "critical"
    bugs_found: list[dict]
    security_issues: list[str]
    performance_concerns: list[str]
    otel_correlation: dict   # live metrics for affected service
    recommendation: str      # "APPROVE" | "REQUEST_CHANGES" | "COMMENT"
    review_body: str         # full markdown comment for GitHub
    confidence: float
    triggered_incident: bool = False


# ── GitHub API client ─────────────────────────────────────────────────────────

class GitHubClient:
    BASE = "https://api.github.com"

    def __init__(self):
        self.token = config.github.token
        self.headers = {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
        }

    def get_pr_files(self, owner: str, repo: str, pr_number: int) -> list[PRFile]:
        """Fetch all changed files and their diffs for a PR."""
        url = f"{self.BASE}/repos/{owner}/{repo}/pulls/{pr_number}/files"
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=self.headers)
            resp.raise_for_status()
            files = []
            for f in resp.json():
                files.append(PRFile(
                    filename=f["filename"],
                    status=f["status"],
                    additions=f.get("additions", 0),
                    deletions=f.get("deletions", 0),
                    patch=f.get("patch", ""),
                ))
            return files

    def post_review(
        self,
        owner: str,
        repo: str,
        pr_number: int,
        body: str,
        event: str = "COMMENT",  # APPROVE | REQUEST_CHANGES | COMMENT
    ) -> dict:
        """Post a review comment to a PR."""
        url = f"{self.BASE}/repos/{owner}/{repo}/pulls/{pr_number}/reviews"
        payload = {"body": body, "event": event}
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=self.headers, json=payload)
            resp.raise_for_status()
            return resp.json()

    def post_comment(self, owner: str, repo: str, pr_number: int, body: str) -> dict:
        """Post a plain issue comment to a PR."""
        url = f"{self.BASE}/repos/{owner}/{repo}/issues/{pr_number}/comments"
        with httpx.Client(timeout=30) as client:
            resp = client.post(url, headers=self.headers, json={"body": body})
            resp.raise_for_status()
            return resp.json()

    def get_pr_details(self, owner: str, repo: str, pr_number: int) -> dict:
        url = f"{self.BASE}/repos/{owner}/{repo}/pulls/{pr_number}"
        with httpx.Client(timeout=30) as client:
            resp = client.get(url, headers=self.headers)
            resp.raise_for_status()
            return resp.json()


github_client = GitHubClient()


# ── PR Analyzer ───────────────────────────────────────────────────────────────

class PRAnalyzer:
    """
    Analyzes a PR diff using AI and correlates with live OTEL telemetry.
    Uses the priority model stack:
      - Qwen3 Coder (P3) for code review
      - DeepSeek V3 (P2) for risk validation
      - Kimi K2 (P4) for fast summary generation
    """

    def analyze(self, pr: PRContext) -> PRReviewResult:
        """Full PR analysis pipeline."""
        logger.info("[PRAnalyzer] Analyzing PR #%d: %s", pr.pr_number, pr.pr_title)

        # Step 1: Detect which service is affected
        service = self._detect_service(pr.files)
        logger.info("[PRAnalyzer] Detected service: %s", service)

        # Step 2: Pull live OTEL metrics for that service
        otel_data = otel_collector.get_service_snapshot(service)
        logger.info("[PRAnalyzer] OTEL snapshot: %s", otel_data)

        # Step 3: Build the diff context for AI review
        diff_context = self._build_diff_context(pr)

        # Step 4: Qwen3 Coder reviews the code
        code_review = self._run_code_review(pr, diff_context, otel_data, service)

        # Step 5: DeepSeek V3 validates the risk assessment
        risk_validation = self._validate_risk(code_review, diff_context)

        # Step 6: Build the final review result
        result = self._build_result(pr, code_review, risk_validation, otel_data, service)

        logger.info(
            "[PRAnalyzer] PR #%d review complete: risk=%s, recommendation=%s, confidence=%.2f",
            pr.pr_number, result.risk_level, result.recommendation, result.confidence
        )
        return result

    def _detect_service(self, files: list[PRFile]) -> str:
        """Infer the affected microservice from changed file paths."""
        path_service_map = {
            "payment": "payment-service",
            "order": "order-service",
            "user": "user-service",
            "auth": "auth-service",
            "notification": "notification-service",
            "inventory": "inventory-service",
            "recommendation": "recommendation-service",
            "api_gateway": "api-gateway",
            "media": "media-service",
        }
        for f in files:
            path_lower = f.filename.lower()
            for keyword, service in path_service_map.items():
                if keyword in path_lower:
                    return service
        return "unknown-service"

    def _build_diff_context(self, pr: PRContext) -> str:
        """Build a readable diff context string for the AI."""
        lines = [
            f"## PR #{pr.pr_number}: {pr.pr_title}",
            f"**Author**: {pr.author}",
            f"**Branch**: {pr.head_branch} → {pr.base_branch}",
            f"**Description**: {pr.description or 'No description provided'}",
            "",
            f"## Changed Files ({len(pr.files)} files)",
        ]
        for f in pr.files:
            lines.append(f"\n### `{f.filename}` ({f.status}, +{f.additions}/-{f.deletions})")
            if f.patch:
                # Limit patch size to avoid token overflow
                patch = f.patch[:3000] + "\n... [truncated]" if len(f.patch) > 3000 else f.patch
                lines.append(f"```diff\n{patch}\n```")
            else:
                lines.append("_No diff available (binary or new file)_")
        return "\n".join(lines)

    def _run_code_review(
        self,
        pr: PRContext,
        diff_context: str,
        otel_data: dict,
        service: str,
    ) -> dict:
        """Use Qwen3 Coder (P3) to review the diff for bugs and issues."""
        otel_summary = self._format_otel_for_prompt(otel_data, service)

        prompt = (
            f"You are an expert code reviewer analyzing a Pull Request for production safety.\n\n"
            f"{diff_context}\n\n"
            f"## Live Service Telemetry ({service})\n{otel_summary}\n\n"
            f"Analyze this PR for:\n"
            f"1. **Bugs** — logic errors, null pointer risks, off-by-one, race conditions, "
            f"   resource leaks (connections, file handles, memory)\n"
            f"2. **Security** — SQL injection, hardcoded secrets, missing auth, insecure deserialization\n"
            f"3. **Performance** — N+1 queries, missing indexes, unbounded loops, blocking I/O\n"
            f"4. **Reliability** — missing error handling, no retry logic, missing timeouts, "
            f"   no circuit breakers\n"
            f"5. **OTEL Correlation** — does this change touch code paths that are currently "
            f"   showing elevated latency or errors in the live telemetry above?\n\n"
            f"Respond in JSON:\n"
            f"{{\n"
            f'  "risk_level": "low|medium|high|critical",\n'
            f'  "bugs": [{{"file": "...", "line_hint": "...", "severity": "low|medium|high|critical", "description": "...", "fix": "..."}}],\n'
            f'  "security_issues": ["..."],\n'
            f'  "performance_concerns": ["..."],\n'
            f'  "otel_correlation": {{"affected": true/false, "reason": "..."}},\n'
            f'  "summary": "...",\n'
            f'  "confidence": 0.0\n'
            f"}}"
        )

        try:
            response = model_router.route(
                TaskType.CODE_REVIEW,
                prompt=prompt,
                system_prompt=(
                    "You are a senior software engineer and security expert reviewing production code. "
                    "Be precise and specific. Cite exact file names and code patterns. "
                    "Never invent issues that aren't in the diff. "
                    "If the code is clean, say so clearly."
                ),
                max_tokens=3000,
                temperature=0.1,
            )
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error("[PRAnalyzer] Code review failed: %s", e)

        return {
            "risk_level": "medium",
            "bugs": [],
            "security_issues": [],
            "performance_concerns": [],
            "otel_correlation": {"affected": False, "reason": "Analysis unavailable"},
            "summary": "Automated review failed. Manual review required.",
            "confidence": 0.30,
        }

    def _validate_risk(self, code_review: dict, diff_context: str) -> dict:
        """Use DeepSeek V3 (P2) to independently validate the risk assessment."""
        if code_review.get("risk_level") in ("low",) and not code_review.get("bugs"):
            # Skip expensive validation for clean low-risk PRs
            return {"verdict": "APPROVED", "adjustment": 0, "notes": "Low risk, no validation needed"}

        prompt = (
            f"Validate this code review risk assessment:\n\n"
            f"Risk Level: {code_review.get('risk_level')}\n"
            f"Bugs Found: {json.dumps(code_review.get('bugs', []), indent=2)}\n"
            f"Security Issues: {code_review.get('security_issues', [])}\n"
            f"Summary: {code_review.get('summary', '')}\n\n"
            f"Diff context (abbreviated):\n{diff_context[:2000]}\n\n"
            f"Is this risk assessment accurate? Respond in JSON:\n"
            f'{{"verdict": "APPROVED|NEEDS_REVISION|REJECTED", '
            f'"confidence_adjustment": -0.2 to +0.2, '
            f'"notes": "..."}}'
        )

        try:
            response = model_router.route(
                TaskType.FINAL_VALIDATION,
                prompt=prompt,
                max_tokens=512,
                temperature=0.0,
            )
            import re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            logger.error("[PRAnalyzer] Risk validation failed: %s", e)

        return {"verdict": "APPROVED", "confidence_adjustment": 0, "notes": "Validation unavailable"}

    def _build_result(
        self,
        pr: PRContext,
        code_review: dict,
        risk_validation: dict,
        otel_data: dict,
        service: str,
    ) -> PRReviewResult:
        """Assemble the final review result and generate the GitHub comment."""
        risk_level = code_review.get("risk_level", "medium")
        bugs = code_review.get("bugs", [])
        security_issues = code_review.get("security_issues", [])
        performance_concerns = code_review.get("performance_concerns", [])
        otel_corr = code_review.get("otel_correlation", {})

        # Determine GitHub review action
        if risk_level == "critical" or any(b.get("severity") == "critical" for b in bugs):
            recommendation = "REQUEST_CHANGES"
        elif risk_level == "high" or security_issues:
            recommendation = "REQUEST_CHANGES"
        elif risk_level == "medium" and bugs:
            recommendation = "REQUEST_CHANGES"
        else:
            recommendation = "APPROVE"

        # Adjust confidence based on DeepSeek validation
        base_confidence = float(code_review.get("confidence", 0.75))
        adj = float(risk_validation.get("confidence_adjustment", 0))
        confidence = max(0.10, min(0.98, base_confidence + adj))

        # Build the GitHub review comment
        review_body = self._build_review_comment(
            pr, risk_level, bugs, security_issues,
            performance_concerns, otel_corr, otel_data,
            service, code_review.get("summary", ""), confidence
        )

        return PRReviewResult(
            pr_number=pr.pr_number,
            risk_level=risk_level,
            bugs_found=bugs,
            security_issues=security_issues,
            performance_concerns=performance_concerns,
            otel_correlation=otel_corr,
            recommendation=recommendation,
            review_body=review_body,
            confidence=confidence,
            triggered_incident=risk_level == "critical",
        )

    def _build_review_comment(
        self,
        pr: PRContext,
        risk_level: str,
        bugs: list,
        security_issues: list,
        performance_concerns: list,
        otel_corr: dict,
        otel_data: dict,
        service: str,
        summary: str,
        confidence: float,
    ) -> str:
        risk_emoji = {"low": "🟢", "medium": "🟡", "high": "🔴", "critical": "🚨"}.get(risk_level, "⚪")
        rec_emoji = "✅" if not bugs and not security_issues else "⚠️"

        lines = [
            f"## 🤖 IncidentIQ Automated PR Review",
            f"",
            f"| Field | Value |",
            f"|-------|-------|",
            f"| **Risk Level** | {risk_emoji} `{risk_level.upper()}` |",
            f"| **Service** | `{service}` |",
            f"| **Confidence** | `{confidence:.0%}` |",
            f"| **Models Used** | Qwen3 Coder (review) + DeepSeek V3 (validation) |",
            f"",
            f"### Summary",
            summary,
            f"",
        ]

        # Bugs section
        if bugs:
            lines += [f"### 🐛 Bugs Found ({len(bugs)})", ""]
            for b in bugs:
                sev_emoji = {"critical": "🚨", "high": "🔴", "medium": "🟡", "low": "🟢"}.get(
                    b.get("severity", "medium"), "⚪"
                )
                lines += [
                    f"#### {sev_emoji} `{b.get('file', 'unknown')}` — {b.get('description', '')}",
                    f"- **Severity**: `{b.get('severity', 'unknown')}`",
                    f"- **Location**: {b.get('line_hint', 'See diff')}",
                    f"- **Fix**: {b.get('fix', 'Manual review required')}",
                    "",
                ]
        else:
            lines += ["### ✅ No Bugs Detected", ""]

        # Security section
        if security_issues:
            lines += [f"### 🔒 Security Issues ({len(security_issues)})", ""]
            for issue in security_issues:
                lines.append(f"- 🚨 {issue}")
            lines.append("")

        # Performance section
        if performance_concerns:
            lines += [f"### ⚡ Performance Concerns ({len(performance_concerns)})", ""]
            for concern in performance_concerns:
                lines.append(f"- ⚠️ {concern}")
            lines.append("")

        # OTEL correlation section
        lines += ["### 📊 Live Telemetry Correlation", ""]
        if otel_data.get("available"):
            lines += [
                f"| Metric | Value | Status |",
                f"|--------|-------|--------|",
                f"| p99 Latency | `{otel_data.get('latency_p99_ms', 'N/A')}ms` | "
                f"{'🔴' if float(otel_data.get('latency_p99_ms', 0)) > 500 else '🟢'} |",
                f"| Error Rate | `{otel_data.get('error_rate_percent', 'N/A')}%` | "
                f"{'🔴' if float(otel_data.get('error_rate_percent', 0)) > 1 else '🟢'} |",
                f"| CPU | `{otel_data.get('cpu_percent', 'N/A')}%` | "
                f"{'🔴' if float(otel_data.get('cpu_percent', 0)) > 80 else '🟢'} |",
                "",
            ]
            if otel_corr.get("affected"):
                lines += [
                    f"> ⚠️ **OTEL Alert**: This PR touches code paths currently showing "
                    f"elevated signals in production.",
                    f"> {otel_corr.get('reason', '')}",
                    "",
                ]
        else:
            lines += [
                f"> ℹ️ Live telemetry not available for `{service}`. "
                f"Connect OpenTelemetry collector to enable real-time correlation.",
                "",
            ]

        # Footer
        lines += [
            "---",
            f"*IncidentIQ autonomous review — powered by Amazon Bedrock*  ",
            f"*[View full analysis](http://localhost:8000/docs) | "
            f"[Incident dashboard](http://localhost:8000/docs)*",
        ]

        return "\n".join(lines)

    def _format_otel_for_prompt(self, otel_data: dict, service: str) -> str:
        if not otel_data.get("available"):
            return f"No live telemetry available for {service}."
        return (
            f"- p99 latency: {otel_data.get('latency_p99_ms', 'N/A')}ms\n"
            f"- p50 latency: {otel_data.get('latency_p50_ms', 'N/A')}ms\n"
            f"- error rate: {otel_data.get('error_rate_percent', 'N/A')}%\n"
            f"- cpu: {otel_data.get('cpu_percent', 'N/A')}%\n"
            f"- memory: {otel_data.get('memory_mb', 'N/A')}MB\n"
            f"- active db connections: {otel_data.get('active_db_connections', 'N/A')}\n"
            f"- recent errors: {otel_data.get('recent_errors', [])}"
        )


pr_analyzer = PRAnalyzer()


# ── Webhook signature verification ───────────────────────────────────────────

def _verify_signature(payload: bytes, signature: str) -> bool:
    """Verify GitHub webhook HMAC-SHA256 signature."""
    secret = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
    if not secret:
        logger.warning("GITHUB_WEBHOOK_SECRET not set — skipping signature verification")
        return True
    expected = "sha256=" + hmac.new(
        secret.encode(), payload, hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(expected, signature)


# ── FastAPI webhook endpoint ──────────────────────────────────────────────────

@router.post("/webhook")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: str = Header(default=""),
    x_hub_signature_256: str = Header(default=""),
):
    """
    Receives GitHub webhook events.
    Triggers PR analysis on pull_request opened/synchronize events.
    """
    payload_bytes = await request.body()

    # Verify signature
    if x_hub_signature_256 and not _verify_signature(payload_bytes, x_hub_signature_256):
        raise HTTPException(status_code=401, detail="Invalid webhook signature")

    payload = json.loads(payload_bytes)
    action = payload.get("action", "")

    logger.info("[Webhook] GitHub event: %s / action: %s", x_github_event, action)

    # Only process PR open and update events
    if x_github_event == "pull_request" and action in ("opened", "synchronize", "reopened"):
        pr_data = payload.get("pull_request", {})
        repo = payload.get("repository", {})

        pr_context = PRContext(
            pr_number=pr_data["number"],
            pr_title=pr_data["title"],
            pr_url=pr_data["html_url"],
            author=pr_data["user"]["login"],
            base_branch=pr_data["base"]["ref"],
            head_branch=pr_data["head"]["ref"],
            repo_full_name=repo["full_name"],
            description=pr_data.get("body") or "",
        )

        # Run analysis in background so webhook returns immediately (GitHub requires <10s)
        background_tasks.add_task(_analyze_and_comment, pr_context)
        return {"status": "accepted", "pr": pr_context.pr_number, "message": "Analysis started"}

    return {"status": "ignored", "event": x_github_event, "action": action}


async def _analyze_and_comment(pr: PRContext):
    """Background task: analyze PR and post review comment."""
    try:
        owner, repo = pr.repo_full_name.split("/", 1)

        # Fetch the actual diff
        pr.files = github_client.get_pr_files(owner, repo, pr.pr_number)
        logger.info("[Webhook] Fetched %d files for PR #%d", len(pr.files), pr.pr_number)

        # Run analysis
        result = pr_analyzer.analyze(pr)

        # Post review to GitHub
        if config.github.token:
            github_client.post_review(
                owner=owner,
                repo=repo,
                pr_number=pr.pr_number,
                body=result.review_body,
                event=result.recommendation if result.recommendation in ("APPROVE", "REQUEST_CHANGES") else "COMMENT",
            )
            logger.info(
                "[Webhook] Posted review to PR #%d: %s",
                pr.pr_number, result.recommendation
            )
        else:
            logger.warning("[Webhook] No GitHub token — review not posted")

        # If critical, trigger full incident workflow
        if result.triggered_incident:
            logger.warning(
                "[Webhook] Critical PR #%d — triggering incident workflow", pr.pr_number
            )
            from backend.agents.orchestrator import orchestrator
            orchestrator.run_full_workflow(
                service=pr_analyzer._detect_service(pr.files),
                description=f"Critical bug detected in PR #{pr.pr_number}: {pr.pr_title}",
                telemetry={},
                logs=[f"PR #{pr.pr_number} introduced critical issue: {b['description']}"
                      for b in result.bugs_found if b.get("severity") == "critical"],
                deployment_history=[{
                    "version": pr.head_branch,
                    "timestamp": "",
                    "author": pr.author,
                    "description": pr.pr_title,
                }],
                severity="p1",
            )

    except Exception as e:
        logger.error("[Webhook] PR analysis failed for #%d: %s", pr.pr_number, e)
