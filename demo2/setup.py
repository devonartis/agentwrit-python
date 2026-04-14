"""One-time setup: register the support ticket demo app with the broker.

Usage:
    ./broker/scripts/stack_up.sh
    uv run python demo2/setup.py
"""

from __future__ import annotations

import os
import sys

import httpx

BROKER_URL = os.environ.get("AGENTAUTH_BROKER_URL", "http://localhost:8080")
ADMIN_SECRET = os.environ.get("AGENTAUTH_ADMIN_SECRET", "")

APP_SCOPE_CEILING = [
    "read:tickets:*",
    "read:customers:*",
    "write:customers:*",
    "read:kb:*",
    "read:billing:*",
    "write:billing:*",
    "write:notes:*",
    "write:email:internal",
    "delete:account:*",
]


def main() -> None:
    if not ADMIN_SECRET:
        print("ERROR: Set AGENTAUTH_ADMIN_SECRET environment variable")
        sys.exit(1)

    print(f"Broker: {BROKER_URL}")

    # Health check
    try:
        health = httpx.get(f"{BROKER_URL}/v1/health", timeout=5)
        health.raise_for_status()
        h = health.json()
        print(f"Broker status: {h['status']} (v{h['version']}, uptime {h['uptime']}s)")
    except Exception as e:
        print(f"ERROR: Cannot reach broker at {BROKER_URL}: {e}")
        sys.exit(1)

    # Authenticate as admin
    print("\nAuthenticating as admin...")
    auth_resp = httpx.post(
        f"{BROKER_URL}/v1/admin/auth",
        json={"secret": ADMIN_SECRET},
        timeout=10,
    )
    if auth_resp.status_code != 200:
        print(f"ERROR: Admin auth failed ({auth_resp.status_code}): {auth_resp.text}")
        sys.exit(1)

    admin_token = auth_resp.json()["access_token"]
    print("Admin authenticated.")

    # Register the demo app
    print("\nRegistering support ticket demo app with scope ceiling:")
    for scope in APP_SCOPE_CEILING:
        print(f"  - {scope}")

    app_resp = httpx.post(
        f"{BROKER_URL}/v1/admin/apps",
        json={
            "name": "support-ticket-demo",
            "scopes": APP_SCOPE_CEILING,
            "token_ttl": 1800,
        },
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )

    if app_resp.status_code not in (200, 201):
        print(f"ERROR: App registration failed ({app_resp.status_code}): {app_resp.text}")
        sys.exit(1)

    app_data = app_resp.json()

    print("\nApp registered successfully!")
    print(f"  app_id:        {app_data['app_id']}")
    print(f"  client_id:     {app_data['client_id']}")
    print(f"  client_secret: {app_data['client_secret']}")
    print(f"  scopes:        {app_data['scopes']}")

    print(f"\n{'='*60}")
    print("Add these to demo2/.env:")
    print(f"{'='*60}")
    print(f"AGENTAUTH_BROKER_URL={BROKER_URL}")
    print(f"AGENTAUTH_CLIENT_ID={app_data['client_id']}")
    print(f"AGENTAUTH_CLIENT_SECRET={app_data['client_secret']}")
    print(f"AGENTAUTH_ADMIN_SECRET={ADMIN_SECRET}")
    print("LLM_BASE_URL=<your-llm-base-url>")
    print("LLM_API_KEY=<your-api-key>")
    print("LLM_MODEL=<your-model>")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
