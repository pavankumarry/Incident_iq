"""
IncidentIQ - Validation & Guardrail Agent
Prevents unsafe autonomous actions. Enforces policy, confidence thresholds,
secret protection, and human approval requirements.
"""
import logging
import re
from enum import Enum
from typing import Any, Optional

from backend.config import config

logger = logging.getLogger(__name__)


class ActionType(str, Enum):
    GENERATE_PR = "generate_pr"
    CREATE_ALERT = "create_alert"
    RECOMMEND_MITIGATION = "recommend_mitigation"
    GENERATE_DOCUMENTATION = "generate_documentation"
    RUN_SANDBOX_TEST = "run_sandbox_test"
    SUGGEST_ROLLBACK = "suggest_rollback"
    # Require human approval:
    DEPLOY_TO_PRODUCTION = "deploy_to_production"
    DATABASE_SCHEMA_CHANGE = "database_schema_change"
    INFRASTRUCTURE_DELETION = "infrastructure_deletion"
    PERMISSION_CHANGE = "permission_change"
    CUSTOMER_IMPACTING_ACTION = "customer_impacting_action"


# Actions that are always advisory-only (never autonomous execution)
ADVISORY_ONLY_ACTIONS = {
    ActionType.DEPLOY_TO_PRODUCTION,
    ActionType.DATABASE_SCHEMA_CHANGE,
    ActionType.INFRASTRUCTURE_DELETION,
    ActionType.PERMISSION_CHANGE,
    ActionType.CUSTOMER_IMPACTING_ACTION,
}

# Patterns that indicate potential secret leakage
SECRET_PATTERNS = [
    r"(?i)(aws_access_key_id|aws_secret_access_key|aws_session_token)\s*=\s*['\"]?[A-Za-z0-9+/=]{16,}",
    r"(?i)(password|passwd|pwd)\s*=\s*['\"][^'\"]{6,}['\"]",
    r"(?i)(api_key|apikey|api-key)\s*=\s*['\"][^'\"]{8,}['\"]",
    r"(?i)(secret|token)\s*=\s*['\"][^'\"]{8,}['\"]",
    r"(?i)bearer\s+[A-Za-z0-9\-._~+/]+=*",
    r"AKIA[0-9A-Z]{16}",  # AWS Access Key ID pattern
    r"(?i)private.?key",
]

# Patterns that indicate prompt injection attempts
PROMPT_INJECTION_PATTERNS = [
    r"(?i)ignore (previous|all|above) instructions",
    r"(?i)you are now",
    r"(?i)forget (everything|all|your instructions)",
    r"(?i)new (system|role|persona|instructions)",
    r"(?i)disregard (your|all|previous)",
    r"(?i)act as (a|an) (?!SRE|engineer|analyst)",
]


class GuardrailViolation(Exception):
    """Raised when a guardrail check fails."""
    def __init__(self, violation_type: str, message: str):
        self.violation_type = violation_type
        self.message = message
        super().__init__(f"[{violation_type}] {message}")


class GuardrailAgent:
    """
    Enforces safety policies across all agent actions.
    Hard guardrails that cannot be bypassed.
    """

    def check_action(
        self,
        action_type: ActionType,
        content: Optional[str] = None,
        confidence: Optional[float] = None,
        context: Optional[dict] = None,
    ) -> dict:
        """
        Run all guardrail checks for a proposed action.
        Returns a result dict with allowed/blocked status and reasons.
        """
        result = {
            "allowed": True,
            "requires_approval": False,
            "violations": [],
            "warnings": [],
        }

        # Check 1: Advisory-only mode
        if config.guardrails.advisory_only_mode and action_type in ADVISORY_ONLY_ACTIONS:
            result["allowed"] = False
            result["requires_approval"] = True
            result["violations"].append(
                f"Action '{action_type}' requires human approval in advisory-only mode."
            )
            logger.warning("[Guardrail] Blocked: %s requires human approval", action_type)

        # Check 2: Confidence threshold
        if confidence is not None and confidence < config.guardrails.confidence_threshold:
            result["allowed"] = False
            result["violations"].append(
                f"Confidence {confidence:.2f} below threshold {config.guardrails.confidence_threshold}. "
                f"Action suppressed to prevent hallucination."
            )
            logger.warning(
                "[Guardrail] Blocked: confidence %.2f below threshold", confidence
            )

        # Check 3: Secret leakage detection
        if content:
            secret_violations = self._check_secret_leakage(content)
            if secret_violations:
                result["allowed"] = False
                result["violations"].extend(secret_violations)
                logger.error("[Guardrail] SECRET LEAKAGE DETECTED: %s", secret_violations)

        # Check 4: Prompt injection detection
        if content:
            injection_violations = self._check_prompt_injection(content)
            if injection_violations:
                result["allowed"] = False
                result["violations"].extend(injection_violations)
                logger.error("[Guardrail] PROMPT INJECTION DETECTED: %s", injection_violations)

        # Check 5: Human approval required
        if self.requires_human_approval(action_type, context):
            result["requires_approval"] = True
            if action_type not in ADVISORY_ONLY_ACTIONS:
                result["warnings"].append(
                    f"Action '{action_type}' requires human approval before execution."
                )

        return result

    def requires_human_approval(
        self, action_type: ActionType, context: Optional[dict] = None
    ) -> bool:
        """Check if an action requires human approval."""
        if action_type in ADVISORY_ONLY_ACTIONS:
            return True
        if action_type.value in config.guardrails.require_human_approval_for:
            return True
        # Additional context-based checks
        if context:
            if context.get("severity") in ("p0", "critical"):
                return True
            if context.get("affects_production"):
                return True
        return False

    def validate_generated_code(self, code: str, file_path: str) -> dict:
        """
        Validate generated code for security issues and dangerous patterns.
        """
        issues = []
        warnings = []

        # Check for dangerous patterns
        dangerous_patterns = {
            r"os\.system\(": "Direct OS command execution",
            r"subprocess\.call\(": "Subprocess execution without shell=False",
            r"eval\(": "Dynamic code evaluation",
            r"exec\(": "Dynamic code execution",
            r"__import__\(": "Dynamic import",
            r"open\(['\"]\/etc": "Reading system files",
            r"DROP\s+TABLE": "SQL DROP TABLE statement",
            r"DELETE\s+FROM\s+\w+\s*;": "Unfiltered SQL DELETE",
            r"TRUNCATE\s+TABLE": "SQL TRUNCATE statement",
        }

        for pattern, description in dangerous_patterns.items():
            if re.search(pattern, code, re.IGNORECASE):
                issues.append(f"Dangerous pattern in {file_path}: {description}")

        # Check for hardcoded secrets
        secret_issues = self._check_secret_leakage(code)
        issues.extend(secret_issues)

        # Check for SQL injection vulnerabilities
        sql_injection_patterns = [
            r'f".*SELECT.*{',
            r"f'.*SELECT.*{",
            r'f".*WHERE.*{',
            r"f'.*WHERE.*{",
        ]
        for pattern in sql_injection_patterns:
            if re.search(pattern, code):
                warnings.append(
                    f"Potential SQL injection in {file_path}: use parameterized queries"
                )

        return {
            "valid": len(issues) == 0,
            "issues": issues,
            "warnings": warnings,
            "requires_review": len(warnings) > 0,
        }

    def _check_secret_leakage(self, content: str) -> list[str]:
        """Detect potential secret/credential leakage in content."""
        violations = []
        for pattern in SECRET_PATTERNS:
            if re.search(pattern, content):
                violations.append(
                    f"Potential secret leakage detected. Pattern: {pattern[:30]}... "
                    f"Rotate credentials immediately if real credentials were exposed."
                )
        return violations

    def _check_prompt_injection(self, content: str) -> list[str]:
        """Detect prompt injection attempts in user-provided content."""
        violations = []
        for pattern in PROMPT_INJECTION_PATTERNS:
            if re.search(pattern, content):
                violations.append(
                    f"Prompt injection attempt detected. Content rejected."
                )
                break  # One violation is enough
        return violations

    def sanitize_for_llm(self, user_input: str) -> str:
        """
        Sanitize user input before passing to LLM to prevent prompt injection.
        Wraps input in a safe delimiter.
        """
        # Remove any system-level instruction patterns
        sanitized = user_input
        for pattern in PROMPT_INJECTION_PATTERNS:
            sanitized = re.sub(pattern, "[REDACTED]", sanitized, flags=re.IGNORECASE)
        return f"<user_input>{sanitized}</user_input>"

    def audit_log(
        self,
        action_type: ActionType,
        actor: str,
        result: dict,
        context: Optional[dict] = None,
    ):
        """Write an immutable audit log entry for every autonomous action."""
        from datetime import datetime
        entry = {
            "timestamp": datetime.utcnow().isoformat(),
            "action_type": action_type,
            "actor": actor,
            "allowed": result.get("allowed"),
            "requires_approval": result.get("requires_approval"),
            "violations": result.get("violations", []),
            "context": context or {},
        }
        # In production: write to CloudWatch Logs, S3, or audit DB
        logger.info("[AuditLog] %s", entry)
        return entry


# Singleton
guardrail = GuardrailAgent()
