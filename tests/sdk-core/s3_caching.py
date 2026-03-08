#!/usr/bin/env python3
"""SDK-S3: Token Caching -- live acceptance test."""

from __future__ import annotations

import os
import sys
import time

print("""
======================================================================
SDK-S3 -- Token Caching and Automatic Renewal
======================================================================

Who: The developer.

What: The developer calls get_token twice with the same agent name and
scope. The second call returns the cached token instantly without
hitting the broker again.

Why: Without caching, every get_token triggers 3 HTTP calls and a
keypair generation. A loop calling get_token would hammer the broker.

How to run:
    python tests/sdk-core/s3_caching.py

Expected: Second call returns the same JWT. No extra broker calls.
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

print("--- Test 1: Second call returns cached token ---")
try:
    t0: float = time.monotonic()
    token1: str = client.get_token("s3-cache-agent", ["read:data:*"])
    t1: float = time.monotonic()
    token2: str = client.get_token("s3-cache-agent", ["read:data:*"])
    t2: float = time.monotonic()

    print(f"  Call 1: {(t1-t0)*1000:.0f}ms -> {token1[:40]}...")
    print(f"  Call 2: {(t2-t1)*1000:.0f}ms -> {token2[:40]}...")
    print(f"  Tokens match: {token1 == token2}")
    assert token1 == token2, "Tokens differ -- cache miss!"
    print("  Result: PASS\n")
    passed += 1
except Exception as e:
    print(f"  FAILED: {e}\n")
    failed += 1

print("--- Test 2: Different scope = different cache entry ---")
try:
    token_a: str = client.get_token("s3-scope-agent", ["read:data:*"])
    token_b: str = client.get_token("s3-scope-agent", ["read:data:logs"])
    print(f"  read:data:*    -> {token_a[:40]}...")
    print(f"  read:data:logs -> {token_b[:40]}...")
    print(f"  Tokens differ: {token_a != token_b}")
    assert token_a != token_b, "Same token for different scopes!"
    print("  Result: PASS\n")
    passed += 1
except Exception as e:
    print(f"  FAILED: {e}\n")
    failed += 1

print("======================================================================")
if failed == 0:
    print(f"VERDICT: PASS -- {passed}/{passed + failed} tests passed.")
    print("  Cache hit on identical args. Different scopes = different tokens.")
else:
    print(f"VERDICT: FAIL -- {passed}/{passed + failed} tests passed.")
    sys.exit(1)
print("======================================================================")
