#!/usr/bin/env python3
"""SDK-S5: Clear Error Messages for Scope Violations -- live acceptance test."""

from __future__ import annotations

import os
import sys

print("""
======================================================================
SDK-S5 -- Clear Error Messages for Scope Violations
======================================================================

Who: The developer.

What: The developer requests a scope their app is not allowed to use.
The SDK raises ScopeCeilingError with a message that tells them exactly
what went wrong -- not a generic 403.

Why: Scope errors are the most common developer mistake. A clear error
message saves debugging time and prevents support tickets.

How to run:
    python tests/sdk-core/s5_scope_error.py

Expected: ScopeCeilingError raised with actionable message mentioning
the app's scope ceiling.
======================================================================
""")

from agentauth import AgentAuthApp, ScopeCeilingError

BROKER: str = os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")
client = AgentAuthApp(
    broker_url=BROKER,
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)

passed: int = 0
failed: int = 0

print("--- Test 1: Scope exceeding ceiling raises ScopeCeilingError ---")
try:
    client.get_token("s5-agent", ["admin:everything:*"])
    print("  FAILED: No exception raised\n")
    failed += 1
except ScopeCeilingError as e:
    print(f"  ScopeCeilingError raised: {e}")
    print(f"  Status code: {e.status_code}")
    assert e.status_code == 403
    print("  Result: PASS\n")
    passed += 1
except Exception as e:
    print(f"  FAILED: Wrong exception: {type(e).__name__}: {e}\n")
    failed += 1

print("======================================================================")
if failed == 0:
    print(f"VERDICT: PASS -- {passed}/{passed + failed} tests passed.")
    print("  ScopeCeilingError raised with clear message about the ceiling.")
else:
    print(f"VERDICT: FAIL -- {passed}/{passed + failed} tests passed.")
    sys.exit(1)
print("======================================================================")
