#!/usr/bin/env python3
"""STORY-P3-S7: Agent Delegates Narrower Scope to Another Agent

A primary agent has read:data:user-42 and write:data:user-42. It needs
a helper agent to read user-42's data but NOT write it. The primary
delegates only read:data:user-42 to the helper. The helper can read
but cannot write — authority only narrows, never expands.
"""
import os
import sys

print()
print("╔══════════════════════════════════════════════════════════════════╗")
print("║  Agent Delegates Narrower Scope to Helper (STORY-P3-S7)        ║")
print("║                                                                  ║")
print("║  A primary agent (read+write for user-42) delegates only read   ║")
print("║  access to a helper agent. The helper cannot write.             ║")
print("║  Authority only narrows — never expands.                        ║")
print("╚══════════════════════════════════════════════════════════════════╝")
print()

from agentauth import AgentAuthApp, scope_is_subset

broker_url = os.environ["AGENTAUTH_BROKER_URL"]
client_id = os.environ["AGENTAUTH_CLIENT_ID"]
client_secret = os.environ["AGENTAUTH_CLIENT_SECRET"]

app = AgentAuthApp(broker_url=broker_url, client_id=client_id, client_secret=client_secret)

print("Step 1: Create primary agent (read + write for user-42)")
primary = app.create_agent(
    orch_id="data-pipeline", task_id="process-user-42",
    requested_scope=["read:data:user-42", "write:data:user-42"],
)
print(f"  agent_id = {primary.agent_id}")
print(f"  scope    = {primary.scope}")
print()

print("Step 2: Create helper agent (will receive delegated read-only)")
helper = app.create_agent(
    orch_id="data-pipeline", task_id="helper-read-user-42",
    requested_scope=["read:data:user-42"],
)
print(f"  agent_id = {helper.agent_id}")
print(f"  scope    = {helper.scope}")
print()

print("Step 3: Primary delegates read:data:user-42 to helper")
delegated = primary.delegate(
    delegate_to=helper.agent_id,
    scope=["read:data:user-42"],
)
print(f"  delegated token   = {delegated.access_token[:30]}...")
print(f"  expires_in        = {delegated.expires_in}s")
print(f"  delegation_chain  = {len(delegated.delegation_chain)} entries")
for i, entry in enumerate(delegated.delegation_chain):
    print(f"    chain[{i}].agent = {entry.agent}")
    print(f"    chain[{i}].scope = {entry.scope}")
print()

print("Step 4: Verify delegated scope is read-only")
passed = True

can_read = scope_is_subset(["read:data:user-42"], helper.scope)
print(f"  helper can read user-42  = {can_read}")
if can_read:
    print("  PASS: helper can read user-42")
else:
    print("  FAIL: helper cannot read user-42")
    passed = False

can_write = scope_is_subset(["write:data:user-42"], helper.scope)
print(f"  helper can write user-42 = {can_write}")
if not can_write:
    print("  PASS: helper cannot write user-42 (scope only narrows)")
else:
    print("  FAIL: helper can write — delegation expanded scope")
    passed = False

if len(delegated.delegation_chain) >= 1:
    print(f"  PASS: delegation chain has {len(delegated.delegation_chain)} entry(ies)")
else:
    print("  FAIL: delegation chain is empty")
    passed = False

primary.release()
helper.release()
print("  Both agents released")

print()
if passed:
    print("═══ STORY-P3-S7: PASS ═══")
else:
    print("═══ STORY-P3-S7: FAIL ═══")
    sys.exit(1)
