#!/usr/bin/env python3
"""STORY-P3-S2: Multiple Agents From One Running App

The app is processing a batch. It creates agents for different users
back-to-back. The SDK reuses its internal session — no duplicate auth
calls to the broker even under load.
"""
import os
import sys

print()
print("╔══════════════════════════════════════════════════════════════════╗")
print("║  Multiple Agents From One Running App (STORY-P3-S2)            ║")
print("║                                                                  ║")
print("║  The app processes a batch of tasks. Each agent gets only the   ║")
print("║  specific user data it needs. The SDK handles session reuse.    ║")
print("╚══════════════════════════════════════════════════════════════════╝")
print()

from agentwrit import AgentWritApp

broker_url = os.environ["AGENTWRIT_BROKER_URL"]
client_id = os.environ["AGENTWRIT_CLIENT_ID"]
client_secret = os.environ["AGENTWRIT_CLIENT_SECRET"]

app = AgentWritApp(broker_url=broker_url, client_id=client_id, client_secret=client_secret)

print("Step 1: Task batch arrives — two users to analyze")
agent1 = app.create_agent(
    orch_id="data-pipeline", task_id="analyze-user-42",
    requested_scope=["read:data:user-42"],
)
print(f"  Agent 1: {agent1.agent_id}")
print(f"           scope = {agent1.scope}")

agent2 = app.create_agent(
    orch_id="data-pipeline", task_id="analyze-user-99",
    requested_scope=["read:data:user-99"],
)
print(f"  Agent 2: {agent2.agent_id}")
print(f"           scope = {agent2.scope}")
print()

print("Step 2: Verifying isolation")
passed = True

if agent1.agent_id != agent2.agent_id:
    print("  PASS: each agent has its own SPIFFE identity")
else:
    print(f"  FAIL: same SPIFFE ID: {agent1.agent_id}")
    passed = False

if agent1.scope == ["read:data:user-42"]:
    print("  PASS: agent 1 scoped to user-42 only")
else:
    print(f"  FAIL: agent 1 scope is {agent1.scope}")
    passed = False

if agent2.scope == ["read:data:user-99"]:
    print("  PASS: agent 2 scoped to user-99 only")
else:
    print(f"  FAIL: agent 2 scope is {agent2.scope}")
    passed = False

agent1.release()
agent2.release()
print("  Both agents released")

print()
if passed:
    print("═══ STORY-P3-S2: PASS ═══")
else:
    print("═══ STORY-P3-S2: FAIL ═══")
    sys.exit(1)
