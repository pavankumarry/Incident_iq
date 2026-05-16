"""
IncidentIQ - Incident Copilot Agent
Real-time AI second pair of eyes during incidents.
Watches Slack threads, PagerDuty alerts, logs, and metrics.
Provides smart interjections with confidence gating.
"""
import logging
import time
from dataclasses import dataclass, field
from typing import Optional

from backend.bedrock.model_router import TaskType, model_router
from backend.memory.vector_store import vector_store
from backend.config import config

logger = logging.getLogger(__name__)


@dataclass
class SOPStep:
    """A single step in a Standard Operating Procedure."""
    step_number: int
    description: str
    expected_outcome: str
    completed: bool = False
    skipped: bool = False


@dataclass
class Interjection:
    """A smart AI interjection during an incident."""
    message: str
    evidence: list[str]
    similar_incident_ref: Optional[str]
    confidence: float
    suggested_command: Optional[str]
    expected_outcome: Optional[str]
    priority: str  # "critical", "high", "medium"
    timestamp: float = field(default_factory=time.time)


@dataclass
class IncidentContext:
    """Running context for an active incident."""
    incident_id: str
    service: str
    severity: str
    start_time: float
    slack_messages: list[str] = field(default_factory=list)
    executed_steps: list[str] = field(default_factory=list)
    current_metrics: dict = field(default_factory=dict)
    deployment_version: Optional[str] = None
    last_interjection_time: float = 0.0
    interjection_count: int = 0


# Standard Operating Procedures by incident category
SOPS = {
    "latency": [
        SOPStep(1, "Check service error rate and latency metrics", "Baseline established"),
        SOPStep(2, "Review recent deployments in last 2 hours", "Deployment correlation identified"),
        SOPStep(3, "Check database connection pool and slow query log", "DB health confirmed"),
        SOPStep(4, "Verify downstream service health", "Dependencies healthy"),
        SOPStep(5, "Check Redis/cache hit rate", "Cache performance verified"),
        SOPStep(6, "Review CPU and memory utilization", "Resource usage normal"),
        SOPStep(7, "Check Kubernetes pod events and restarts", "Pod health confirmed"),
    ],
    "error_rate": [
        SOPStep(1, "Identify error type and HTTP status codes", "Error classification complete"),
        SOPStep(2, "Check application logs for stack traces", "Error patterns identified"),
        SOPStep(3, "Verify recent deployments", "Deployment impact assessed"),
        SOPStep(4, "Check downstream dependency health", "Dependencies verified"),
        SOPStep(5, "Review circuit breaker state", "Circuit breaker status confirmed"),
        SOPStep(6, "Consider rollback if deployment-related", "Rollback decision made"),
    ],
    "memory": [
        SOPStep(1, "Check memory usage trend over last 24h", "Memory trend established"),
        SOPStep(2, "Review pod restart history", "Restart pattern identified"),
        SOPStep(3, "Check for memory leak indicators in logs", "Leak indicators reviewed"),
        SOPStep(4, "Review recent code changes for memory management", "Code changes assessed"),
        SOPStep(5, "Consider pod restart as temporary mitigation", "Restart decision made"),
        SOPStep(6, "Capture heap dump for analysis", "Heap dump captured"),
    ],
    "database": [
        SOPStep(1, "Check database CPU and connection count", "DB resource usage confirmed"),
        SOPStep(2, "Identify slow queries from slow query log", "Slow queries identified"),
        SOPStep(3, "Check for lock contention and deadlocks", "Lock status verified"),
        SOPStep(4, "Review connection pool configuration", "Pool config verified"),
        SOPStep(5, "Check index usage with EXPLAIN", "Query plans reviewed"),
        SOPStep(6, "Consider read replica offloading", "Read scaling assessed"),
    ],
}


class IncidentCopilotAgent:
    """
    Real-time incident copilot that watches incident activity and
    provides smart, confidence-gated interjections.
    """

    def __init__(self):
        self.active_incidents: dict[str, IncidentContext] = {}

    def start_incident(
        self,
        incident_id: str,
        service: str,
        severity: str,
        initial_description: str,
    ) -> IncidentContext:
        """Initialize tracking for a new incident."""
        context = IncidentContext(
            incident_id=incident_id,
            service=service,
            severity=severity,
            start_time=time.time(),
        )
        self.active_incidents[incident_id] = context
        logger.info("[Copilot] Started tracking incident %s on %s", incident_id, service)
        return context

    def process_update(
        self,
        incident_id: str,
        update_type: str,  # "slack_message", "metric_update", "action_taken"
        content: str,
        metrics: Optional[dict] = None,
    ) -> Optional[Interjection]:
        """
        Process an incident update and potentially generate an interjection.
        Respects the confidence gate and rate limiting (max 1 per 5 minutes).
        """
        context = self.active_incidents.get(incident_id)
        if not context:
            logger.warning("[Copilot] Unknown incident: %s", incident_id)
            return None

        # Update context
        if update_type == "slack_message":
            context.slack_messages.append(content)
        elif update_type == "action_taken":
            context.executed_steps.append(content)
        if metrics:
            context.current_metrics.update(metrics)

        # Rate limiting: max 1 interjection per 5 minutes
        elapsed = time.time() - context.last_interjection_time
        if elapsed < config.guardrails.max_interjection_interval_seconds:
            logger.debug(
                "[Copilot] Rate limited: %.0fs until next interjection allowed", 
                config.guardrails.max_interjection_interval_seconds - elapsed
            )
            return None

        # Generate interjection
        interjection = self._analyze_and_interject(context)
        if interjection:
            context.last_interjection_time = time.time()
            context.interjection_count += 1
            logger.info(
                "[Copilot] Interjecting on incident %s (confidence=%.2f): %s",
                incident_id,
                interjection.confidence,
                interjection.message[:100],
            )

        return interjection

    def _analyze_and_interject(self, context: IncidentContext) -> Optional[Interjection]:
        """
        Analyze current incident state and generate a high-confidence interjection.
        Only interjects if confidence >= threshold (default 0.70).
        """
        # Determine incident category for SOP matching
        category = self._classify_incident_category(context)
        sop = SOPS.get(category, SOPS["latency"])

        # Detect missing SOP steps
        missing_steps = self._detect_missing_sop_steps(context, sop)

        # Retrieve similar historical incidents
        query = f"{context.service} {' '.join(context.slack_messages[-5:])}"
        similar = []
        try:
            similar = vector_store.search_similar_incidents(query=query, top_k=3)
        except Exception as e:
            logger.debug("[Copilot] Vector search failed: %s", e)

        # Build analysis prompt
        recent_messages = "\n".join(context.slack_messages[-10:])
        executed = "\n".join(f"- {s}" for s in context.executed_steps[-10:])
        missing = "\n".join(f"- Step {s.step_number}: {s.description}" for s in missing_steps[:3])
        historical = "\n".join(
            f"- {r.incident.incident_id} ({r.similarity_score:.0%}): {r.incident.root_cause}"
            for r in similar[:2]
        )

        prompt = (
            f"You are an AI incident copilot analyzing an active incident.\n\n"
            f"**Incident**: {context.incident_id} | **Service**: {context.service} | "
            f"**Severity**: {context.severity}\n\n"
            f"**Recent Slack Messages**:\n{recent_messages or 'None yet'}\n\n"
            f"**Actions Taken So Far**:\n{executed or 'None yet'}\n\n"
            f"**Missing SOP Steps**:\n{missing or 'None detected'}\n\n"
            f"**Similar Historical Incidents**:\n{historical or 'None found'}\n\n"
            f"**Current Metrics**: {context.current_metrics}\n\n"
            f"Should you interject with a recommendation? Only interject if you have "
            f"high-confidence (>=0.70) insight that engineers may have missed.\n\n"
            f"Respond in JSON:\n"
            f'{{\n'
            f'  "should_interject": true/false,\n'
            f'  "message": "...",\n'
            f'  "evidence": ["..."],\n'
            f'  "similar_incident_ref": "INC-XXXX or null",\n'
            f'  "confidence": 0.0-1.0,\n'
            f'  "suggested_command": "kubectl ... or null",\n'
            f'  "expected_outcome": "...",\n'
            f'  "priority": "critical/high/medium"\n'
            f'}}'
        )

        try:
            response = model_router.route(
                TaskType.CHATOPS_RESPONSE,
                prompt=prompt,
                max_tokens=1024,
                temperature=0.1,
            )

            import json, re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                return None

            data = json.loads(json_match.group())
            if not data.get("should_interject"):
                return None

            confidence = float(data.get("confidence", 0.0))
            if confidence < config.guardrails.confidence_threshold:
                logger.debug(
                    "[Copilot] Suppressing interjection: confidence %.2f below threshold %.2f",
                    confidence,
                    config.guardrails.confidence_threshold,
                )
                return None

            return Interjection(
                message=data.get("message", ""),
                evidence=data.get("evidence", []),
                similar_incident_ref=data.get("similar_incident_ref"),
                confidence=confidence,
                suggested_command=data.get("suggested_command"),
                expected_outcome=data.get("expected_outcome"),
                priority=data.get("priority", "medium"),
            )

        except Exception as e:
            logger.error("[Copilot] Interjection analysis failed: %s", e)
            return None

    def _classify_incident_category(self, context: IncidentContext) -> str:
        """Classify incident into a category for SOP matching."""
        all_text = " ".join(context.slack_messages).lower()
        metrics = context.current_metrics

        if metrics.get("latency_p99_ms", 0) > 1000 or "latency" in all_text or "slow" in all_text:
            return "latency"
        if metrics.get("error_rate_percent", 0) > 2 or "error" in all_text or "500" in all_text:
            return "error_rate"
        if metrics.get("memory_mb", 0) > 1500 or "memory" in all_text or "oom" in all_text:
            return "memory"
        if "database" in all_text or "db" in all_text or "query" in all_text or "sql" in all_text:
            return "database"
        return "latency"  # default

    def _detect_missing_sop_steps(
        self, context: IncidentContext, sop: list[SOPStep]
    ) -> list[SOPStep]:
        """Detect SOP steps that haven't been executed yet."""
        executed_text = " ".join(context.executed_steps + context.slack_messages).lower()
        missing = []
        for step in sop:
            # Simple keyword matching - in production use semantic similarity
            keywords = step.description.lower().split()
            key_terms = [w for w in keywords if len(w) > 4]
            if not any(term in executed_text for term in key_terms[:3]):
                missing.append(step)
        return missing

    def generate_live_summary(self, incident_id: str) -> str:
        """Generate a real-time summary of the incident for status updates."""
        context = self.active_incidents.get(incident_id)
        if not context:
            return f"No active incident found: {incident_id}"

        elapsed_minutes = (time.time() - context.start_time) / 60
        recent_messages = "\n".join(context.slack_messages[-15:])
        actions = "\n".join(f"- {s}" for s in context.executed_steps)

        prompt = (
            f"Generate a concise incident status update (3-4 sentences) for:\n"
            f"Incident: {incident_id} | Service: {context.service} | "
            f"Duration: {elapsed_minutes:.0f} minutes\n\n"
            f"Recent activity:\n{recent_messages}\n\n"
            f"Actions taken:\n{actions or 'None yet'}\n\n"
            f"Write a clear status update suitable for a status page or Slack."
        )

        try:
            return model_router.route(
                TaskType.STREAMING_SUMMARY,
                prompt=prompt,
                max_tokens=512,
                temperature=0.2,
            )
        except Exception as e:
            logger.error("[Copilot] Summary generation failed: %s", e)
            return f"Incident {incident_id} on {context.service} - investigation in progress."

    def generate_postmortem(self, incident_id: str, rca_report) -> str:
        """Auto-generate a postmortem document after incident resolution."""
        context = self.active_incidents.get(incident_id)
        if not context:
            return "Incident context not found."

        duration_minutes = (time.time() - context.start_time) / 60
        actions = "\n".join(f"- {s}" for s in context.executed_steps)

        prompt = (
            f"Generate a professional incident postmortem document.\n\n"
            f"**Incident ID**: {incident_id}\n"
            f"**Service**: {context.service}\n"
            f"**Severity**: {context.severity}\n"
            f"**Duration**: {duration_minutes:.0f} minutes\n"
            f"**Root Cause**: {rca_report.top_hypothesis.hypothesis if rca_report else 'TBD'}\n\n"
            f"**Actions Taken**:\n{actions or 'Not recorded'}\n\n"
            f"Generate a postmortem with sections:\n"
            f"1. Executive Summary\n"
            f"2. Timeline\n"
            f"3. Root Cause\n"
            f"4. Impact\n"
            f"5. Mitigation Steps\n"
            f"6. Prevention Recommendations\n"
            f"7. Action Items (with owners and due dates)"
        )

        try:
            return model_router.route(
                TaskType.DEEP_REASONING,
                prompt=prompt,
                max_tokens=3000,
                temperature=0.2,
            )
        except Exception as e:
            logger.error("[Copilot] Postmortem generation failed: %s", e)
            return f"Postmortem generation failed for {incident_id}. Manual postmortem required."

    def close_incident(self, incident_id: str) -> dict:
        """Close an incident and return summary statistics."""
        context = self.active_incidents.pop(incident_id, None)
        if not context:
            return {"error": f"Incident {incident_id} not found"}

        duration_minutes = (time.time() - context.start_time) / 60
        return {
            "incident_id": incident_id,
            "service": context.service,
            "severity": context.severity,
            "duration_minutes": round(duration_minutes, 1),
            "total_interjections": context.interjection_count,
            "actions_taken": len(context.executed_steps),
            "slack_messages_processed": len(context.slack_messages),
        }


# Singleton
incident_copilot = IncidentCopilotAgent()
