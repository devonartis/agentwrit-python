#!/usr/bin/env python3
"""SDK-S7: Delegation -- live acceptance test."""

from __future__ import annotations

import os
import sys

import requests

print("""
======================================================================
SDK-S7 -- Delegation: Agent Grants Attenuated Scope to Another
======================================================================

Who: The developer.

What: Agent A holds read:data:* and delegates read:data:results to
Agent B. The broker enforces that the delegated scope is a subset.

Why: Multi-agent workflows need permission sharing without over-
provisioning. The broker enforces scope attenuation cryptographically.

How to run:
    python tests/sdk-core/s7_delegation.py

Expected: Delegated JWT has read:data:results scope -- narrower than
the delegating agent's read:data:*.
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

print("--- Test 1: Delegate returns attenuated token ---")
try:
    agent_token: str = client.get_token("s7-delegator", ["read:data:*"])
    print(f"  Delegator token: {agent_token[:40]}...")

    delegate_token: str = client.get_token("s7-delegate", ["read:data:logs"], task_id="s7")
    delegate_claims: dict[str, object] = requests.post(
        f"{BROKER}/v1/token/validate", json={"token": delegate_token}, timeout=10
    ).json()["claims"]
    delegate_id: str = str(delegate_claims["sub"])
    print(f"  Delegate agent: {delegate_id}")

    delegated: str = client.delegate(
        token=agent_token, to_agent_id=delegate_id,
        scope=["read:data:results"], ttl=60,
    )
    print(f"  Delegated token: {delegated[:40]}...")

    result: dict[str, object] = requests.post(
        f"{BROKER}/v1/token/validate", json={"token": delegated}, timeout=10
    ).json()
    claims: dict[str, object] = result["claims"]  # type: ignore[assignment]
    print(f"  Delegated scope: {claims['scope']}")
    assert "read:data:results" in claims["scope"]
    assert "read:data:*" not in claims["scope"]
    print("  Scope attenuated correctly!")
    print("  Result: PASS\n")
    passed += 1
except Exception as e:
    print(f"  FAILED: {e}\n")
    failed += 1

print("======================================================================")
if failed == 0:
    print(f"VERDICT: PASS -- {passed}/{passed + failed} tests passed.")
else:
    print(f"VERDICT: FAIL -- {passed}/{passed + failed} tests passed.")
    sys.exit(1)
print("======================================================================")
