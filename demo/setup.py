"""One-time setup: register the MedAssist demo app with the broker.

Authenticates as admin, creates the app with a wide scope ceiling,
and prints the client_id/client_secret for .env configuration.

Usage:
    # Start broker first
    ./broker/scripts/stack_up.sh

    # Run setup
    uv run python demo/setup.py
"""

from __future__ import annotations

import os
import sys

import httpx

BROKER_URL = os.environ.get("AGENTAUTH_BROKER_URL", "http://localhost:8080")
ADMIN_SECRET = os.environ.get("AGENTAUTH_ADMIN_SECRET", "")

APP_SCOPE_CEILING = [
    "read:records:*",
    "write:records:*",
    "read:labs:*",
    "write:prescriptions:*",
    "read:formulary:*",
    "read:billing:*",
    "write:billing:*",
    "read:insurance:*",
]


def main() -> None:
    if not ADMIN_SECRET:
        print("ERROR: Set AGENTAUTH_ADMIN_SECRET environment variable")
        print("  export AGENTAUTH_ADMIN_SECRET=<your-admin-secret>")
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
        print("  Start the broker first: ./broker/scripts/stack_up.sh")
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
    print(f"\nRegistering MedAssist demo app with scope ceiling:")
    for scope in APP_SCOPE_CEILING:
        print(f"  - {scope}")

    app_resp = httpx.post(
        f"{BROKER_URL}/v1/admin/apps",
        json={
            "name": "medassist-demo",
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
    client_id = app_data["client_id"]
    client_secret = app_data["client_secret"]

    print(f"\nApp registered successfully!")
    print(f"  app_id:        {app_data['app_id']}")
    print(f"  client_id:     {client_id}")
    print(f"  client_secret: {client_secret}")
    print(f"  scopes:        {app_data['scopes']}")
    print(f"  token_ttl:     {app_data['token_ttl']}s")

    print(f"\n{'='*60}")
    print("Add these to demo/.env:")
    print(f"{'='*60}")
    print(f"AGENTAUTH_BROKER_URL={BROKER_URL}")
    print(f"AGENTAUTH_CLIENT_ID={client_id}")
    print(f"AGENTAUTH_CLIENT_SECRET={client_secret}")
    print(f"AGENTAUTH_ADMIN_SECRET={ADMIN_SECRET}")
    print(f"OPENAI_API_KEY=<your-openai-key>")
    print(f"{'='*60}")


if __name__ == "__main__":
    main()
