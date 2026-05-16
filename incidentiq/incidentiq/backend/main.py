"""
IncidentIQ - FastAPI Gateway
Main API entry point. Provides REST endpoints and WebSocket streaming
for the incident response platform.
"""
import logging
import uuid
from datetime import datetime
from typing import Optional

from dotenv import load_dotenv
load_dotenv()  # Load .env before anything else touches boto3/AWS

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from backend.agents.orchestrator import orchestrator
from backend.agents.incident_copilot_agent import incident_copilot
from backend.agents.observability_agent import TelemetrySnapshot, observability_agent
from backend.validators.guardrail import guardrail, ActionType
from backend.integrations.github_webhook import router as github_router
from backend.config import config

logging.basicConfig(
    level=getattr(logging, config.log_level),
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="IncidentIQ",
    description="Real-time AI co-pilot for incident response — powered by Amazon Bedrock",
    version="1.0.0",
    docs_url="/docs",
    redoc_url="/redoc",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Restrict in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers
app.include_router(github_router)


# ─── Request/Response Models ──────────────────────────────────────────────────

class TelemetryInput(BaseModel):
    service: str
    latency_p99_ms: Optional[float] = None
    latency_p50_ms: Optional[float] = None
    error_rate_percent: Optional[float] = None
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None
    requests_per_second: Optional[float] = None
    active_db_connections: Optional[int] = None
    pod_restarts: Optional[int] = None
    deployment_version: Optional[str] = None
    raw_logs: list[str] = Field(default_factory=list)
    custom_metrics: dict = Field(default_factory=dict)


class IncidentInvestigationRequest(BaseModel):
    service: str
    description: str
    severity: str = "p2"
    telemetry: dict = Field(default_factory=dict)
    logs: list[str] = Field(default_factory=list)
    deployment_history: list[dict] = Field(default_factory=list)
    dependency_graph: Optional[dict] = None
    code_context: Optional[dict] = None  # {file_path: code_content}


class CopilotUpdateRequest(BaseModel):
    incident_id: str
    update_type: str  # "slack_message", "metric_update", "action_taken"
    content: str
    metrics: Optional[dict] = None


class ApprovalRequest(BaseModel):
    workflow_id: str
    approved: bool
    approver: str
    reason: Optional[str] = None


# ─── Health & Status ──────────────────────────────────────────────────────────

@app.get("/health")
def health_check():
    return {
        "status": "healthy",
        "service": "incidentiq",
        "version": "1.0.0",
        "timestamp": datetime.utcnow().isoformat(),
        "bedrock_region": config.bedrock.region,
        "advisory_only_mode": config.guardrails.advisory_only_mode,
    }


@app.get("/config")
def get_config():
    """Return non-sensitive configuration for the frontend."""
    return {
        "confidence_threshold": config.guardrails.confidence_threshold,
        "advisory_only_mode": config.guardrails.advisory_only_mode,
        "max_interjection_interval_seconds": config.guardrails.max_interjection_interval_seconds,
        "vector_db_provider": config.vector_db.provider,
        "environment": config.environment,
    }


# ─── Telemetry & Anomaly Detection ───────────────────────────────────────────

@app.post("/api/telemetry/analyze")
def analyze_telemetry(input: TelemetryInput):
    """
    Analyze a telemetry snapshot for anomalies.
    Returns detected anomalies with severity and confidence scores.
    """
    snapshot = TelemetrySnapshot(
        service=input.service,
        timestamp=datetime.utcnow().isoformat(),
        latency_p99_ms=input.latency_p99_ms,
        latency_p50_ms=input.latency_p50_ms,
        error_rate_percent=input.error_rate_percent,
        cpu_percent=input.cpu_percent,
        memory_mb=input.memory_mb,
        requests_per_second=input.requests_per_second,
        active_db_connections=input.active_db_connections,
        pod_restarts=input.pod_restarts,
        deployment_version=input.deployment_version,
        raw_logs=input.raw_logs,
        custom_metrics=input.custom_metrics,
    )

    anomalies = observability_agent.analyze_telemetry(snapshot)
    summary = observability_agent.generate_anomaly_report_summary(anomalies)

    return {
        "service": input.service,
        "anomalies_detected": len(anomalies),
        "anomalies": [
            {
                "anomaly_id": a.anomaly_id,
                "type": a.anomaly_type,
                "severity": a.severity,
                "description": a.description,
                "confidence": a.confidence,
                "recommended_action": a.recommended_action,
                "evidence": a.evidence,
            }
            for a in anomalies
        ],
        "summary": summary,
    }


# ─── Full Incident Investigation ──────────────────────────────────────────────

@app.post("/api/incident/investigate")
def investigate_incident(request: IncidentInvestigationRequest):
    """
    Run the full 13-step autonomous incident investigation workflow.
    Returns RCA report, PR, reasoning log, and approval status.
    """
    # Guardrail: sanitize description to prevent prompt injection
    safe_description = guardrail.sanitize_for_llm(request.description)

    workflow = orchestrator.run_full_workflow(
        service=request.service,
        description=safe_description,
        telemetry=request.telemetry,
        logs=request.logs,
        deployment_history=request.deployment_history,
        severity=request.severity,
        dependency_graph=request.dependency_graph,
        code_context=request.code_context,
    )

    return orchestrator.format_workflow_summary(workflow)


@app.get("/api/incident/{incident_id}/reasoning-log")
def get_reasoning_log(incident_id: str):
    """Return the full reasoning log for an incident workflow."""
    # In production: fetch from persistent store
    return {"incident_id": incident_id, "message": "Reasoning log stored in workflow result"}


# ─── Incident Copilot ─────────────────────────────────────────────────────────

@app.post("/api/copilot/start")
def start_incident_tracking(
    incident_id: str,
    service: str,
    severity: str,
    description: str,
):
    """Start real-time copilot tracking for an incident."""
    context = incident_copilot.start_incident(
        incident_id=incident_id,
        service=service,
        severity=severity,
        initial_description=description,
    )
    return {
        "incident_id": context.incident_id,
        "service": context.service,
        "severity": context.severity,
        "message": "Copilot tracking started",
    }


@app.post("/api/copilot/update")
def process_copilot_update(request: CopilotUpdateRequest):
    """
    Send an incident update to the copilot.
    Returns an interjection if confidence threshold is met.
    """
    interjection = incident_copilot.process_update(
        incident_id=request.incident_id,
        update_type=request.update_type,
        content=request.content,
        metrics=request.metrics,
    )

    if interjection:
        return {
            "interjection": {
                "message": interjection.message,
                "evidence": interjection.evidence,
                "similar_incident_ref": interjection.similar_incident_ref,
                "confidence": interjection.confidence,
                "suggested_command": interjection.suggested_command,
                "expected_outcome": interjection.expected_outcome,
                "priority": interjection.priority,
            }
        }
    return {"interjection": None, "message": "No high-confidence interjection at this time"}


@app.get("/api/copilot/{incident_id}/summary")
def get_incident_summary(incident_id: str):
    """Get a live summary of the current incident state."""
    summary = incident_copilot.generate_live_summary(incident_id)
    return {"incident_id": incident_id, "summary": summary}


@app.post("/api/copilot/{incident_id}/postmortem")
def generate_postmortem(incident_id: str):
    """Auto-generate a postmortem document for a resolved incident."""
    postmortem = incident_copilot.generate_postmortem(incident_id, rca_report=None)
    return {"incident_id": incident_id, "postmortem": postmortem}


@app.post("/api/copilot/{incident_id}/close")
def close_incident(incident_id: str):
    """Close an incident and return summary statistics."""
    stats = incident_copilot.close_incident(incident_id)
    return stats


# ─── Human Approval Workflow ──────────────────────────────────────────────────

@app.post("/api/approval")
def process_approval(request: ApprovalRequest):
    """
    Process a human approval decision for a pending workflow action.
    Required for production deployments, schema changes, and other critical actions.
    """
    # Audit log the approval decision
    guardrail.audit_log(
        action_type=ActionType.DEPLOY_TO_PRODUCTION,
        actor=request.approver,
        result={"allowed": request.approved, "requires_approval": True},
        context={"workflow_id": request.workflow_id, "reason": request.reason},
    )

    return {
        "workflow_id": request.workflow_id,
        "approved": request.approved,
        "approver": request.approver,
        "timestamp": datetime.utcnow().isoformat(),
        "message": "Approval recorded. Workflow will proceed." if request.approved
                   else "Workflow blocked by human reviewer.",
    }


# ─── WebSocket: Real-time Incident Streaming ─────────────────────────────────

@app.websocket("/ws/incident/{incident_id}")
async def incident_websocket(websocket: WebSocket, incident_id: str):
    """
    WebSocket endpoint for real-time incident streaming.
    Streams copilot interjections, metric updates, and reasoning logs.
    """
    await websocket.accept()
    logger.info("WebSocket connected for incident %s", incident_id)

    try:
        while True:
            data = await websocket.receive_json()
            update_type = data.get("type", "slack_message")
            content = data.get("content", "")
            metrics = data.get("metrics")

            interjection = incident_copilot.process_update(
                incident_id=incident_id,
                update_type=update_type,
                content=content,
                metrics=metrics,
            )

            response = {
                "incident_id": incident_id,
                "timestamp": datetime.utcnow().isoformat(),
                "interjection": None,
            }

            if interjection:
                response["interjection"] = {
                    "message": interjection.message,
                    "confidence": interjection.confidence,
                    "evidence": interjection.evidence,
                    "similar_incident_ref": interjection.similar_incident_ref,
                    "suggested_command": interjection.suggested_command,
                    "priority": interjection.priority,
                }

            await websocket.send_json(response)

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected for incident %s", incident_id)


# ─── PR Analysis (manual trigger) ────────────────────────────────────────────

class ManualPRRequest(BaseModel):
    repo_owner: str
    repo_name: str
    pr_number: int


@app.post("/api/pr/analyze")
def analyze_pr(request: ManualPRRequest):
    """
    Manually trigger PR analysis for any PR.
    Fetches the diff from GitHub, runs AI review with OTEL correlation,
    and posts the review comment back to the PR.
    Use this to test the pipeline without setting up a webhook.
    """
    from backend.integrations.github_webhook import (
        PRContext, github_client, pr_analyzer
    )

    # Fetch PR details from GitHub
    try:
        pr_data = github_client.get_pr_details(
            request.repo_owner, request.repo_name, request.pr_number
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch PR: {e}")

    pr = PRContext(
        pr_number=request.pr_number,
        pr_title=pr_data["title"],
        pr_url=pr_data["html_url"],
        author=pr_data["user"]["login"],
        base_branch=pr_data["base"]["ref"],
        head_branch=pr_data["head"]["ref"],
        repo_full_name=f"{request.repo_owner}/{request.repo_name}",
        description=pr_data.get("body") or "",
    )

    # Fetch diff
    try:
        pr.files = github_client.get_pr_files(
            request.repo_owner, request.repo_name, request.pr_number
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to fetch PR files: {e}")

    # Run analysis
    result = pr_analyzer.analyze(pr)

    # Post review to GitHub
    posted = False
    if config.github.token:
        try:
            github_client.post_review(
                owner=request.repo_owner,
                repo=request.repo_name,
                pr_number=request.pr_number,
                body=result.review_body,
                event=result.recommendation if result.recommendation in (
                    "APPROVE", "REQUEST_CHANGES"
                ) else "COMMENT",
            )
            posted = True
        except Exception as e:
            logger.warning("Failed to post review to GitHub: %s", e)

    return {
        "pr_number": result.pr_number,
        "risk_level": result.risk_level,
        "recommendation": result.recommendation,
        "confidence": result.confidence,
        "bugs_found": len(result.bugs_found),
        "security_issues": len(result.security_issues),
        "performance_concerns": len(result.performance_concerns),
        "otel_correlation": result.otel_correlation,
        "triggered_incident": result.triggered_incident,
        "review_posted_to_github": posted,
        "review_body": result.review_body,
    }


@app.get("/api/pr/otel/{service}")
def get_service_telemetry(service: str):
    """Get live OTEL telemetry snapshot for a service."""
    from backend.integrations.otel_collector import otel_collector
    return otel_collector.get_service_snapshot(service)


# ─── Demo Scenario ────────────────────────────────────────────────────────────

@app.post("/api/demo/run")
def run_demo_scenario():
    """
    Run the hackathon demo scenario:
    Payment service latency spike → RCA → PR generation.
    """
    demo_request = IncidentInvestigationRequest(
        service="payment-service",
        description="Payment service API latency spiked to 8s p99. Users experiencing checkout timeouts.",
        severity="p1",
        telemetry={
            "latency_p99_ms": 8200,
            "latency_p50_ms": 1400,
            "error_rate_percent": 3.2,
            "cpu_percent": 45,
            "memory_mb": 512,
            "active_db_connections": 98,
            "requests_per_second": 340,
        },
        logs=[
            "2026-05-16T10:00:01Z ERROR Connection pool exhausted: timeout waiting for connection",
            "2026-05-16T10:00:02Z WARN  Slow query detected: SELECT * FROM sessions WHERE user_id=? (4.2s)",
            "2026-05-16T10:00:03Z ERROR Connection pool exhausted: timeout waiting for connection",
            "2026-05-16T10:00:05Z WARN  Redis connection timeout after 5000ms",
            "2026-05-16T10:00:07Z ERROR Payment processing failed: upstream timeout",
        ],
        deployment_history=[
            {
                "version": "v2.4.0",
                "timestamp": "2026-05-16T08:30:00Z",
                "author": "alice@company.com",
                "description": "Add session caching layer",
            },
            {
                "version": "v2.4.1",
                "timestamp": "2026-05-16T09:45:00Z",
                "author": "bob@company.com",
                "description": "Fix session handler exception path",
            },
        ],
        code_context={
            "payment_service/session_manager.py": (
                "def get_session(user_id):\n"
                "    conn = pool.get_connection()\n"
                "    try:\n"
                "        result = conn.execute('SELECT * FROM sessions WHERE user_id = %s', user_id)\n"
                "        return result.fetchone()\n"
                "    except Exception as e:\n"
                "        logger.error(f'Session fetch failed: {e}')\n"
                "        raise\n"
                "    # BUG: connection never released on exception path\n"
            )
        },
    )

    return investigate_incident(demo_request)
