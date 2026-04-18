#!/usr/bin/env python3
"""STORY-P3-S3: Agent Gets a Verifiable SPIFFE Identity

A task arrives. The app creates an agent with a narrow scope. The agent
receives a SPIFFE identity and a JWT that the broker can verify. This
proves the agent is a real principal in the trust domain, not just a
token string.
"""
import os
import sys

print()
print("╔══════════════════════════════════════════════════════════════════╗")
print("║  Agent Gets a Verifiable SPIFFE Identity (STORY-P3-S3)         ║")
print("║                                                                  ║")
print("║  A task arrives to analyze user-42's data. The app creates an   ║")
print("║  agent scoped to read:data:user-42. The broker issues a SPIFFE  ║")
print("║  identity and a JWT. The app validates the token to confirm     ║")
print("║  the agent is real before letting it work.                      ║")
print("╚══════════════════════════════════════════════════════════════════╝")
print()

from agentwrit import AgentWritApp, validate

broker_url = os.environ["AGENTWRIT_BROKER_URL"]
client_id = os.environ["AGENTWRIT_CLIENT_ID"]
client_secret = os.environ["AGENTWRIT_CLIENT_SECRET"]

app = AgentWritApp(broker_url=broker_url, client_id=client_id, client_secret=client_secret)

print("Step 1: Task arrives — create agent for user-42 analysis")
agent = app.create_agent(
    orch_id="data-pipeline", task_id="analyze-user-42",
    requested_scope=["read:data:user-42"],
)
print(f"  agent_id   = {agent.agent_id}")
print(f"  scope      = {agent.scope}")
print(f"  expires_in = {agent.expires_in}s")
print()

print("Step 2: App validates the agent's token with the broker")
result = validate(broker_url, agent.access_token)
print(f"  valid          = {result.valid}")
if result.claims:
    print(f"  claims.sub     = {result.claims.sub}")
    print(f"  claims.scope   = {result.claims.scope}")
    print(f"  claims.task_id = {result.claims.task_id}")
    print(f"  claims.orch_id = {result.claims.orch_id}")
print()

print("Step 3: Verifying")
passed = True

if agent.agent_id.startswith("spiffe://"):
    print("  PASS: agent_id is a SPIFFE URI")
else:
    print(f"  FAIL: agent_id is {agent.agent_id!r}")
    passed = False

if "data-pipeline" in agent.agent_id and "analyze-user-42" in agent.agent_id:
    print("  PASS: orch_id and task_id appear in SPIFFE ID")
else:
    print(f"  FAIL: SPIFFE ID missing orch/task: {agent.agent_id}")
    passed = False

if result.valid is True:
    print("  PASS: broker confirms token is valid")
else:
    print("  FAIL: broker says token is not valid")
    passed = False

if result.claims and result.claims.sub == agent.agent_id:
    print("  PASS: broker claims.sub matches agent_id")
else:
    print("  FAIL: claims.sub mismatch")
    passed = False

if result.claims and result.claims.scope == ["read:data:user-42"]:
    print("  PASS: broker confirms scope is exactly read:data:user-42")
else:
    print(f"  FAIL: broker scope is {result.claims.scope if result.claims else 'N/A'}")
    passed = False

agent.release()
print()
print("Step 4: Agent released")

print()
if passed:
    print("═══ STORY-P3-S3: PASS ═══")
else:
    print("═══ STORY-P3-S3: FAIL ═══")
    sys.exit(1)
