"""
IncidentIQ - GitHub Webhook Setup
Registers the IncidentIQ webhook on your GitHub repo automatically.
Supports both ngrok (local dev) and a real public URL (production).

Run: python scripts/setup_webhook.py
"""
import os, sys, json, secrets
from pathlib import Path

env_path = Path(__file__).parent.parent / ".env"
if env_path.exists():
    for line in env_path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, _, v = line.partition("=")
            os.environ.setdefault(k.strip(), v.strip())

import httpx

GITHUB_TOKEN  = os.environ.get("GITHUB_TOKEN", "")
REPO_OWNER    = os.environ.get("GITHUB_REPO_OWNER", "")
REPO_NAME     = os.environ.get("GITHUB_REPO_NAME", "")
WEBHOOK_SECRET = os.environ.get("GITHUB_WEBHOOK_SECRET", "")
PUBLIC_URL    = os.environ.get("INCIDENTIQ_PUBLIC_URL", "")  # e.g. https://abc123.ngrok.io


def get_ngrok_url() -> str:
    """Try to get the current ngrok public URL from the local ngrok API."""
    try:
        resp = httpx.get("http://localhost:4040/api/tunnels", timeout=3)
        tunnels = resp.json().get("tunnels", [])
        for t in tunnels:
            if t.get("proto") == "https":
                return t["public_url"]
        for t in tunnels:
            if t.get("proto") == "http":
                return t["public_url"].replace("http://", "https://")
    except Exception:
        pass
    return ""


def register_webhook(public_url: str, secret: str) -> dict:
    """Register the webhook on GitHub."""
    webhook_url = f"{public_url}/api/github/webhook"
    payload = {
        "name": "web",
        "active": True,
        "events": ["pull_request"],
        "config": {
            "url": webhook_url,
            "content_type": "json",
            "secret": secret,
            "insecure_ssl": "0",
        },
    }
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    resp = httpx.post(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks",
        headers=headers,
        json=payload,
        timeout=15,
    )
    resp.raise_for_status()
    return resp.json()


def list_webhooks() -> list:
    headers = {
        "Authorization": f"Bearer {GITHUB_TOKEN}",
        "Accept": "application/vnd.github+json",
    }
    resp = httpx.get(
        f"https://api.github.com/repos/{REPO_OWNER}/{REPO_NAME}/hooks",
        headers=headers,
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def main():
    print("\n" + "="*60)
    print("  IncidentIQ — GitHub Webhook Setup")
    print("="*60 + "\n")

    # Validate config
    if not GITHUB_TOKEN:
        print("❌ GITHUB_TOKEN not set in .env")
        sys.exit(1)
    if not REPO_OWNER or not REPO_NAME:
        print("❌ GITHUB_REPO_OWNER / GITHUB_REPO_NAME not set in .env")
        sys.exit(1)

    print(f"  Repo   : {REPO_OWNER}/{REPO_NAME}")

    # Determine public URL
    public_url = PUBLIC_URL
    if not public_url:
        print("  Checking for ngrok tunnel...")
        public_url = get_ngrok_url()
        if public_url:
            print(f"  ✅ ngrok URL detected: {public_url}")
        else:
            print("  ⚠️  No ngrok tunnel found and INCIDENTIQ_PUBLIC_URL not set.")
            print()
            print("  To expose your local server:")
            print("  1. Install ngrok: https://ngrok.com/download")
            print("  2. Run: ngrok http 8000")
            print("  3. Re-run this script")
            print()
            print("  Or set INCIDENTIQ_PUBLIC_URL=https://your-domain.com in .env")
            sys.exit(1)

    # Generate webhook secret if not set
    secret = WEBHOOK_SECRET
    if not secret:
        secret = secrets.token_hex(32)
        print(f"\n  Generated webhook secret: {secret}")
        print(f"  Add to .env: GITHUB_WEBHOOK_SECRET={secret}\n")

    webhook_endpoint = f"{public_url}/api/github/webhook"
    print(f"  Webhook URL: {webhook_endpoint}")

    # Check existing webhooks
    try:
        existing = list_webhooks()
        for hook in existing:
            if "incidentiq" in hook.get("config", {}).get("url", "").lower() or \
               "github/webhook" in hook.get("config", {}).get("url", "").lower():
                print(f"\n  ⚠️  Existing webhook found (id={hook['id']}): {hook['config']['url']}")
                print("  Delete it first or update INCIDENTIQ_PUBLIC_URL if URL changed.")
    except Exception as e:
        print(f"  Could not list existing webhooks: {e}")

    # Register
    print(f"\n  Registering webhook on {REPO_OWNER}/{REPO_NAME}...")
    try:
        result = register_webhook(public_url, secret)
        print(f"  ✅ Webhook registered! ID: {result['id']}")
        print(f"  Events: {result['events']}")
        print(f"  URL: {result['config']['url']}")
        print()
        print("  Now push a PR to your repo — IncidentIQ will auto-review it!")
        print("  Watch the server logs: the review will appear as a PR comment.")
    except httpx.HTTPStatusError as e:
        print(f"  ❌ Failed: {e.response.status_code} — {e.response.text}")
        sys.exit(1)

    print("\n" + "="*60 + "\n")


if __name__ == "__main__":
    main()
