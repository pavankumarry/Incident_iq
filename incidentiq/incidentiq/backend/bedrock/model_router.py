"""
IncidentIQ - Model Router
Routes tasks to the appropriate Bedrock model based on task type.

Priority stack (highest → lowest):
  P1  qwen.qwen3-32b-v1:0              — primary reasoning, RCA, orchestration
  P2  deepseek.v3-v1:0                 — deep analysis, critical incident validation
  P3  qwen.qwen3-coder-30b-a3b-v1:0   — code intelligence, PR generation
  P4  moonshotai.kimi-k2.5             — fast ChatOps, streaming, summaries
  EMB amazon.titan-embed-text-v2:0     — embeddings only
"""
import logging
from enum import Enum
from typing import Optional

from backend.bedrock.client import bedrock_client
from backend.config import config

logger = logging.getLogger(__name__)


class TaskType(str, Enum):
    # ── P1: Qwen3 32B — primary reasoning ────────────────────────────────────
    DEEP_REASONING            = "deep_reasoning"
    ROOT_CAUSE_ANALYSIS       = "root_cause_analysis"
    ARCHITECTURE_ANALYSIS     = "architecture_analysis"
    SOP_VALIDATION            = "sop_validation"
    MULTI_STEP_ORCHESTRATION  = "multi_step_orchestration"

    # ── P2: DeepSeek V3 — deep / critical analysis ────────────────────────────
    CRITICAL_INCIDENT         = "critical_incident"
    FINAL_VALIDATION          = "final_validation"
    SECONDARY_VALIDATION      = "secondary_validation"
    CONSENSUS_CHECK           = "consensus_check"

    # ── P3: Qwen3 Coder — code tasks ─────────────────────────────────────────
    PR_GENERATION             = "pr_generation"
    CODE_FIX                  = "code_fix"
    CODE_REVIEW               = "code_review"
    TEST_GENERATION           = "test_generation"

    # ── P4: Kimi K2 — fast / streaming ───────────────────────────────────────
    STREAMING_SUMMARY         = "streaming_summary"
    CHATOPS_RESPONSE          = "chatops_response"
    OPERATIONAL_RECOMMENDATION = "operational_recommendation"
    ALERT_CLASSIFICATION      = "alert_classification"
    EVENT_TRIAGE              = "event_triage"
    QUICK_SUMMARY             = "quick_summary"


# ── Task → Model mapping (priority order) ────────────────────────────────────
def _build_task_map() -> dict:
    b = config.bedrock
    return {
        # P1 — Qwen3 32B
        TaskType.DEEP_REASONING:            b.qwen3_32b,
        TaskType.ROOT_CAUSE_ANALYSIS:       b.qwen3_32b,
        TaskType.ARCHITECTURE_ANALYSIS:     b.qwen3_32b,
        TaskType.SOP_VALIDATION:            b.qwen3_32b,
        TaskType.MULTI_STEP_ORCHESTRATION:  b.qwen3_32b,

        # P2 — DeepSeek V3
        TaskType.CRITICAL_INCIDENT:         b.deepseek_v3,
        TaskType.FINAL_VALIDATION:          b.deepseek_v3,
        TaskType.SECONDARY_VALIDATION:      b.deepseek_v3,
        TaskType.CONSENSUS_CHECK:           b.deepseek_v3,

        # P3 — Qwen3 Coder
        TaskType.PR_GENERATION:             b.qwen3_coder,
        TaskType.CODE_FIX:                  b.qwen3_coder,
        TaskType.CODE_REVIEW:               b.qwen3_coder,
        TaskType.TEST_GENERATION:           b.qwen3_coder,

        # P4 — Kimi K2
        TaskType.STREAMING_SUMMARY:         b.kimi_k2,
        TaskType.CHATOPS_RESPONSE:          b.kimi_k2,
        TaskType.OPERATIONAL_RECOMMENDATION: b.kimi_k2,
        TaskType.ALERT_CLASSIFICATION:      b.kimi_k2,
        TaskType.EVENT_TRIAGE:              b.kimi_k2,
        TaskType.QUICK_SUMMARY:             b.kimi_k2,
    }


TASK_MODEL_MAP: dict = {}  # populated lazily on first use


def _get_map() -> dict:
    global TASK_MODEL_MAP
    if not TASK_MODEL_MAP:
        TASK_MODEL_MAP = _build_task_map()
    return TASK_MODEL_MAP


class ModelRouter:
    """
    Routes AI tasks to the optimal model.
    Implements multi-model consensus for critical decisions.
    """

    def route(
        self,
        task_type: TaskType,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> str:
        """Route a task to the appropriate model and return the response."""
        model_id = _get_map().get(task_type, config.bedrock.primary)
        logger.info("[Router] %s → %s", task_type.value, model_id)
        return bedrock_client.invoke(
            model_id=model_id,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
            temperature=temperature,
        )

    def route_streaming(
        self,
        task_type: TaskType,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
    ):
        """Route a streaming task to the appropriate model."""
        model_id = _get_map().get(task_type, config.bedrock.fast_model)
        logger.info("[Router] streaming %s → %s", task_type.value, model_id)
        return bedrock_client.invoke_streaming(
            model_id=model_id,
            prompt=prompt,
            system_prompt=system_prompt,
            max_tokens=max_tokens,
        )

    def consensus_validate(
        self,
        hypothesis: str,
        context: str,
        severity: str = "medium",
    ) -> dict:
        """
        Multi-model consensus workflow using the priority stack:
          1. Kimi K2      — fast incident classification
          2. Qwen3 32B    — deep RCA reasoning
          3. DeepSeek V3  — independent hypothesis validation
          4. DeepSeek V3  — final critical validation (P0/P1 only)
        """
        results = {}

        # Step 1: Kimi K2 — fast classification
        results["classification"] = self.route(
            TaskType.ALERT_CLASSIFICATION,
            prompt=f"Classify this incident hypothesis in one sentence:\n{hypothesis}\nContext:\n{context}",
            max_tokens=256,
        )

        # Step 3: Qwen3 32B — deep RCA
        results["rca"] = self.route(
            TaskType.ROOT_CAUSE_ANALYSIS,
            prompt=f"Perform root cause analysis:\nHypothesis: {hypothesis}\nContext: {context}",
            system_prompt=SYSTEM_PROMPTS["rca"],
            max_tokens=3000,
        )

        # Step 3: DeepSeek V3 — secondary validation
        results["deepseek_validation"] = self.route(
            TaskType.SECONDARY_VALIDATION,
            prompt=(
                f"Validate this root cause analysis. Is it sound?\n"
                f"RCA: {results['rca']}\nOriginal hypothesis: {hypothesis}"
            ),
            max_tokens=1024,
        )

        # Step 4: DeepSeek V3 — final critical validation for P0/P1
        if severity in ("critical", "p0", "p1"):
            results["final_validation"] = self.route(
                TaskType.FINAL_VALIDATION,
                prompt=(
                    f"Final critical validation:\n"
                    f"RCA: {results['rca']}\n"
                    f"Validation: {results['deepseek_validation']}\n"
                    f"Hypothesis: {hypothesis}"
                ),
                system_prompt=SYSTEM_PROMPTS["final_validation"],
                max_tokens=2048,
            )

        results["confidence"] = self._score_consensus(results)
        return results

    def _score_consensus(self, results: dict) -> float:
        validation_text = (
            results.get("deepseek_validation", "") +
            results.get("final_validation", "")
        ).lower()

        agreement    = ["agree", "correct", "valid", "sound", "accurate", "confirmed", "supported"]
        disagreement = ["disagree", "incorrect", "invalid", "unsound", "inaccurate", "wrong", "flawed"]

        score = 0.75
        for s in agreement:
            if s in validation_text:
                score = min(score + 0.04, 0.98)
        for s in disagreement:
            if s in validation_text:
                score = max(score - 0.10, 0.10)

        return round(score, 2)


SYSTEM_PROMPTS = {
    "rca": (
        "You are an expert Site Reliability Engineer performing root cause analysis. "
        "Be precise, cite evidence from the provided data, and structure your response as: "
        "1) Summary  2) Root Cause  3) Contributing Factors  4) Evidence  5) Confidence Score (0-1). "
        "Never speculate without evidence. If uncertain, say so explicitly."
    ),
    "final_validation": (
        "You are a senior engineering lead performing final validation of an incident RCA. "
        "Critically evaluate the analysis for logical gaps, missing evidence, or incorrect assumptions. "
        "Provide a final verdict: APPROVED, NEEDS_REVISION, or REJECTED with justification."
    ),
    "pr_generation": (
        "You are an expert software engineer generating a production-ready Pull Request. "
        "Include: clear title, problem summary, root cause, fix explanation, risk analysis, "
        "rollback strategy, test coverage, and expected impact. "
        "Code must be secure, performant, and well-documented."
    ),
    "code_fix": (
        "You are an expert software engineer fixing a production bug. "
        "Write clean, secure, well-commented code. "
        "Always use parameterized queries, proper error handling, and resource cleanup. "
        "Return only the fixed code with a brief explanation."
    ),
}


# Singleton
model_router = ModelRouter()
