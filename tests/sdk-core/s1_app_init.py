#!/usr/bin/env python3
"""SDK-S1: Developer Initializes the Client -- live acceptance test."""

from __future__ import annotations

import os
import sys

# Banner
print("""
======================================================================
SDK-S1 -- Developer Initializes the Client
======================================================================

Who: The developer.

What: The developer creates an AgentAuthClient with their broker URL,
client_id, and client_secret. The SDK authenticates the app with the
broker via POST /v1/app/auth behind the scenes. The developer writes
three lines and gets a working client back.

Why: This is the entry point for every SDK interaction. If init fails
or requires extra steps, the entire "3 lines to a token" promise breaks.

How to run:
    export AGENTAUTH_BROKER_URL=http://127.0.0.1:8080
    export AGENTAUTH_CLIENT_ID=<from broker registration>
    export AGENTAUTH_CLIENT_SECRET=<from broker registration>
    python tests/sdk-core/s1_app_init.py

Expected: Client is created without error. repr() shows broker_url and
client_id but never the client_secret.
======================================================================
""")

from agentauth import AgentAuthClient
from agentauth.errors import AuthenticationError

BROKER_URL: str = os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")
CLIENT_ID: str = os.environ["AGENTAUTH_CLIENT_ID"]
CLIENT_SECRET: str = os.environ["AGENTAUTH_CLIENT_SECRET"]

passed: int = 0
failed: int = 0

# Test 1: Valid credentials
print("--- Test 1: Initialize with valid credentials ---")
try:
    client = AgentAuthClient(
        broker_url=BROKER_URL,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
    )
    print(f"  Client created: {repr(client)}")
    assert CLIENT_SECRET not in repr(client), "SECURITY FAILURE: secret in repr!"
    print(f"  Secret not in repr: CONFIRMED")
    print("  Result: PASS\n")
    passed += 1
except Exception as e:
    print(f"  FAILED: {e}\n")
    failed += 1

# Test 2: Wrong credentials
print("--- Test 2: Wrong credentials raise AuthenticationError ---")
try:
    AgentAuthClient(
        broker_url=BROKER_URL,
        client_id="wrong-id",
        client_secret="wrong-secret",
    )
    print("  FAILED: No exception raised\n")
    failed += 1
except AuthenticationError as e:
    print(f"  AuthenticationError raised: {e}")
    assert "wrong-secret" not in str(e), "SECURITY FAILURE: secret in error!"
    print(f"  Secret not in error message: CONFIRMED")
    print("  Result: PASS\n")
    passed += 1
except Exception as e:
    print(f"  FAILED: Wrong exception type: {type(e).__name__}: {e}\n")
    failed += 1

# Verdict
print("======================================================================")
if failed == 0:
    print(f"VERDICT: PASS -- {passed}/{passed + failed} tests passed.")
    print("  Client initializes in 3 lines. Secret never exposed.")
    print("======================================================================")
else:
    print(f"VERDICT: FAIL -- {passed}/{passed + failed} tests passed.")
    print("======================================================================")
    sys.exit(1)
