"""Find which repos the current token can push to."""
import os, sys
from pathlib import Path

for line in (Path(__file__).parent.parent / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

import httpx

TOKEN = os.environ.get("GITHUB_TOKEN", "")
HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

client = httpx.Client(headers=HEADERS, timeout=10)

print("\n=== Token Info ===")
r = client.get("https://api.github.com/user")
user = r.json()
print(f"Login: {user['login']}")

# Check token type from headers
r2 = client.get("https://api.github.com/user")
print(f"X-OAuth-Scopes: {r2.headers.get('x-oauth-scopes', 'none (fine-grained PAT)')}")
print(f"X-Accepted-OAuth-Scopes: {r2.headers.get('x-accepted-oauth-scopes', '')}")

print("\n=== Repos with push access ===")
r3 = client.get("https://api.github.com/user/repos?per_page=50&sort=updated")
repos = r3.json()
writable = []
for repo in repos:
    if repo.get("permissions", {}).get("push"):
        writable.append(repo)
        print(f"  ✅ PUSH  {repo['full_name']}")
    else:
        print(f"  ❌ READ  {repo['full_name']}")

print(f"\n=== Fine-grained PAT permissions ===")
# Fine-grained PATs show their resource server
r4 = client.get("https://api.github.com/installation/repositories")
print(f"Installation repos status: {r4.status_code}")

print("\n=== Recommendation ===")
if writable:
    print(f"Use repo: {writable[0]['full_name']}")
    print(f"Update .env: GITHUB_REPO_NAME={writable[0]['name']}")
    print(f"Update .env: GITHUB_REPO_OWNER={writable[0]['owner']['login']}")
else:
    print("No repos with push access found.")
    print()
    print("Your fine-grained PAT needs to be updated.")
    print("Go to: https://github.com/settings/personal-access-tokens")
    print("Edit your token and add these permissions:")
    print("  Repository permissions:")
    print("    - Contents: Read and Write  (to push code)")
    print("    - Pull requests: Read and Write  (to post PR reviews)")
    print("    - Webhooks: Read and Write  (to register webhooks)")
    print("    - Metadata: Read  (required)")
    print()
    print("OR generate a classic PAT (simpler):")
    print("  https://github.com/settings/tokens/new?scopes=repo,admin:repo_hook")

client.close()
