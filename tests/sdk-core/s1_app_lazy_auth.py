#!/usr/bin/env python3
"""STORY-P3-S1: App Authenticates on First Agent Request

The app is running. An agent task comes in. The app has never talked to
the broker yet. On the first create_agent() call, the SDK authenticates
automatically and creates the agent — no setup step needed at runtime.
"""
import os
import sys

print()
print("╔══════════════════════════════════════════════════════════════════╗")
print("║  App Authenticates on First Agent Request (STORY-P3-S1)         ║")
print("║                                                                  ║")
print("║  The app starts up. A task arrives. The SDK handles broker       ║")
print("║  authentication transparently on the first create_agent() call.  ║")
print("╚══════════════════════════════════════════════════════════════════╝")
print()

from agentwrit import AgentWritApp

broker_url = os.environ["AGENTWRIT_BROKER_URL"]
client_id = os.environ["AGENTWRIT_CLIENT_ID"]
client_secret = os.environ["AGENTWRIT_CLIENT_SECRET"]

print("Step 1: App starts up")
app = AgentWritApp(broker_url=broker_url, client_id=client_id, client_secret=client_secret)
print("  App initialized (no broker call yet)")
print()

print("Step 2: First task arrives — create an agent for user-42")
agent = app.create_agent(
    orch_id="data-pipeline", task_id="analyze-user-42",
    requested_scope=["read:data:user-42"],
)
print(f"  agent_id   = {agent.agent_id}")
print(f"  scope      = {agent.scope}")
print(f"  expires_in = {agent.expires_in}s")
print()

print("Step 3: Verifying")
passed = True

if agent.agent_id.startswith("spiffe://"):
    print("  PASS: agent has a SPIFFE identity")
else:
    print(f"  FAIL: agent_id is {agent.agent_id!r}")
    passed = False

if agent.scope == ["read:data:user-42"]:
    print("  PASS: agent is scoped to user-42 only")
else:
    print(f"  FAIL: scope is {agent.scope}")
    passed = False

agent.release()
print("  Agent released")

print()
if passed:
    print("═══ STORY-P3-S1: PASS ═══")
else:
    print("═══ STORY-P3-S1: FAIL ═══")
    sys.exit(1)
