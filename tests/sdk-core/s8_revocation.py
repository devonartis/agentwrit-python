#!/usr/bin/env python3
"""SDK-S8: Self-Revocation -- live acceptance test."""

from __future__ import annotations

import os
import sys

import requests

print("""
======================================================================
SDK-S8 -- Self-Revocation: Agent Surrenders Its Credential
======================================================================

Who: The developer.

What: The agent is done with its task and calls revoke_token(). The
broker marks the token's JTI as revoked. The token is now rejected.

Why: Ephemeral credentials should be explicitly released to reduce the
exposure window. The broker logs a token_released audit event.

How to run:
    python tests/sdk-core/s8_revocation.py

Expected: revoke_token() succeeds. Token is invalid afterward.
======================================================================
""")

from agentauth import AgentAuthApp

BROKER: str = os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")
client = AgentAuthApp(
    broker_url=BROKER,
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)

passed: int = 0
failed: int = 0

print("--- Test 1: Revoked token is rejected by broker ---")
try:
    token: str = client.get_token("s8-revoke-agent", ["read:data:*"])
    print(f"  Token: {token[:40]}...")

    before: dict[str, object] = requests.post(
        f"{BROKER}/v1/token/validate", json={"token": token}, timeout=10
    ).json()
    print(f"  Before revoke: valid={before['valid']}")
    assert before["valid"] is True

    client.revoke_token(token)
    print("  revoke_token() called -- no error")

    after: dict[str, object] = requests.post(
        f"{BROKER}/v1/token/validate", json={"token": token}, timeout=10
    ).json()
    print(f"  After revoke:  valid={after['valid']}")
    assert after["valid"] is False
    print("  Result: PASS\n")
    passed += 1
except Exception as e:
    print(f"  FAILED: {e}\n")
    failed += 1

print("======================================================================")
if failed == 0:
    print(f"VERDICT: PASS -- {passed}/{passed + failed} tests passed.")
    print("  Token valid before revoke, invalid after. Clean lifecycle.")
else:
    print(f"VERDICT: FAIL -- {passed}/{passed + failed} tests passed.")
    sys.exit(1)
print("======================================================================")
