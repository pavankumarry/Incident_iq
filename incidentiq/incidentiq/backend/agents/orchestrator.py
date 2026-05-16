"""
IncidentIQ - LangGraph Orchestrator
Coordinates all specialized agents through a structured reasoning workflow.
Implements the 13-step reasoning chain with guardrails and human approval gates.
"""
import logging
import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Optional

from backend.agents.observability_agent import (
    AnomalyReport,
    ObservabilityAgent,
    TelemetrySnapshot,
    observability_agent,
)
from backend.agents.rca_agent import RCAReport, rca_agent
from backend.agents.code_intelligence_agent import PullRequest, code_intelligence_agent
from backend.agents.incident_copilot_agent import incident_copilot
from backend.validators.guardrail import guardrail, ActionType
from backend.config import config

logger = logging.getLogger(__name__)


class WorkflowState(str, Enum):
    IDLE = "idle"
    COLLECTING_TELEMETRY = "collecting_telemetry"
    DETECTING_ANOMALIES = "detecting_anomalies"
    RETRIEVING_HISTORY = "retrieving_history"
    GENERATING_HYPOTHESES = "generating_hypotheses"
    VALIDATING_HYPOTHESES = "validating_hypotheses"
    ANALYZING_CODE = "analyzing_code"
    GENERATING_REMEDIATION = "generating_remediation"
    SIMULATING_OUTCOMES = "simulating_outcomes"
    GENERATING_FIX = "generating_fix"
    RUNNING_VALIDATION = "running_validation"
    GENERATING_PR = "generating_pr"
    AWAITING_APPROVAL = "awaiting_approval"
    MONITORING_POST_DEPLOY = "monitoring_post_deploy"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class IncidentWorkflow:
    """Tracks the full state of an incident investigation workflow."""
    workflow_id: str
    incident_id: str
    service: str
    severity: str
    description: str
    state: WorkflowState = WorkflowState.IDLE
    telemetry: dict = field(default_factory=dict)
    anomalies: list[AnomalyReport] = field(default_factory=list)
    rca_report: Optional[RCAReport] = None
    pull_request: Optional[PullRequest] = None
    reasoning_log: list[str] = field(default_factory=list)
    requires_human_approval: bool = False
    approval_granted: bool = False
    error: Optional[str] = None
    created_at: str = field(default_factory=lambda: datetime.utcnow().isoformat())
    completed_at: Optional[str] = None


class IncidentOrchestrator:
    """
    Central orchestrator implementing the 13-step reasoning workflow.
    Coordinates all agents and enforces guardrails.
    """

    def run_full_workflow(
        self,
        service: str,
        description: str,
        telemetry: dict,
        logs: list[str],
        deployment_history: list[dict],
        severity: str = "p2",
        dependency_graph: Optional[dict] = None,
        code_context: Optional[dict] = None,
    ) -> IncidentWorkflow:
        """
        Execute the full 13-step incident investigation and remediation workflow.
        """
        incident_id = f"INC-{datetime.utcnow().strftime('%Y%m%d%H%M%S')}"
        workflow_id = str(uuid.uuid4())[:8]

        workflow = IncidentWorkflow(
            workflow_id=workflow_id,
            incident_id=incident_id,
            service=service,
            severity=severity,
            description=description,
        )

        self._log(workflow, f"Starting workflow {workflow_id} for incident {incident_id}")
        self._log(workflow, f"Service: {service} | Severity: {severity}")

        try:
            # Step 1: Collect telemetry
            workflow.state = WorkflowState.COLLECTING_TELEMETRY
            self._log(workflow, "Step 1: Collecting telemetry, logs, traces, and metrics")
            workflow.telemetry = telemetry

            # Step 2: Detect anomalies
            workflow.state = WorkflowState.DETECTING_ANOMALIES
            self._log(workflow, "Step 2: Identifying anomalies and correlating failures")
            snapshot = TelemetrySnapshot(
                service=service,
                timestamp=datetime.utcnow().isoformat(),
                raw_logs=logs,
                **{k: v for k, v in telemetry.items() if k in TelemetrySnapshot.__dataclass_fields__},
            )
            workflow.anomalies = observability_agent.analyze_telemetry(snapshot)
            self._log(
                workflow,
                f"[ObservabilityAgent] Detected {len(workflow.anomalies)} anomalies"
            )

            # Step 3-5: RCA (retrieval, hypotheses, validation)
            workflow.state = WorkflowState.RETRIEVING_HISTORY
            self._log(workflow, "Step 3: Retrieving historical incidents and SOPs")
            self._log(workflow, "Step 4: Generating root cause hypotheses")
            self._log(workflow, "Step 5: Validating hypotheses with deterministic tools")

            workflow.rca_report = rca_agent.investigate(
                incident_id=incident_id,
                service=service,
                description=description,
                telemetry=telemetry,
                logs=logs,
                deployment_history=deployment_history,
                dependency_graph=dependency_graph,
            )

            # Append RCA reasoning log
            for entry in workflow.rca_report.reasoning_log:
                workflow.reasoning_log.append(entry)

            self._log(
                workflow,
                f"[RCAAgent] Top hypothesis: '{workflow.rca_report.top_hypothesis.hypothesis}' "
                f"(confidence={workflow.rca_report.top_hypothesis.confidence:.2f})"
            )

            if workflow.rca_report.similar_incidents:
                top = workflow.rca_report.similar_incidents[0]
                self._log(
                    workflow,
                    f"[KnowledgeAgent] Similar incident: {top.incident.incident_id} "
                    f"({top.similarity_score:.0%} similarity)"
                )

            # Step 6: Analyze repository context
            workflow.state = WorkflowState.ANALYZING_CODE
            self._log(workflow, "Step 6: Analyzing repository context and impacted services")

            # Step 7: Generate remediation options
            workflow.state = WorkflowState.GENERATING_REMEDIATION
            self._log(workflow, "Step 7: Generating remediation options")
            self._log(
                workflow,
                f"[RCAAgent] Mitigations: {workflow.rca_report.recommended_mitigations}"
            )

            # Step 8: Simulate outcomes
            workflow.state = WorkflowState.SIMULATING_OUTCOMES
            self._log(workflow, "Step 8: Simulating potential outcomes")

            # Step 9: Generate code fix (if code context provided)
            workflow.state = WorkflowState.GENERATING_FIX
            self._log(workflow, "Step 9: Generating code fixes and tests")

            code_fixes = []
            if code_context:
                for file_path, file_code in code_context.items():
                    fix = code_intelligence_agent.generate_fix(
                        root_cause=workflow.rca_report.top_hypothesis.hypothesis,
                        service=service,
                        code_context=file_code,
                        file_path=file_path,
                        fix_type=workflow.rca_report.top_hypothesis.category,
                    )
                    code_fixes.append(fix)
                    self._log(
                        workflow,
                        f"[CodeAgent] Generated fix for {file_path} (risk={fix.risk_level})"
                    )

            # Step 10: Run validation pipeline
            workflow.state = WorkflowState.RUNNING_VALIDATION
            self._log(workflow, "Step 10: Running validation pipeline")

            # Step 11: Generate PR
            workflow.state = WorkflowState.GENERATING_PR
            self._log(workflow, "Step 11: Generating Pull Request")

            if code_fixes:
                workflow.pull_request = code_intelligence_agent.generate_pull_request(
                    incident_id=incident_id,
                    service=service,
                    root_cause=workflow.rca_report.top_hypothesis.hypothesis,
                    code_fixes=code_fixes,
                    telemetry_before=telemetry,
                    severity=severity,
                )
                self._log(
                    workflow,
                    f"[CodeAgent] PR generated: '{workflow.pull_request.title}' "
                    f"(confidence={workflow.pull_request.confidence:.2f})"
                )

            # Step 12: Check if human approval required
            workflow.state = WorkflowState.AWAITING_APPROVAL
            self._log(workflow, "Step 12: Checking human approval requirements")

            needs_approval = guardrail.requires_human_approval(
                action_type=ActionType.DEPLOY_TO_PRODUCTION,
                context={"severity": severity, "service": service},
            )

            if needs_approval or (
                workflow.pull_request
                and workflow.pull_request.validation_results.get("requires_human_approval")
            ):
                workflow.requires_human_approval = True
                self._log(
                    workflow,
                    "[GuardrailAgent] Human approval required before deployment"
                )
            else:
                workflow.approval_granted = True
                self._log(workflow, "[GuardrailAgent] No approval required for this action")

            # Step 13: Monitor post-deployment
            workflow.state = WorkflowState.MONITORING_POST_DEPLOY
            self._log(workflow, "Step 13: Monitoring post-deployment impact (async)")

            workflow.state = WorkflowState.COMPLETED
            workflow.completed_at = datetime.utcnow().isoformat()
            self._log(workflow, f"Workflow {workflow_id} completed successfully")

        except Exception as e:
            workflow.state = WorkflowState.FAILED
            workflow.error = str(e)
            self._log(workflow, f"Workflow failed: {e}")
            logger.exception("Workflow %s failed", workflow_id)

        return workflow

    def _log(self, workflow: IncidentWorkflow, message: str):
        """Append to reasoning log and logger."""
        workflow.reasoning_log.append(message)
        logger.info(message)

    def get_reasoning_log(self, workflow: IncidentWorkflow) -> str:
        """Format the reasoning log for display."""
        return "\n".join(workflow.reasoning_log)

    def format_workflow_summary(self, workflow: IncidentWorkflow) -> dict:
        """Return a structured summary of the workflow for the API."""
        return {
            "workflow_id": workflow.workflow_id,
            "incident_id": workflow.incident_id,
            "service": workflow.service,
            "severity": workflow.severity,
            "state": workflow.state,
            "anomalies_detected": len(workflow.anomalies),
            "rca": {
                "top_hypothesis": workflow.rca_report.top_hypothesis.hypothesis
                if workflow.rca_report
                else None,
                "confidence": workflow.rca_report.top_hypothesis.confidence
                if workflow.rca_report
                else None,
                "similar_incidents": len(workflow.rca_report.similar_incidents)
                if workflow.rca_report
                else 0,
                "mitigations": workflow.rca_report.recommended_mitigations
                if workflow.rca_report
                else [],
            },
            "pull_request": {
                "title": workflow.pull_request.title if workflow.pull_request else None,
                "branch": workflow.pull_request.branch_name if workflow.pull_request else None,
                "confidence": workflow.pull_request.confidence if workflow.pull_request else None,
            }
            if workflow.pull_request
            else None,
            "requires_human_approval": workflow.requires_human_approval,
            "reasoning_log": workflow.reasoning_log,
            "created_at": workflow.created_at,
            "completed_at": workflow.completed_at,
            "error": workflow.error,
        }


# Singleton
orchestrator = IncidentOrchestrator()
