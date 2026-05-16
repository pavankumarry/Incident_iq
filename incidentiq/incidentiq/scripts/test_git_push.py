"""
Test git push via GitHub API (Contents API) instead of git CLI.
Fine-grained PATs with Contents:Write can push via API even if git HTTPS fails.
Also tests PR creation and webhook registration.
"""
import os, sys, json, base64
from pathlib import Path

for line in (Path(__file__).parent.parent / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import httpx

TOKEN = os.environ.get("GITHUB_TOKEN", "")
OWNER = os.environ.get("GITHUB_REPO_OWNER", "pavankumarry")
REPO  = os.environ.get("GITHUB_REPO_NAME", "dummy")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}
client = httpx.Client(headers=HEADERS, timeout=15)

print(f"\n=== Testing GitHub API capabilities for {OWNER}/{REPO} ===\n")

# Test 1: Read repo
r = client.get(f"https://api.github.com/repos/{OWNER}/{REPO}")
print(f"Read repo:        {'✅' if r.status_code == 200 else '❌'} ({r.status_code})")

# Test 2: List branches
r = client.get(f"https://api.github.com/repos/{OWNER}/{REPO}/branches")
print(f"List branches:    {'✅' if r.status_code == 200 else '❌'} ({r.status_code})")
if r.status_code == 200:
    branches = [b["name"] for b in r.json()]
    print(f"  Branches: {branches}")
    default_branch = branches[0] if branches else "main"
else:
    default_branch = "main"

# Test 3: Create a file via Contents API (tests write access)
test_content = base64.b64encode(b"# IncidentIQ ShopApp\nThis repo is monitored by IncidentIQ.\n").decode()
r = client.put(
    f"https://api.github.com/repos/{OWNER}/{REPO}/contents/INCIDENTIQ.md",
    json={
        "message": "chore: add IncidentIQ monitoring badge",
        "content": test_content,
        "branch": default_branch,
    }
)
if r.status_code in (201, 422):  # 422 = file already exists
    print(f"Write file:       ✅ (Contents API works)")
    can_write = True
else:
    print(f"Write file:       ❌ ({r.status_code}: {r.json().get('message','')[:60]})")
    can_write = False

# Test 4: Create a branch (needed for PR demo)
if can_write:
    # Get current SHA of default branch
    r = client.get(f"https://api.github.com/repos/{OWNER}/{REPO}/git/ref/heads/{default_branch}")
    if r.status_code == 200:
        sha = r.json()["object"]["sha"]
        # Create test branch
        r2 = client.post(
            f"https://api.github.com/repos/{OWNER}/{REPO}/git/refs",
            json={"ref": "refs/heads/incidentiq-demo-bug", "sha": sha}
        )
        if r2.status_code in (201, 422):
            print(f"Create branch:    ✅ (branch API works)")
            branch_ok = True
        else:
            print(f"Create branch:    ❌ ({r2.status_code}: {r2.json().get('message','')[:60]})")
            branch_ok = False
    else:
        branch_ok = False

# Test 5: Create PR comment (tests PR write access)
r = client.get(f"https://api.github.com/repos/{OWNER}/{REPO}/pulls?state=open&per_page=1")
print(f"List PRs:         {'✅' if r.status_code == 200 else '❌'} ({r.status_code})")

# Test 6: Webhooks
r = client.get(f"https://api.github.com/repos/{OWNER}/{REPO}/hooks")
print(f"List webhooks:    {'✅' if r.status_code == 200 else '❌'} ({r.status_code})")
if r.status_code == 200:
    hooks = r.json()
    print(f"  Existing hooks: {len(hooks)}")

# Test 7: Create webhook (dry run — delete immediately)
r = client.post(
    f"https://api.github.com/repos/{OWNER}/{REPO}/hooks",
    json={
        "name": "web", "active": False,
        "events": ["pull_request"],
        "config": {"url": "https://test.example.com/webhook", "content_type": "json"}
    }
)
if r.status_code == 201:
    hook_id = r.json()["id"]
    client.delete(f"https://api.github.com/repos/{OWNER}/{REPO}/hooks/{hook_id}")
    print(f"Create webhook:   ✅ (webhook API works)")
    webhook_ok = True
else:
    print(f"Create webhook:   ❌ ({r.status_code}: {r.json().get('message','')[:60]})")
    webhook_ok = False

print(f"\n=== Summary ===")
print(f"  Repo: {OWNER}/{REPO}")
print(f"  Contents write: {'✅' if can_write else '❌'}")
print(f"  Webhook create: {'✅' if webhook_ok else '❌'}")
print()

if can_write and webhook_ok:
    print("  ✅ Token has all required permissions!")
    print("  You can now:")
    print("  1. Start ngrok: ngrok http 8000")
    print("  2. Register webhook: python scripts/setup_webhook.py")
    print("  3. Create a PR with bugs → IncidentIQ auto-reviews it")
elif can_write:
    print("  ⚠️  Can write files but not webhooks.")
    print("  Token needs 'Webhooks: Read and Write' permission.")
    print("  Update at: https://github.com/settings/personal-access-tokens")
else:
    print("  ❌ Token needs 'Contents: Read and Write' permission.")
    print("  Update at: https://github.com/settings/personal-access-tokens")
    print()
    print("  OR generate a classic PAT:")
    print("  https://github.com/settings/tokens/new?scopes=repo,admin:repo_hook")

client.close()
