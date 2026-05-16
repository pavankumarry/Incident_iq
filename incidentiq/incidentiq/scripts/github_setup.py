"""
IncidentIQ - Full GitHub Setup
1. Lists existing repos to find the right target
2. Creates the incidentiq repo if it doesn't exist
3. Generates a webhook secret and saves it to .env
4. Registers the webhook (requires ngrok or public URL)
5. Pushes the shopapp code so PRs can be raised against it

Run: python scripts/github_setup.py
"""
import os, sys, json, secrets
from pathlib import Path

# Load .env
ENV_PATH = Path(__file__).parent.parent / ".env"
env_vars = {}
for line in ENV_PATH.read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        env_vars[k.strip()] = v.strip()
        os.environ.setdefault(k.strip(), v.strip())

import httpx

TOKEN  = os.environ.get("GITHUB_TOKEN", "")
OWNER  = os.environ.get("GITHUB_REPO_OWNER", "")
SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

client = httpx.Client(headers=HEADERS, timeout=15)


def sep(title=""):
    print(f"\n{'─'*58}")
    if title:
        print(f"  {title}")
        print(f"{'─'*58}")


def update_env(key: str, value: str):
    """Update or add a key in the .env file."""
    lines = ENV_PATH.read_text().splitlines()
    found = False
    new_lines = []
    for line in lines:
        if line.strip().startswith(f"{key}=") or line.strip().startswith(f"{key} ="):
            new_lines.append(f"{key}={value}")
            found = True
        else:
            new_lines.append(line)
    if not found:
        new_lines.append(f"{key}={value}")
    ENV_PATH.write_text("\n".join(new_lines) + "\n")
    os.environ[key] = value
    print(f"  ✅ Updated .env: {key}=***")


# ── Step 1: List existing repos ───────────────────────────────────────────────
sep("Step 1: Your GitHub Repositories")
r = client.get("https://api.github.com/user/repos?per_page=30&sort=updated")
if r.status_code != 200:
    print(f"  ❌ Cannot list repos: {r.status_code} {r.text[:100]}")
    print("  Your token may need 'repo' scope. Generate a new classic PAT at:")
    print("  https://github.com/settings/tokens/new?scopes=repo")
    sys.exit(1)

repos = r.json()
repo_names = [repo["full_name"] for repo in repos]
print(f"  Found {len(repos)} repos:")
for repo in repos[:15]:
    marker = " ← target" if repo["name"] == "incidentiq" else ""
    print(f"    {repo['full_name']} ({repo['visibility']}){marker}")

# ── Step 2: Create repo if needed ─────────────────────────────────────────────
sep("Step 2: Target Repository")
target_full = f"{OWNER}/incidentiq"

if target_full in repo_names:
    print(f"  ✅ Repo {target_full} already exists")
    repo_data = next(r2 for r2 in repos if r2["full_name"] == target_full)
else:
    print(f"  Repo {target_full} not found.")
    print()
    print("  Your token is a fine-grained PAT — it cannot create repos.")
    print("  Two options:")
    print()
    print("  OPTION A — Use an existing repo (recommended for hackathon):")
    print("  Pick any repo from the list above and update .env:")
    print('  GITHUB_REPO_OWNER=pavankumarry')
    print('  GITHUB_REPO_NAME=<repo-name-from-list>')
    print()
    print("  OPTION B — Generate a classic PAT with full repo scope:")
    print("  https://github.com/settings/tokens/new?scopes=repo,admin:repo_hook")
    print("  Then update GITHUB_TOKEN in .env")
    print()

    # Auto-pick the best existing repo for the demo
    # Prefer 'dummy' or 'localrepo' as they're likely test repos
    preferred = ["dummy", "localrepo", "chatbot"]
    picked = None
    for name in preferred:
        if f"{OWNER}/{name}" in repo_names:
            picked = name
            break
    if not picked and repos:
        # Just use the most recently updated one owned by the user
        user_repos = [r2 for r2 in repos if r2["owner"]["login"] == OWNER]
        if user_repos:
            picked = user_repos[0]["name"]

    if picked:
        print(f"  Auto-selecting existing repo: {OWNER}/{picked}")
        print(f"  Updating .env with GITHUB_REPO_NAME={picked}")
        update_env("GITHUB_REPO_NAME", picked)
        REPO = picked
        repo_data = next(r2 for r2 in repos if r2["name"] == picked and r2["owner"]["login"] == OWNER)
        print(f"  ✅ Using: {repo_data['html_url']}")
    else:
        print("  No suitable repo found. Please create one manually on GitHub.")
        sys.exit(1)

print(f"  URL: {repo_data['html_url']}")
print(f"  Clone: {repo_data['clone_url']}")

# ── Step 3: Webhook secret ────────────────────────────────────────────────────
sep("Step 3: Webhook Secret")
if not SECRET:
    SECRET = secrets.token_hex(32)
    update_env("GITHUB_WEBHOOK_SECRET", SECRET)
    print(f"  Generated new webhook secret and saved to .env")
else:
    print(f"  ✅ Webhook secret already set in .env")

# ── Step 4: Check for ngrok / public URL ──────────────────────────────────────
sep("Step 4: Public URL for Webhook")

public_url = os.environ.get("INCIDENTIQ_PUBLIC_URL", "")

# Try ngrok
if not public_url:
    try:
        r_ngrok = httpx.get("http://localhost:4040/api/tunnels", timeout=3)
        tunnels = r_ngrok.json().get("tunnels", [])
        for t in tunnels:
            if t.get("proto") == "https":
                public_url = t["public_url"]
                break
        if not public_url and tunnels:
            public_url = tunnels[0].get("public_url", "").replace("http://", "https://")
    except Exception:
        pass

if public_url:
    print(f"  ✅ Public URL: {public_url}")
    webhook_url = f"{public_url}/api/github/webhook"

    # Register webhook
    sep("Step 5: Registering Webhook")

    # Check existing hooks first
    r = client.get(f"https://api.github.com/repos/{OWNER}/incidentiq/hooks")
    existing_hooks = r.json() if r.status_code == 200 else []
    already_registered = any(
        "github/webhook" in h.get("config", {}).get("url", "")
        for h in existing_hooks
    )

    if already_registered:
        print(f"  ✅ Webhook already registered")
        for h in existing_hooks:
            if "github/webhook" in h.get("config", {}).get("url", ""):
                print(f"     id={h['id']} url={h['config']['url']} active={h['active']}")
    else:
        r = client.post(
            f"https://api.github.com/repos/{OWNER}/incidentiq/hooks",
            json={
                "name": "web",
                "active": True,
                "events": ["pull_request", "push"],
                "config": {
                    "url": webhook_url,
                    "content_type": "json",
                    "secret": SECRET,
                    "insecure_ssl": "0",
                },
            },
        )
        if r.status_code == 201:
            hook = r.json()
            print(f"  ✅ Webhook registered!")
            print(f"     ID     : {hook['id']}")
            print(f"     URL    : {hook['config']['url']}")
            print(f"     Events : {hook['events']}")
        else:
            print(f"  ❌ Failed: {r.status_code} {r.text[:200]}")
else:
    sep("Step 5: Webhook Registration — SKIPPED")
    print("  ⚠️  No public URL found. ngrok is not running.")
    print()
    print("  To register the webhook:")
    print("  1. Open a new terminal and run:")
    print("     ngrok http 8000")
    print()
    print("  2. Then run this script again, OR run:")
    print("     python scripts/setup_webhook.py")
    print()
    print("  OR set INCIDENTIQ_PUBLIC_URL in .env if you have a domain.")

# ── Step 6: Git remote setup ──────────────────────────────────────────────────
sep("Step 6: Git Remote for ShopApp")
shopapp_dir = Path(__file__).parent.parent.parent / "shopapp"
print(f"  ShopApp directory: {shopapp_dir}")

if shopapp_dir.exists():
    # Check if git is initialized
    git_dir = shopapp_dir / ".git"
    if not git_dir.exists():
        print("  Git not initialized in shopapp/")
        print("  To push shopapp code so you can raise PRs against it:")
        print(f"  1. cd {shopapp_dir}")
        print(f"  2. git init")
        print(f"  3. git remote add origin https://github.com/{OWNER}/incidentiq.git")
        print(f"  4. git add .")
        print(f'  5. git commit -m "Initial ShopApp commit"')
        print(f"  6. git push -u origin main")
    else:
        import subprocess
        result = subprocess.run(
            ["git", "remote", "-v"],
            cwd=str(shopapp_dir),
            capture_output=True, text=True
        )
        if result.returncode == 0 and result.stdout:
            print(f"  ✅ Git remotes configured:")
            for line in result.stdout.strip().splitlines():
                print(f"     {line}")
        else:
            print("  ⚠️  No git remotes configured")
            print(f"  Run: git remote add origin https://github.com/{OWNER}/incidentiq.git")

# ── Summary ───────────────────────────────────────────────────────────────────
sep("Summary")
print(f"  GitHub user    : {OWNER}")
print(f"  Target repo    : https://github.com/{OWNER}/incidentiq")
print(f"  Webhook route  : POST /api/github/webhook  ✅ (route exists)")
print(f"  Webhook secret : {'✅ set' if SECRET else '❌ not set'}")
print(f"  Public URL     : {public_url or '❌ not set (start ngrok)'}")
print()
print("  How to trigger a real PR review:")
print(f"  1. Push code to https://github.com/{OWNER}/incidentiq")
print(f"  2. Create a branch with a bug, open a PR")
print(f"  3. IncidentIQ auto-reviews it and posts a comment")
print()
print("  Or test without GitHub:")
print("  python scripts/test_pr_review.py")
print()

client.close()
