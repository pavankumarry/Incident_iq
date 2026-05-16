"""
IncidentIQ - GitHub Integration Status Check
Verifies token, repo access, webhooks, and open PRs.
Run: python scripts/check_github.py
"""
import os, sys, json
from pathlib import Path

# Load .env
for line in (Path(__file__).parent.parent / ".env").read_text().splitlines():
    line = line.strip()
    if line and not line.startswith("#") and "=" in line:
        k, _, v = line.partition("=")
        os.environ.setdefault(k.strip(), v.strip())

try:
    import httpx
except ImportError:
    print("httpx not installed. Run: pip install httpx")
    sys.exit(1)

TOKEN  = os.environ.get("GITHUB_TOKEN", "")
OWNER  = os.environ.get("GITHUB_REPO_OWNER", "")
REPO   = os.environ.get("GITHUB_REPO_NAME", "")
SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")

HEADERS = {
    "Authorization": f"Bearer {TOKEN}",
    "Accept": "application/vnd.github+json",
    "X-GitHub-Api-Version": "2022-11-28",
}

def check(label, ok, detail=""):
    icon = "✅" if ok else "❌"
    print(f"  {icon}  {label:<30} {detail}")

def section(title):
    print(f"\n{'─'*55}")
    print(f"  {title}")
    print(f"{'─'*55}")


print("\n" + "="*55)
print("  IncidentIQ — GitHub Integration Status")
print("="*55)

# ── 1. Config ─────────────────────────────────────────────
section("Configuration")
masked_token = (TOKEN[:8] + "..." + TOKEN[-4:]) if len(TOKEN) > 12 else "(not set)"
check("GITHUB_TOKEN",          bool(TOKEN),  masked_token)
check("GITHUB_REPO_OWNER",     bool(OWNER),  OWNER or "(not set)")
check("GITHUB_REPO_NAME",      bool(REPO),   REPO or "(not set)")
check("GITHUB_WEBHOOK_SECRET", bool(SECRET), "(set)" if SECRET else "(not set)")

if not TOKEN:
    print("\n  ❌ Cannot continue — GITHUB_TOKEN not set in .env")
    sys.exit(1)

client = httpx.Client(headers=HEADERS, timeout=10)

# ── 2. Token validity ─────────────────────────────────────
section("Token & User")
try:
    r = client.get("https://api.github.com/user")
    if r.status_code == 200:
        u = r.json()
        check("Token valid",       True,  "")
        check("GitHub login",      True,  u["login"])
        check("Account type",      True,  u["type"])
        scopes = r.headers.get("x-oauth-scopes", "unknown")
        check("Token scopes",      True,  scopes)
        # Check required scopes
        has_repo = "repo" in scopes or "public_repo" in scopes
        check("Has repo scope",    has_repo, "required for PR reviews")
    else:
        check("Token valid", False, f"{r.status_code}: {r.json().get('message','')}")
        sys.exit(1)
except Exception as e:
    check("Token valid", False, str(e))
    sys.exit(1)

if not OWNER or not REPO:
    print("\n  ⚠️  GITHUB_REPO_OWNER / GITHUB_REPO_NAME not set — skipping repo checks")
    sys.exit(0)

# ── 3. Repo access ────────────────────────────────────────
section(f"Repository: {OWNER}/{REPO}")
try:
    r = client.get(f"https://api.github.com/repos/{OWNER}/{REPO}")
    if r.status_code == 200:
        rd = r.json()
        check("Repo accessible",   True,  rd["full_name"])
        check("Visibility",        True,  rd["visibility"])
        check("Default branch",    True,  rd["default_branch"])
        check("Can push",          rd.get("permissions", {}).get("push", False), "")
        check("Can admin",         rd.get("permissions", {}).get("admin", False), "needed for webhooks")
    else:
        check("Repo accessible", False, f"{r.status_code}: {r.json().get('message','')}")
except Exception as e:
    check("Repo accessible", False, str(e))

# ── 4. Webhooks ───────────────────────────────────────────
section("Webhooks")
try:
    r = client.get(f"https://api.github.com/repos/{OWNER}/{REPO}/hooks")
    if r.status_code == 200:
        hooks = r.json()
        if not hooks:
            check("Webhooks registered", False, "none — run: python scripts/setup_webhook.py")
        else:
            check("Webhooks registered", True, f"{len(hooks)} found")
            for h in hooks:
                url = h["config"].get("url", "?")
                active = h["active"]
                events = ", ".join(h.get("events", []))
                is_incidentiq = "github/webhook" in url or "incidentiq" in url.lower()
                check(
                    f"  Hook #{h['id']}",
                    active and is_incidentiq,
                    f"{'ACTIVE' if active else 'INACTIVE'} | {url[:50]} | events: {events}"
                )
    elif r.status_code == 404:
        check("Webhooks", False, "repo not found or no admin access")
    else:
        check("Webhooks", False, f"{r.status_code}: {r.json().get('message','')}")
except Exception as e:
    check("Webhooks", False, str(e))

# ── 5. Open PRs ───────────────────────────────────────────
section("Open Pull Requests")
try:
    r = client.get(f"https://api.github.com/repos/{OWNER}/{REPO}/pulls?state=open&per_page=10")
    if r.status_code == 200:
        prs = r.json()
        if not prs:
            check("Open PRs", True, "none open")
        else:
            check("Open PRs", True, f"{len(prs)} open")
            for pr in prs[:5]:
                print(f"       #{pr['number']:4d}  {pr['title'][:45]:<45}  by {pr['user']['login']}")
    else:
        check("Open PRs", False, f"{r.status_code}")
except Exception as e:
    check("Open PRs", False, str(e))

# ── 6. Recent commits ─────────────────────────────────────
section("Recent Commits (last 5)")
try:
    r = client.get(f"https://api.github.com/repos/{OWNER}/{REPO}/commits?per_page=5")
    if r.status_code == 200:
        commits = r.json()
        for c in commits:
            sha  = c["sha"][:7]
            msg  = c["commit"]["message"].split("\n")[0][:50]
            author = c["commit"]["author"]["name"][:20]
            print(f"       {sha}  {msg:<50}  {author}")
    else:
        check("Commits", False, f"{r.status_code}")
except Exception as e:
    check("Commits", False, str(e))

# ── 7. IncidentIQ webhook endpoint ────────────────────────
section("IncidentIQ Webhook Endpoint")
try:
    import httpx as _h
    r = _h.get("http://localhost:8000/api/github/webhook", timeout=3)
    # GET returns 405 Method Not Allowed — that means the route exists
    check("Route /api/github/webhook", r.status_code in (200, 405, 422),
          f"HTTP {r.status_code} (405=route exists, POST only)")
except Exception as e:
    check("Route /api/github/webhook", False, f"IncidentIQ not running? {e}")

# ── Summary ───────────────────────────────────────────────
print(f"\n{'='*55}")
print("  Next steps:")
print()
print("  1. To register the webhook on GitHub:")
print("     ngrok http 8000")
print("     python scripts/setup_webhook.py")
print()
print("  2. To manually analyze a PR:")
print("     POST http://localhost:8000/api/pr/analyze")
print('     {"repo_owner":"pavankumarry","repo_name":"incidentiq","pr_number":1}')
print()
print("  3. To test PR review without GitHub:")
print("     python scripts/test_pr_review.py")
print(f"{'='*55}\n")

client.close()
