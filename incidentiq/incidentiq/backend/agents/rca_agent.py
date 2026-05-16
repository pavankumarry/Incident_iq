"""
IncidentIQ - Root Cause Analysis Agent
Investigates failures autonomously using temporal reasoning, dependency graph
traversal, causal inference, and historical incident comparison.
"""
import logging
from dataclasses import dataclass, field
from typing import Optional

from backend.bedrock.model_router import TaskType, model_router
from backend.memory.vector_store import RetrievalResult, vector_store
from backend.config import config

logger = logging.getLogger(__name__)


@dataclass
class RCAHypothesis:
    """A single root cause hypothesis with supporting evidence."""
    hypothesis: str
    confidence: float
    evidence: list[str]
    supporting_incidents: list[str]  # Historical incident IDs
    category: str  # e.g., "database", "deployment", "dependency", "code"


@dataclass
class RCAReport:
    """Complete root cause analysis report."""
    incident_id: str
    service: str
    summary: str
    hypotheses: list[RCAHypothesis]
    top_hypothesis: RCAHypothesis
    timeline: list[dict]
    affected_services: list[str]
    deployment_correlation: Optional[str]
    similar_incidents: list[RetrievalResult]
    recommended_mitigations: list[str]
    prevention_recommendations: list[str]
    confidence: float
    reasoning_log: list[str]


class RCAAgent:
    """
    Autonomous Root Cause Analysis Agent.
    Correlates logs, traces, deployments, and historical incidents
    to generate ranked root cause hypotheses.
    """

    def investigate(
        self,
        incident_id: str,
        service: str,
        description: str,
        telemetry: dict,
        logs: list[str],
        deployment_history: list[dict],
        dependency_graph: Optional[dict] = None,
    ) -> RCAReport:
        """
        Full autonomous RCA investigation.
        Returns a structured RCA report with ranked hypotheses.
        """
        reasoning_log = []
        reasoning_log.append(
            f"[RCAAgent] Starting investigation for incident {incident_id} on {service}"
        )

        # Step 1: Retrieve similar historical incidents
        reasoning_log.append("[RCAAgent] Retrieving similar historical incidents via RAG...")
        similar_incidents = self._retrieve_similar_incidents(description, service)
        if similar_incidents:
            top_match = similar_incidents[0]
            reasoning_log.append(
                f"[RCAAgent] Found {len(similar_incidents)} similar incidents. "
                f"Top match: {top_match.incident.incident_id} "
                f"({top_match.similarity_score:.0%} similarity)"
            )
        else:
            reasoning_log.append("[RCAAgent] No similar historical incidents found.")

        # Step 2: Correlate with deployment history
        reasoning_log.append("[RCAAgent] Correlating with deployment history...")
        deployment_correlation = self._correlate_deployments(
            description, deployment_history, telemetry
        )
        if deployment_correlation:
            reasoning_log.append(f"[RCAAgent] Deployment correlation: {deployment_correlation}")

        # Step 3: Generate hypotheses using Claude Sonnet
        reasoning_log.append("[RCAAgent] Generating root cause hypotheses with Claude Sonnet...")
        hypotheses = self._generate_hypotheses(
            incident_id=incident_id,
            service=service,
            description=description,
            telemetry=telemetry,
            logs=logs,
            similar_incidents=similar_incidents,
            deployment_correlation=deployment_correlation,
            dependency_graph=dependency_graph,
        )
        reasoning_log.append(
            f"[RCAAgent] Generated {len(hypotheses)} hypotheses. "
            f"Top: '{hypotheses[0].hypothesis}' (confidence={hypotheses[0].confidence:.2f})"
        )

        # Step 4: Validate top hypothesis with Llama
        reasoning_log.append("[RCAAgent] Validating top hypothesis with Llama 3.1...")
        validated_hypothesis = self._validate_hypothesis(hypotheses[0], description, telemetry)
        reasoning_log.append(
            f"[RCAAgent] Validation complete. Final confidence: {validated_hypothesis.confidence:.2f}"
        )

        # Step 5: Generate mitigations and prevention recommendations
        reasoning_log.append("[RCAAgent] Generating mitigation recommendations...")
        mitigations, prevention = self._generate_recommendations(
            validated_hypothesis, similar_incidents
        )

        # Step 6: Build timeline
        timeline = self._build_timeline(telemetry, deployment_history, logs)

        # Determine affected services from dependency graph
        affected_services = self._identify_affected_services(service, dependency_graph)

        report = RCAReport(
            incident_id=incident_id,
            service=service,
            summary=self._generate_summary(validated_hypothesis, service, description),
            hypotheses=hypotheses,
            top_hypothesis=validated_hypothesis,
            timeline=timeline,
            affected_services=affected_services,
            deployment_correlation=deployment_correlation,
            similar_incidents=similar_incidents,
            recommended_mitigations=mitigations,
            prevention_recommendations=prevention,
            confidence=validated_hypothesis.confidence,
            reasoning_log=reasoning_log,
        )

        logger.info(
            "[RCAAgent] Investigation complete for %s. Top hypothesis confidence: %.2f",
            incident_id,
            report.confidence,
        )
        return report

    def _retrieve_similar_incidents(
        self, description: str, service: str
    ) -> list[RetrievalResult]:
        """Retrieve semantically similar historical incidents."""
        try:
            return vector_store.search_similar_incidents(
                query=description,
                top_k=5,
                service_filter=None,  # Search across all services
            )
        except Exception as e:
            logger.error("Vector store retrieval failed: %s", e)
            return []

    def _correlate_deployments(
        self,
        description: str,
        deployment_history: list[dict],
        telemetry: dict,
    ) -> Optional[str]:
        """Check if a recent deployment correlates with the incident."""
        if not deployment_history:
            return None

        recent = deployment_history[-3:] if len(deployment_history) >= 3 else deployment_history
        deploy_summary = "\n".join(
            f"- {d.get('version', 'unknown')} deployed at {d.get('timestamp', 'unknown')} "
            f"by {d.get('author', 'unknown')}: {d.get('description', '')}"
            for d in recent
        )

        prompt = (
            f"Given this incident: {description}\n\n"
            f"And these recent deployments:\n{deploy_summary}\n\n"
            f"Is there a likely correlation between any deployment and the incident? "
            f"Respond with: CORRELATED: <version> - <reason>, or NOT_CORRELATED."
        )

        try:
            response = model_router.route(
                TaskType.ALERT_CLASSIFICATION,
                prompt=prompt,
                max_tokens=256,
                temperature=0.0,
            )
            if "CORRELATED:" in response:
                return response.strip()
            return None
        except Exception as e:
            logger.error("Deployment correlation failed: %s", e)
            return None

    def _generate_hypotheses(
        self,
        incident_id: str,
        service: str,
        description: str,
        telemetry: dict,
        logs: list[str],
        similar_incidents: list[RetrievalResult],
        deployment_correlation: Optional[str],
        dependency_graph: Optional[dict],
    ) -> list[RCAHypothesis]:
        """Generate ranked root cause hypotheses using Qwen3 32B."""
        historical_context = vector_store.format_retrieval_context(similar_incidents)
        log_sample = "\n".join(logs[-20:]) if logs else "No logs available."
        telemetry_str = "\n".join(f"  {k}: {v}" for k, v in telemetry.items())

        prompt = (
            f"You are performing root cause analysis for incident {incident_id}.\n\n"
            f"**Service**: {service}\n"
            f"**Incident Description**: {description}\n\n"
            f"**Telemetry**:\n{telemetry_str}\n\n"
            f"**Recent Logs** (last 20 lines):\n{log_sample}\n\n"
            f"**Deployment Correlation**: {deployment_correlation or 'None detected'}\n\n"
            f"{historical_context}\n\n"
            f"Generate 3 ranked root cause hypotheses. For each hypothesis provide:\n"
            f"1. Hypothesis statement\n"
            f"2. Confidence score (0.0-1.0)\n"
            f"3. Supporting evidence from the data above\n"
            f"4. Category (database/deployment/dependency/code/infrastructure/configuration)\n\n"
            f"IMPORTANT: Respond with ONLY a valid JSON array, no other text:\n"
            f'[{{"hypothesis": "...", "confidence": 0.85, "evidence": ["..."], "category": "..."}}]'
        )

        try:
            response = model_router.route(
                TaskType.ROOT_CAUSE_ANALYSIS,
                prompt=prompt,
                system_prompt=(
                    "You are an expert SRE performing root cause analysis. "
                    "Be precise, cite evidence from the provided data, and never speculate "
                    "without supporting evidence. Always include confidence scores."
                ),
                max_tokens=2048,
                temperature=0.1,
            )

            import json, re

            # Try multiple extraction strategies for robustness
            raw_hypotheses = None

            # Strategy 1: clean complete JSON array
            start = response.find('[')
            end = response.rfind(']')
            if start != -1 and end != -1 and end > start:
                try:
                    raw_hypotheses = json.loads(response[start:end+1])
                except json.JSONDecodeError:
                    pass

            # Strategy 2: response was truncated mid-array — close it and parse what we have
            if raw_hypotheses is None and start != -1:
                # Find all complete objects inside the array
                partial = response[start:]
                # Extract individual {...} objects
                objects = re.findall(r'\{[^{}]+\}', partial, re.DOTALL)
                if objects:
                    try:
                        raw_hypotheses = [json.loads(o) for o in objects]
                    except json.JSONDecodeError:
                        pass

            if not raw_hypotheses:
                raise ValueError(f"No parseable JSON in RCA response (len={len(response)})")

            hypotheses = []
            for h in raw_hypotheses[:3]:
                supporting = [
                    r.incident.incident_id
                    for r in similar_incidents
                    if r.similarity_score > 0.75
                ]
                hypotheses.append(
                    RCAHypothesis(
                        hypothesis=h.get("hypothesis", ""),
                        confidence=float(h.get("confidence", 0.5)),
                        evidence=h.get("evidence", []),
                        supporting_incidents=supporting,
                        category=h.get("category", "unknown"),
                    )
                )

            hypotheses.sort(key=lambda x: x.confidence, reverse=True)
            return hypotheses

        except Exception as e:
            logger.error("Hypothesis generation failed: %s", e)
            # Fallback hypothesis
            return [
                RCAHypothesis(
                    hypothesis=f"Unknown root cause for {service} incident. Manual investigation required.",
                    confidence=0.30,
                    evidence=["Automated analysis failed"],
                    supporting_incidents=[],
                    category="unknown",
                )
            ]

    def _validate_hypothesis(
        self,
        hypothesis: RCAHypothesis,
        description: str,
        telemetry: dict,
    ) -> RCAHypothesis:
        """Validate the top hypothesis using Llama 3.1 for consensus."""
        prompt = (
            f"Validate this root cause hypothesis:\n"
            f"Hypothesis: {hypothesis.hypothesis}\n"
            f"Evidence: {', '.join(hypothesis.evidence)}\n"
            f"Incident: {description}\n\n"
            f"Is this hypothesis well-supported by the evidence? "
            f"Respond: VALID (confidence adjustment: +X%) or INVALID (reason: ...) or UNCERTAIN"
        )

        try:
            response = model_router.route(
                TaskType.SECONDARY_VALIDATION,
                prompt=prompt,
                max_tokens=512,
                temperature=0.0,
            )

            import re
            if "VALID" in response and "INVALID" not in response:
                # Look for confidence adjustment
                adj_match = re.search(r'\+(\d+)%', response)
                if adj_match:
                    adjustment = int(adj_match.group(1)) / 100
                    hypothesis.confidence = min(hypothesis.confidence + adjustment, 0.98)
            elif "INVALID" in response:
                hypothesis.confidence = max(hypothesis.confidence - 0.15, 0.10)
            # UNCERTAIN: no change

        except Exception as e:
            logger.error("Hypothesis validation failed: %s", e)

        return hypothesis

    def _generate_recommendations(
        self,
        hypothesis: RCAHypothesis,
        similar_incidents: list[RetrievalResult],
    ) -> tuple[list[str], list[str]]:
        """Generate mitigation and prevention recommendations."""
        historical_mitigations = [
            r.incident.mitigation
            for r in similar_incidents
            if r.similarity_score > 0.70
        ]

        prompt = (
            f"Root cause: {hypothesis.hypothesis}\n"
            f"Category: {hypothesis.category}\n\n"
            f"Historical mitigations for similar incidents:\n"
            + "\n".join(f"- {m}" for m in historical_mitigations[:3])
            + "\n\nProvide:\n"
            f"1. IMMEDIATE_MITIGATIONS: 3 immediate actions to resolve the incident\n"
            f"2. PREVENTION: 3 long-term prevention recommendations\n"
            f"Format as JSON: "
            f'{{"mitigations": ["..."], "prevention": ["..."]}}'
        )

        try:
            response = model_router.route(
                TaskType.OPERATIONAL_RECOMMENDATION,
                prompt=prompt,
                max_tokens=1024,
                temperature=0.1,
            )
            import json, re
            json_match = re.search(r'\{.*\}', response, re.DOTALL)
            if json_match:
                data = json.loads(json_match.group())
                return data.get("mitigations", []), data.get("prevention", [])
        except Exception as e:
            logger.error("Recommendation generation failed: %s", e)

        return (
            ["Investigate the identified root cause", "Consider rollback if deployment-related"],
            ["Add monitoring for this failure mode", "Review similar code paths"],
        )

    def _build_timeline(
        self,
        telemetry: dict,
        deployment_history: list[dict],
        logs: list[str],
    ) -> list[dict]:
        """Build an incident timeline from available data."""
        timeline = []
        for deploy in deployment_history[-5:]:
            timeline.append({
                "timestamp": deploy.get("timestamp", ""),
                "event_type": "deployment",
                "description": f"Deployed {deploy.get('version', 'unknown')}: {deploy.get('description', '')}",
            })
        if telemetry.get("incident_start"):
            timeline.append({
                "timestamp": telemetry["incident_start"],
                "event_type": "anomaly_detected",
                "description": "Anomaly detected by ObservabilityAgent",
            })
        timeline.sort(key=lambda x: x.get("timestamp", ""))
        return timeline

    def _identify_affected_services(
        self, service: str, dependency_graph: Optional[dict]
    ) -> list[str]:
        """Identify potentially affected downstream services."""
        if not dependency_graph:
            return [service]
        # Simple BFS on dependency graph
        affected = {service}
        queue = [service]
        while queue:
            current = queue.pop(0)
            for downstream in dependency_graph.get(current, {}).get("downstream", []):
                if downstream not in affected:
                    affected.add(downstream)
                    queue.append(downstream)
        return list(affected)

    def _generate_summary(
        self, hypothesis: RCAHypothesis, service: str, description: str
    ) -> str:
        return (
            f"Incident on {service}: {description}. "
            f"Most likely root cause ({hypothesis.confidence:.0%} confidence): "
            f"{hypothesis.hypothesis}"
        )


# Singleton
rca_agent = RCAAgent()
