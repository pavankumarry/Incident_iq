"""
IncidentIQ - Amazon Bedrock Client
Handles invocation and streaming for all Bedrock models.

Priority model stack:
  P1  qwen.qwen3-32b-v1:0              — primary reasoning, RCA, orchestration
  P2  deepseek.v3-v1:0                 — deep analysis, critical validation
  P3  qwen.qwen3-coder-30b-a3b-v1:0   — code intelligence, PR generation
  P4  moonshotai.kimi-k2.5             — fast ChatOps, streaming summaries
  EMB amazon.titan-embed-text-v2:0     — vector embeddings (RAG)
"""
import json
import logging
from typing import Generator, Optional

import boto3
from botocore.exceptions import ClientError

from backend.config import config

logger = logging.getLogger(__name__)

# Models that use the Bedrock Converse / Messages-compatible API
# (Qwen, DeepSeek, Kimi all follow the same {"messages": [...]} schema on Bedrock)
_CONVERSE_FAMILIES = ("qwen", "deepseek", "moonshotai", "kimi")

# Models that use the Anthropic Messages API (kept for fallback awareness)
_ANTHROPIC_FAMILIES = ("anthropic", "claude")

# Models that use the Llama prompt format
_LLAMA_FAMILIES = ("llama",)

# Models that use the Nova schema
_NOVA_FAMILIES = ("nova",)


def _family(model_id: str) -> str:
    mid = model_id.lower()
    for f in _CONVERSE_FAMILIES:
        if f in mid:
            return "converse"
    for f in _ANTHROPIC_FAMILIES:
        if f in mid:
            return "anthropic"
    for f in _NOVA_FAMILIES:
        if f in mid:
            return "nova"
    for f in _LLAMA_FAMILIES:
        if f in mid:
            return "llama"
    return "converse"  # safe default — most new models use this schema


class BedrockClient:
    """Central Bedrock client. Dispatches to the correct request schema per model family."""

    def __init__(self):
        self.region = config.bedrock.region
        self._runtime = None

    @property
    def runtime(self):
        if self._runtime is None:
            self._runtime = boto3.client("bedrock-runtime", region_name=self.region)
        return self._runtime

    # ── Public API ────────────────────────────────────────────────────────────

    def invoke(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 4096,
        temperature: float = 0.1,
    ) -> str:
        """Invoke a model synchronously and return the response text."""
        try:
            body = self._build_body(model_id, prompt, system_prompt, max_tokens, temperature)
            logger.debug("Invoking %s (max_tokens=%d)", model_id, max_tokens)
            response = self.runtime.invoke_model(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            return self._parse(model_id, response)
        except ClientError as e:
            logger.error("Bedrock invoke failed [%s]: %s", model_id, e)
            raise

    def invoke_streaming(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: int = 2048,
        temperature: float = 0.1,
    ) -> Generator[str, None, None]:
        """Invoke a model with streaming and yield text chunks."""
        try:
            body = self._build_body(model_id, prompt, system_prompt, max_tokens, temperature)
            response = self.runtime.invoke_model_with_response_stream(
                modelId=model_id,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            yield from self._stream(model_id, response)
        except ClientError as e:
            logger.error("Bedrock stream failed [%s]: %s", model_id, e)
            raise

    def embed(self, text: str) -> list[float]:
        """Generate embeddings using Titan Embeddings V2."""
        try:
            body = {"inputText": text, "dimensions": 1024, "normalize": True}
            response = self.runtime.invoke_model(
                modelId=config.bedrock.titan_embeddings,
                body=json.dumps(body),
                contentType="application/json",
                accept="application/json",
            )
            return json.loads(response["body"].read())["embedding"]
        except ClientError as e:
            logger.error("Titan embed failed: %s", e)
            raise

    # ── Request body builders ─────────────────────────────────────────────────

    def _build_body(
        self,
        model_id: str,
        prompt: str,
        system_prompt: Optional[str],
        max_tokens: int,
        temperature: float,
    ) -> dict:
        fam = _family(model_id)

        if fam == "converse":
            # Qwen3, DeepSeek-V3, Kimi K2 — OpenAI-compatible Messages schema on Bedrock
            body: dict = {
                "messages": [{"role": "user", "content": prompt}],
                "max_tokens": int(max_tokens),
                "temperature": float(temperature),
            }
            if system_prompt:
                # Prepend as a system message (supported by all three)
                body["messages"] = [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": prompt},
                ]
            return body

        if fam == "anthropic":
            body = {
                "anthropic_version": "bedrock-2023-05-31",
                "max_tokens": int(max_tokens),
                "temperature": float(temperature),
                "messages": [{"role": "user", "content": prompt}],
            }
            if system_prompt:
                body["system"] = system_prompt
            return body

        if fam == "nova":
            body = {
                "messages": [{"role": "user", "content": [{"text": prompt}]}],
                "inferenceConfig": {
                    "maxNewTokens": int(max_tokens),
                    "temperature": float(temperature),
                },
            }
            if system_prompt:
                body["system"] = [{"text": system_prompt}]
            return body

        if fam == "llama":
            full = "<|begin_of_text|>"
            if system_prompt:
                full += f"<|start_header_id|>system<|end_header_id|>\n{system_prompt}<|eot_id|>"
            full += f"<|start_header_id|>user<|end_header_id|>\n{prompt}<|eot_id|>"
            full += "<|start_header_id|>assistant<|end_header_id|>"
            return {"prompt": full, "max_gen_len": int(max_tokens), "temperature": float(temperature)}

        raise ValueError(f"Cannot build request body for model: {model_id}")

    # ── Response parsers ──────────────────────────────────────────────────────

    def _parse(self, model_id: str, response: dict) -> str:
        body = json.loads(response["body"].read())
        fam = _family(model_id)

        if fam == "converse":
            # Qwen3 / DeepSeek / Kimi — OpenAI-style response
            # {"choices": [{"message": {"content": "..."}}]}
            choices = body.get("choices")
            if choices:
                return choices[0]["message"]["content"]
            # Some models return {"content": "..."} directly
            if "content" in body:
                return body["content"]
            # Fallback: return raw body as string for debugging
            return json.dumps(body)

        if fam == "anthropic":
            return body["content"][0]["text"]

        if fam == "nova":
            return body["output"]["message"]["content"][0]["text"]

        if fam == "llama":
            return body.get("generation", "")

        raise ValueError(f"Cannot parse response for model: {model_id}")

    def _stream(self, model_id: str, response: dict) -> Generator[str, None, None]:
        fam = _family(model_id)
        stream = response.get("body")
        if not stream:
            return
        for event in stream:
            chunk = event.get("chunk")
            if not chunk:
                continue
            data = json.loads(chunk["bytes"].decode())

            if fam == "converse":
                # SSE delta format: {"choices": [{"delta": {"content": "..."}}]}
                choices = data.get("choices")
                if choices:
                    yield choices[0].get("delta", {}).get("content", "")
                elif data.get("type") == "content_block_delta":
                    yield data.get("delta", {}).get("text", "")

            elif fam == "anthropic":
                if data.get("type") == "content_block_delta":
                    yield data["delta"].get("text", "")

            elif fam == "nova":
                if data.get("type") == "content_block_delta":
                    yield data.get("delta", {}).get("text", "")

            elif fam == "llama":
                yield data.get("generation", "")


# Singleton
bedrock_client = BedrockClient()
