#!/usr/bin/env python3
"""STORY-P3-S6: Agent Releases Token When Task Completes

An agent finishes processing user-42's data. The app calls release().
The token is immediately revoked at the broker. If the agent was
compromised and someone captured its token, it's already dead.
"""
import os
import sys

print()
print("╔══════════════════════════════════════════════════════════════════╗")
print("║  Agent Releases Token When Task Completes (STORY-P3-S6)        ║")
print("║                                                                  ║")
print("║  An agent finishes its task and releases its token. The broker  ║")
print("║  revokes it immediately. Any captured copy of the token is now  ║")
print("║  useless — the window of exposure is minimized.                 ║")
print("╚══════════════════════════════════════════════════════════════════╝")
print()

from agentauth import AgentAuthApp, validate
from agentauth.errors import AgentAuthError

broker_url = os.environ["AGENTAUTH_BROKER_URL"]
client_id = os.environ["AGENTAUTH_CLIENT_ID"]
client_secret = os.environ["AGENTAUTH_CLIENT_SECRET"]

app = AgentAuthApp(broker_url=broker_url, client_id=client_id, client_secret=client_secret)

print("Step 1: Agent starts working on user-42")
agent = app.create_agent(
    orch_id="data-pipeline", task_id="short-task-user-42",
    requested_scope=["read:data:user-42"],
)
captured_token = agent.access_token
print(f"  agent_id = {agent.agent_id}")
print(f"  token    = {captured_token[:30]}...")
print()

print("Step 2: Task completes — release the agent")
agent.release()
print("  Agent released")
print()

print("Step 3: Verify the token is dead at the broker")
result = validate(broker_url, captured_token)
print(f"  captured token valid = {result.valid}")
print()

print("Step 4: Verify the agent can't be used after release")
renew_blocked = False
try:
    agent.renew()
except AgentAuthError as e:
    renew_blocked = True
    print(f"  agent.renew() raised: {e}")

delegate_blocked = False
try:
    agent.delegate(delegate_to="spiffe://x", scope=["read:data:user-42"])
except AgentAuthError as e:
    delegate_blocked = True
    print(f"  agent.delegate() raised: {e}")
print()

print("Step 5: Verifying")
passed = True

if result.valid is False:
    print("  PASS: released token is invalid at broker")
else:
    print("  FAIL: released token is still valid — security risk")
    passed = False

if renew_blocked:
    print("  PASS: renew() blocked after release")
else:
    print("  FAIL: renew() succeeded after release")
    passed = False

if delegate_blocked:
    print("  PASS: delegate() blocked after release")
else:
    print("  FAIL: delegate() succeeded after release")
    passed = False

print()
if passed:
    print("═══ STORY-P3-S6: PASS ═══")
else:
    print("═══ STORY-P3-S6: FAIL ═══")
    sys.exit(1)
