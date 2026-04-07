#!/usr/bin/env python3
"""STORY-P3-S8: App Catches Revoked Agent at Runtime

An agent is working. The operator revokes it (incident response).
The app validates the agent's token before the next tool call and
discovers it's been revoked. The app blocks the agent from proceeding.

This is the zero-trust pattern: validate before every sensitive action.
"""
import os
import sys

print()
print("╔══════════════════════════════════════════════════════════════════╗")
print("║  App Catches Revoked Agent at Runtime (STORY-P3-S8)            ║")
print("║                                                                  ║")
print("║  An agent's token is released (simulating operator revocation). ║")
print("║  The app validates the token before the next tool call and      ║")
print("║  discovers it's invalid. The agent is blocked.                  ║")
print("╚══════════════════════════════════════════════════════════════════╝")
print()

from agentauth import AgentAuthApp, scope_is_subset, validate

broker_url = os.environ["AGENTAUTH_BROKER_URL"]
client_id = os.environ["AGENTAUTH_CLIENT_ID"]
client_secret = os.environ["AGENTAUTH_CLIENT_SECRET"]

app = AgentAuthApp(broker_url=broker_url, client_id=client_id, client_secret=client_secret)

print("Step 1: Agent starts working on user-42")
agent = app.create_agent(
    orch_id="data-pipeline", task_id="work-user-42",
    requested_scope=["read:data:user-42"],
)
print(f"  agent_id = {agent.agent_id}")
print(f"  scope    = {agent.scope}")
print()

print("Step 2: Validate before first tool call — should be valid")
result1 = app.validate(agent.access_token)
print(f"  valid = {result1.valid}")
if result1.claims:
    print(f"  sub   = {result1.claims.sub}")
print()

print("Step 3: Token is released (simulating revocation)")
agent.release()
print("  Agent released")
print()

print("Step 4: Validate before next tool call — should be invalid")
result2 = app.validate(agent.access_token)
print(f"  valid = {result2.valid}")
if result2.error:
    print(f"  error = {result2.error!r}")
print()

print("Step 5: App gates tool access using validation result")
tool_blocked = False
if not result2.valid:
    tool_blocked = True
    print("  App blocked tool execution: agent token is no longer valid")
else:
    print("  App allowed tool execution (THIS SHOULD NOT HAPPEN)")
print()

print("Step 6: Verifying")
passed = True

if result1.valid is True:
    print("  PASS: first validation succeeded (agent was active)")
else:
    print("  FAIL: first validation failed")
    passed = False

if result2.valid is False:
    print("  PASS: second validation failed (agent was revoked)")
else:
    print("  FAIL: second validation succeeded — revoked agent still valid")
    passed = False

if tool_blocked:
    print("  PASS: tool execution was blocked")
else:
    print("  FAIL: tool execution was not blocked")
    passed = False

print()
if passed:
    print("═══ STORY-P3-S8: PASS ═══")
else:
    print("═══ STORY-P3-S8: FAIL ═══")
    sys.exit(1)
