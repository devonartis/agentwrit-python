#!/usr/bin/env python3
"""Check the actual ceiling of the test app."""
import os
import httpx

broker_url = os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")
admin_secret = os.environ.get("AGENTAUTH_ADMIN_SECRET")

if not admin_secret:
    print("Need AGENTAUTH_ADMIN_SECRET to check app ceiling")
    exit(1)

# Get admin token
resp = httpx.post(
    f"{broker_url}/v1/admin/auth",
    json={"secret": admin_secret},
    timeout=10,
)
print(f"Admin auth status: {resp.status_code}")
if resp.status_code != 200:
    print(f"Admin auth failed: {resp.text}")
    exit(1)

admin_token = resp.json()["access_token"]
print(f"Admin token: {admin_token[:30]}...")

# Query apps endpoint
resp = httpx.get(
    f"{broker_url}/v1/admin/apps",
    headers={"Authorization": f"Bearer {admin_token}"},
    timeout=10,
)
print(f"\nApps endpoint status: {resp.status_code}")
if resp.status_code == 200:
    data = resp.json()
    print(f"\nResponse: {data}")
    apps = data.get('apps', [])
    print(f"\nApps found: {len(apps)}")
    for app in apps:
        print(f"\nApp ID: {app.get('client_id')}")
        print(f"  Name: {app.get('name')}")
        print(f"  Scopes: {app.get('scopes')}")
else:
    print(f"Error: {resp.text}")
