"""
IncidentIQ - Bedrock Connection Test
Tests all four priority models + Titan Embeddings.

Priority order:
  P1  qwen.qwen3-32b-v1:0              primary reasoning
  P2  deepseek.v3-v1:0                 deep analysis
  P3  qwen.qwen3-coder-30b-a3b-v1:0   code intelligence
  P4  moonshotai.kimi-k2.5             fast ChatOps
  EMB amazon.titan-embed-text-v2:0     embeddings

Run: python scripts/test_bedrock.py
"""
import os
import sys
import json
from pathlib import Path

# Load .env
env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, val = line.partition("=")
            os.environ.setdefault(key.strip(), val.strip())

import boto3
from botocore.exceptions import ClientError

REGION = os.environ.get("AWS_DEFAULT_REGION", "us-west-2")

MODELS = [
    ("P1  Qwen3 32B (primary reasoning)",    "qwen.qwen3-32b-v1:0",            "converse"),
    ("P2  DeepSeek V3 (deep analysis)",       "deepseek.v3-v1:0",               "converse"),
    ("P3  Qwen3 Coder (code intelligence)",   "qwen.qwen3-coder-30b-a3b-v1:0",  "converse"),
    ("P4  Kimi K2 (fast ChatOps)",            "moonshotai.kimi-k2.5",           "converse"),
    ("EMB Titan Embeddings V2",               "amazon.titan-embed-text-v2:0",   "embed"),
]

CONVERSE_BODY = json.dumps({
    "messages": [{"role": "user", "content": "Reply with exactly three words: INCIDENTIQ IS READY"}],
    "max_tokens": 32,
    "temperature": 0.0,
})

EMBED_BODY = json.dumps({
    "inputText": "IncidentIQ vector store test",
    "dimensions": 256,
    "normalize": True,
})


def test(client, model_id: str, schema: str) -> dict:
    try:
        if schema == "embed":
            resp = client.invoke_model(
                modelId=model_id, body=EMBED_BODY,
                contentType="application/json", accept="application/json",
            )
            result = json.loads(resp["body"].read())
            dim = len(result.get("embedding", []))
            return {"ok": True, "detail": f"embedding dim={dim}"}

        # converse schema (Qwen / DeepSeek / Kimi)
        resp = client.invoke_model(
            modelId=model_id, body=CONVERSE_BODY,
            contentType="application/json", accept="application/json",
        )
        result = json.loads(resp["body"].read())

        # Parse response — try OpenAI-style first, then fallbacks
        text = ""
        if result.get("choices"):
            text = result["choices"][0]["message"]["content"]
        elif result.get("content"):
            text = result["content"]
        elif result.get("output"):
            text = str(result["output"])
        else:
            text = json.dumps(result)[:80]

        return {"ok": True, "detail": text.strip()[:70]}

    except ClientError as e:
        code = e.response["Error"]["Code"]
        msg  = e.response["Error"]["Message"][:90]
        return {"ok": False, "detail": f"{code}: {msg}"}
    except Exception as e:
        return {"ok": False, "detail": str(e)[:90]}


def main():
    print(f"\n{'='*65}")
    print(f"  IncidentIQ — Bedrock Model Connectivity Test")
    print(f"  Region : {REGION}")
    print(f"{'='*65}\n")

    client = boto3.client("bedrock-runtime", region_name=REGION)
    all_ok = True

    for label, model_id, schema in MODELS:
        print(f"  {label}")
        print(f"  Model : {model_id}")
        r = test(client, model_id, schema)
        icon = "✅" if r["ok"] else "❌"
        print(f"  {icon}  {r['detail']}\n")
        if not r["ok"]:
            all_ok = False

    print("="*65)
    if all_ok:
        print("  ✅  All models accessible — IncidentIQ is ready to run!")
    else:
        print("  ❌  Some models failed.")
        print("  →  Enable models at:")
        print("     https://console.aws.amazon.com/bedrock/home#/modelaccess")
    print("="*65 + "\n")
    sys.exit(0 if all_ok else 1)


if __name__ == "__main__":
    main()
