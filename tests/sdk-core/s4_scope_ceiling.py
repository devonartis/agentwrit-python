#!/usr/bin/env python3
"""STORY-P3-S4: Scope Ceiling Enforcement

Who:  A developer whose app has ceiling [read:data:*, write:data:*].
What: The broker rejects agent creation when the requested scope
      falls outside the app's ceiling entirely.
Why:  The operator controls what the app can do. The SDK must surface
      that rejection clearly as AuthorizationError.
"""
import os
import sys

print()
print("╔══════════════════════════════════════════════════════════════════╗")
print("║  Scope Ceiling Blocks Out-of-Bounds Agent Scope (STORY-P3-S4)  ║")
print("║                                                                  ║")
print("║  A developer's app has ceiling [read:data:*, write:data:*].     ║")
print("║  They try to create an agent with read:logs:system — a scope    ║")
print("║  the operator never granted. The broker rejects it with 403.    ║")
print("╚══════════════════════════════════════════════════════════════════╝")
print()

from agentauth import AgentAuthApp
from agentauth.errors import AuthorizationError

broker_url = os.environ["AGENTAUTH_BROKER_URL"]
client_id = os.environ["AGENTAUTH_CLIENT_ID"]
client_secret = os.environ["AGENTAUTH_CLIENT_SECRET"]

app = AgentAuthApp(broker_url=broker_url, client_id=client_id, client_secret=client_secret)

print("Step 1: Setup")
print("  App ceiling     = [read:data:*, write:data:*]")
print("  Requested scope = [read:logs:system]  (outside ceiling)")
print()

print("Step 2: Calling app.create_agent() with out-of-bounds scope")
passed = True
try:
    app.create_agent(
        orch_id="data-pipeline",
        task_id="log-reader",
        requested_scope=["read:logs:system"],
    )
    print("  FAIL: No exception raised — agent was created when it shouldn't have been")
    passed = False
except AuthorizationError as e:
    print(f"  Exception type     = AuthorizationError")
    print(f"  status_code        = {e.status_code}")
    print(f"  problem.detail     = {e.problem.detail!r}")
    print(f"  problem.error_code = {e.problem.error_code!r}")
    print()
    if e.status_code == 403:
        print("  PASS: broker returned 403, SDK raised AuthorizationError")
    else:
        print(f"  FAIL: status_code is {e.status_code}, expected 403")
        passed = False
except Exception as e:
    print(f"  FAIL: wrong exception type: {type(e).__name__}: {e}")
    passed = False

print()
if passed:
    print("═══ STORY-P3-S4: PASS ═══")
else:
    print("═══ STORY-P3-S4: FAIL ═══")
    sys.exit(1)
