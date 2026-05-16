"""Test RCA model response to debug JSON parsing."""
import os, sys, json, re
from pathlib import Path

for line in (Path(__file__).parent.parent / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.bedrock.model_router import model_router, TaskType

prompt = (
    "Service shopapp has 25% error rate after deployment v1.1.0.\n"
    "Logs: connection pool exhausted, SQL injection risk in products.py, "
    "raw connections never released in sessions.py.\n\n"
    "Generate 3 root cause hypotheses.\n"
    "IMPORTANT: Respond with ONLY a valid JSON array, no other text:\n"
    '[{"hypothesis": "...", "confidence": 0.85, "evidence": ["..."], "category": "..."}]'
)

print("Calling Qwen3 32B for RCA...")
resp = model_router.route(TaskType.ROOT_CAUSE_ANALYSIS, prompt=prompt, max_tokens=1024, temperature=0.1)
print("Raw response:")
print(repr(resp[:800]))
print()

# Try parsing
start = resp.find("[")
end = resp.rfind("]")
if start != -1 and end != -1:
    try:
        data = json.loads(resp[start:end+1])
        print(f"Parsed {len(data)} hypotheses:")
        for h in data:
            print(f"  - {h.get('hypothesis','?')[:80]} (conf={h.get('confidence','?')})")
    except Exception as e:
        print(f"JSON parse failed: {e}")
        print(f"Attempted to parse: {repr(resp[start:end+1][:300])}")
else:
    print("No JSON array found in response")
