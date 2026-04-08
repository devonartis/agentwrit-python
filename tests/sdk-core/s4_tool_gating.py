#!/usr/bin/env python3
"""STORY-P3-S4: App Blocks Rogue Agent From Unauthorized Tool

An agent was created with read:data:user-42. At runtime, the agent
(possibly compromised by prompt injection) tries to call a tool that
requires read:data:user-99. The app checks scope_is_subset BEFORE
executing the tool and blocks the request.

This is the core security pattern: validate first, check scope second,
act third.
"""
import os
import sys

print()
print("╔══════════════════════════════════════════════════════════════════╗")
print("║  App Blocks Rogue Agent From Unauthorized Tool (STORY-P3-S4)   ║")
print("║                                                                  ║")
print("║  An agent scoped to read:data:user-42 tries to access           ║")
print("║  user-99's data. The app checks scope_is_subset() and blocks    ║")
print("║  the request before the tool ever executes.                     ║")
print("╚══════════════════════════════════════════════════════════════════╝")
print()

from agentauth import AgentAuthApp, scope_is_subset, validate

broker_url = os.environ["AGENTAUTH_BROKER_URL"]
client_id = os.environ["AGENTAUTH_CLIENT_ID"]
client_secret = os.environ["AGENTAUTH_CLIENT_SECRET"]

app = AgentAuthApp(broker_url=broker_url, client_id=client_id, client_secret=client_secret)

print("Step 1: Create agent scoped to user-42")
agent = app.create_agent(
    orch_id="data-pipeline", task_id="analyze-user-42",
    requested_scope=["read:data:user-42"],
)
print(f"  agent_id = {agent.agent_id}")
print(f"  scope    = {agent.scope}")
print()

print("Step 2: Agent requests tool 'read_user_profile' for user-42")
tool_scope = ["read:data:user-42"]
allowed = scope_is_subset(tool_scope, agent.scope)
print(f"  tool requires = {tool_scope}")
print(f"  agent has     = {agent.scope}")
print(f"  allowed       = {allowed}")
print()

print("Step 3: Agent requests tool 'read_user_profile' for user-99 (ROGUE)")
rogue_scope = ["read:data:user-99"]
blocked = not scope_is_subset(rogue_scope, agent.scope)
print(f"  tool requires = {rogue_scope}")
print(f"  agent has     = {agent.scope}")
print(f"  blocked       = {blocked}")
print()

print("Step 4: Full pattern — validate token, then check scope")
result = validate(broker_url, agent.access_token)
print(f"  token valid   = {result.valid}")
if result.claims:
    print(f"  claims.scope  = {result.claims.scope}")
    verified_scope = scope_is_subset(rogue_scope, result.claims.scope)
    print(f"  rogue request allowed by verified claims = {verified_scope}")
print()

print("Step 5: Verifying")
passed = True

if allowed is True:
    print("  PASS: legitimate request (user-42) was allowed")
else:
    print("  FAIL: legitimate request was blocked")
    passed = False

if blocked is True:
    print("  PASS: rogue request (user-99) was blocked")
else:
    print("  FAIL: rogue request was allowed — agent escaped its scope")
    passed = False

if result.valid is True:
    print("  PASS: broker confirmed agent token is valid")
else:
    print("  FAIL: broker said token is invalid")
    passed = False

if result.claims and not scope_is_subset(rogue_scope, result.claims.scope):
    print("  PASS: verified claims also block the rogue request")
else:
    print("  FAIL: verified claims allowed the rogue request")
    passed = False

agent.release()
print("  Agent released")

print()
if passed:
    print("═══ STORY-P3-S4: PASS ═══")
else:
    print("═══ STORY-P3-S4: FAIL ═══")
    sys.exit(1)
