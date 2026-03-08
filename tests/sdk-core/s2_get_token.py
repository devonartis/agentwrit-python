#!/usr/bin/env python3
"""SDK-S2: Developer Gets a Token in Three Lines -- live acceptance test."""

from __future__ import annotations

import os
import sys

import requests

print("""
======================================================================
SDK-S2 -- Developer Gets a Token in Three Lines
======================================================================

Who: The developer.

What: The developer calls client.get_token("my-agent", ["read:data:*"])
and gets back a valid JWT. The SDK handles the full 8-step flow: app auth,
launch token, Ed25519 keygen, challenge nonce, sign, register, cache.

Why: This is the entire value proposition. Without the SDK, the developer
writes 40-80 lines of cryptography and HTTP code. The nonce has a 30-second
TTL. The Ed25519 key encoding (raw 32-byte vs DER) is the #1 mistake.

How to run:
    python tests/sdk-core/s2_get_token.py

Expected: get_token returns a valid JWT. Broker validates it with the
correct scope and a SPIFFE-format subject.
======================================================================
""")

from agentauth import AgentAuthClient

BROKER: str = os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")
client = AgentAuthClient(
    broker_url=BROKER,
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)

passed: int = 0
failed: int = 0

print("--- Test 1: get_token returns a valid JWT ---")
try:
    token: str = client.get_token("s2-agent", ["read:data:*"])
    parts: list[str] = token.split(".")
    assert len(parts) == 3, f"Expected 3 JWT parts, got {len(parts)}"
    print(f"  Token: {token[:60]}...")
    print(f"  JWT parts: {len(parts)} (header.payload.signature)")

    result: dict[str, object] = requests.post(
        f"{BROKER}/v1/token/validate", json={"token": token}, timeout=10
    ).json()
    assert result["valid"] is True, f"Broker says invalid: {result}"
    claims: dict[str, object] = result["claims"]  # type: ignore[assignment]
    print(f"  Broker validated: valid={result['valid']}")
    print(f"  Scope: {claims['scope']}")
    print(f"  Subject: {claims['sub']}")
    assert "read:data:*" in claims["scope"]
    assert str(claims["sub"]).startswith("spiffe://")
    print("  Result: PASS\n")
    passed += 1
except Exception as e:
    print(f"  FAILED: {e}\n")
    failed += 1

print("======================================================================")
if failed == 0:
    print(f"VERDICT: PASS -- {passed}/{passed + failed} tests passed.")
    print("  get_token returns a valid JWT with correct scope and SPIFFE sub.")
else:
    print(f"VERDICT: FAIL -- {passed}/{passed + failed} tests passed.")
    sys.exit(1)
print("======================================================================")
