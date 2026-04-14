#!/usr/bin/env python3
"""STORY-P3-S5: Agent Renews Token During Long Task

An agent is processing user-42's data. The task is long-running and the
token will expire. The app renews the agent's token. The agent keeps its
identity and scope. The old token is revoked — if someone captured it,
it's useless now.
"""
import os
import sys

print()
print("╔══════════════════════════════════════════════════════════════════╗")
print("║  Agent Renews Token During Long Task (STORY-P3-S5)             ║")
print("║                                                                  ║")
print("║  An agent processing user-42's data needs a fresh token.        ║")
print("║  After renewal: same identity, same scope, new token.           ║")
print("║  The old token is revoked — captured tokens become useless.     ║")
print("╚══════════════════════════════════════════════════════════════════╝")
print()

from agentwrit import AgentWritApp, validate

broker_url = os.environ["AGENTWRIT_BROKER_URL"]
client_id = os.environ["AGENTWRIT_CLIENT_ID"]
client_secret = os.environ["AGENTWRIT_CLIENT_SECRET"]

app = AgentWritApp(broker_url=broker_url, client_id=client_id, client_secret=client_secret)

print("Step 1: Agent starts working on user-42")
agent = app.create_agent(
    orch_id="data-pipeline", task_id="long-task-user-42",
    requested_scope=["read:data:user-42"],
)
old_token = agent.access_token
old_id = agent.agent_id
print(f"  agent_id = {agent.agent_id}")
print(f"  scope    = {agent.scope}")
print(f"  token    = {old_token[:30]}...")
print()

print("Step 2: Token is about to expire — renew it")
agent.renew()
print(f"  new token    = {agent.access_token[:30]}...")
print(f"  agent_id     = {agent.agent_id}")
print(f"  scope        = {agent.scope}")
print(f"  expires_in   = {agent.expires_in}s")
print()

print("Step 3: Verifying renewal")
passed = True

if agent.access_token != old_token:
    print("  PASS: token changed")
else:
    print("  FAIL: token is the same")
    passed = False

if agent.agent_id == old_id:
    print("  PASS: identity unchanged")
else:
    print(f"  FAIL: identity changed from {old_id} to {agent.agent_id}")
    passed = False

if agent.scope == ["read:data:user-42"]:
    print("  PASS: scope unchanged")
else:
    print(f"  FAIL: scope changed to {agent.scope}")
    passed = False
print()

print("Step 4: New token is valid")
new_result = validate(broker_url, agent.access_token)
print(f"  new token valid = {new_result.valid}")
if new_result.valid is True:
    print("  PASS: renewed token is valid")
else:
    print("  FAIL: renewed token is not valid")
    passed = False
print()

print("Step 5: Old token is revoked (attacker can't use it)")
old_result = validate(broker_url, old_token)
print(f"  old token valid = {old_result.valid}")
if old_result.valid is False:
    print("  PASS: old token is revoked")
else:
    print("  FAIL: old token is still valid — security risk")
    passed = False

agent.release()
print()
print("Step 6: Agent released")

print()
if passed:
    print("═══ STORY-P3-S5: PASS ═══")
else:
    print("═══ STORY-P3-S5: FAIL ═══")
    sys.exit(1)
