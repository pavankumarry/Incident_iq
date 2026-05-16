"""
IncidentIQ - Observability Agent
Monitors telemetry, logs, traces, and metrics. Detects anomalies using
statistical analysis and LLM reasoning. Triggers incident workflows.
"""
import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from backend.bedrock.model_router import TaskType, model_router
from backend.config import config

logger = logging.getLogger(__name__)


class Severity(str, Enum):
    P0 = "p0"  # Critical - immediate response
    P1 = "p1"  # High - response within 15 min
    P2 = "p2"  # Medium - response within 1 hour
    P3 = "p3"  # Low - response within 24 hours


class AnomalyType(str, Enum):
    LATENCY_SPIKE = "latency_spike"
    ERROR_RATE_INCREASE = "error_rate_increase"
    CPU_SPIKE = "cpu_spike"
    MEMORY_SPIKE = "memory_spike"
    THROUGHPUT_DROP = "throughput_drop"
    DATABASE_SLOW_QUERY = "database_slow_query"
    KUBERNETES_EVENT = "kubernetes_event"
    DEPLOYMENT_REGRESSION = "deployment_regression"
    DEPENDENCY_FAILURE = "dependency_failure"
    CUSTOM = "custom"


@dataclass
class TelemetrySnapshot:
    """Represents a point-in-time telemetry snapshot from a service."""
    service: str
    timestamp: str
    latency_p99_ms: Optional[float] = None
    latency_p50_ms: Optional[float] = None
    error_rate_percent: Optional[float] = None
    cpu_percent: Optional[float] = None
    memory_mb: Optional[float] = None
    requests_per_second: Optional[float] = None
    active_db_connections: Optional[int] = None
    pod_restarts: Optional[int] = None
    deployment_version: Optional[str] = None
    raw_logs: Optional[list[str]] = field(default_factory=list)
    custom_metrics: dict = field(default_factory=dict)


@dataclass
class AnomalyReport:
    """Structured anomaly detection result."""
    anomaly_id: str
    anomaly_type: AnomalyType
    severity: Severity
    service: str
    timestamp: str
    description: str
    evidence: list[str]
    affected_metrics: dict
    confidence: float
    recommended_action: str
    triggered_incident: bool = False


class ObservabilityAgent:
    """
    Monitors telemetry and detects anomalies.
    Uses statistical thresholds for fast detection and LLM for contextual analysis.
    """

    # Statistical thresholds for fast anomaly detection
    THRESHOLDS = {
        "latency_p99_ms": {"warning": 500, "critical": 2000},
        "error_rate_percent": {"warning": 1.0, "critical": 5.0},
        "cpu_percent": {"warning": 75, "critical": 90},
        "memory_mb": {"warning": 1500, "critical": 1900},
        "pod_restarts": {"warning": 2, "critical": 5},
    }

    def analyze_telemetry(self, snapshot: TelemetrySnapshot) -> list[AnomalyReport]:
        """
        Analyze a telemetry snapshot for anomalies.
        Returns list of detected anomaly reports.
        """
        anomalies = []

        # Fast statistical checks
        anomalies.extend(self._check_thresholds(snapshot))

        # LLM-based contextual analysis for log patterns
        if snapshot.raw_logs:
            log_anomaly = self._analyze_logs_with_llm(snapshot)
            if log_anomaly:
                anomalies.append(log_anomaly)

        # Log all detected anomalies
        for anomaly in anomalies:
            logger.warning(
                "[ObservabilityAgent] Anomaly detected: %s on %s (severity=%s, confidence=%.2f)",
                anomaly.anomaly_type,
                anomaly.service,
                anomaly.severity,
                anomaly.confidence,
            )

        return anomalies

    def _check_thresholds(self, snapshot: TelemetrySnapshot) -> list[AnomalyReport]:
        """Statistical threshold-based anomaly detection."""
        anomalies = []
        ts = snapshot.timestamp or datetime.utcnow().isoformat()

        checks = [
            ("latency_p99_ms", AnomalyType.LATENCY_SPIKE, snapshot.latency_p99_ms),
            ("error_rate_percent", AnomalyType.ERROR_RATE_INCREASE, snapshot.error_rate_percent),
            ("cpu_percent", AnomalyType.CPU_SPIKE, snapshot.cpu_percent),
            ("memory_mb", AnomalyType.MEMORY_SPIKE, snapshot.memory_mb),
            ("pod_restarts", AnomalyType.KUBERNETES_EVENT, snapshot.pod_restarts),
        ]

        for metric_name, anomaly_type, value in checks:
            if value is None:
                continue
            thresholds = self.THRESHOLDS.get(metric_name, {})
            critical = thresholds.get("critical")
            warning = thresholds.get("warning")

            if critical and value >= critical:
                severity = Severity.P1
                confidence = 0.92
            elif warning and value >= warning:
                severity = Severity.P2
                confidence = 0.80
            else:
                continue

            anomalies.append(
                AnomalyReport(
                    anomaly_id=f"{snapshot.service}-{anomaly_type}-{ts}",
                    anomaly_type=anomaly_type,
                    severity=severity,
                    service=snapshot.service,
                    timestamp=ts,
                    description=f"{metric_name} is {value} (threshold: {critical or warning})",
                    evidence=[f"{metric_name}={value}"],
                    affected_metrics={metric_name: value},
                    confidence=confidence,
                    recommended_action=self._get_recommended_action(anomaly_type, severity),
                )
            )

        return anomalies

    def _analyze_logs_with_llm(self, snapshot: TelemetrySnapshot) -> Optional[AnomalyReport]:
        """Use Nova Lite for fast log pattern classification."""
        if not snapshot.raw_logs:
            return None

        log_sample = "\n".join(snapshot.raw_logs[-50:])  # Last 50 log lines
        prompt = (
            f"Analyze these logs from service '{snapshot.service}' for anomalies.\n"
            f"Respond in JSON format:\n"
            f'{{"anomaly_detected": true/false, "anomaly_type": "...", "severity": "p0/p1/p2/p3", '
            f'"description": "...", "confidence": 0.0-1.0}}\n\n'
            f"Logs:\n{log_sample}"
        )

        try:
            response = model_router.route(
                TaskType.ALERT_CLASSIFICATION,
                prompt=prompt,
                max_tokens=512,
                temperature=0.0,
            )

            import json
            import re
            # Extract JSON from response
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if not json_match:
                return None

            result = json.loads(json_match.group())
            if not result.get("anomaly_detected"):
                return None

            confidence = float(result.get("confidence", 0.5))
            if confidence < config.guardrails.confidence_threshold:
                logger.debug(
                    "Log anomaly confidence %.2f below threshold, suppressing.", confidence
                )
                return None

            return AnomalyReport(
                anomaly_id=f"{snapshot.service}-log-{snapshot.timestamp}",
                anomaly_type=AnomalyType.CUSTOM,
                severity=Severity(result.get("severity", "p2")),
                service=snapshot.service,
                timestamp=snapshot.timestamp,
                description=result.get("description", "Log anomaly detected"),
                evidence=snapshot.raw_logs[-5:],
                affected_metrics={"log_analysis": True},
                confidence=confidence,
                recommended_action="Investigate log patterns and correlate with metrics.",
            )
        except Exception as e:
            logger.error("Log analysis failed: %s", e)
            return None

    def _get_recommended_action(self, anomaly_type: AnomalyType, severity: Severity) -> str:
        actions = {
            AnomalyType.LATENCY_SPIKE: "Check database query performance, downstream dependencies, and recent deployments.",
            AnomalyType.ERROR_RATE_INCREASE: "Review error logs, check deployment history, verify downstream service health.",
            AnomalyType.CPU_SPIKE: "Profile CPU usage, check for infinite loops or inefficient algorithms.",
            AnomalyType.MEMORY_SPIKE: "Check for memory leaks, review heap dumps, consider pod restart.",
            AnomalyType.KUBERNETES_EVENT: "Review pod events, check resource limits, inspect node health.",
            AnomalyType.DATABASE_SLOW_QUERY: "Run EXPLAIN on slow queries, check index usage, review connection pool.",
            AnomalyType.DEPLOYMENT_REGRESSION: "Compare metrics before/after deployment, consider rollback.",
            AnomalyType.DEPENDENCY_FAILURE: "Check dependency health endpoints, review circuit breaker state.",
        }
        return actions.get(anomaly_type, "Investigate the anomaly and correlate with recent changes.")

    def generate_anomaly_report_summary(self, anomalies: list[AnomalyReport]) -> str:
        """Generate a human-readable summary of detected anomalies."""
        if not anomalies:
            return "No anomalies detected."

        lines = [f"## Anomaly Report — {len(anomalies)} issue(s) detected\n"]
        for a in sorted(anomalies, key=lambda x: x.severity):
            lines.append(
                f"**[{a.severity.upper()}]** {a.anomaly_type} on `{a.service}`\n"
                f"- {a.description}\n"
                f"- Confidence: {a.confidence:.0%}\n"
                f"- Action: {a.recommended_action}\n"
            )
        return "\n".join(lines)


# Singleton
observability_agent = ObservabilityAgent()
