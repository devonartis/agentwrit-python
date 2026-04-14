# App 7: Incident Response System

## The Scenario

Your security team detects anomalous behavior from an agent. The incident responder needs to immediately revoke credentials at the right granularity — revoke one token if it's a leak, revoke all tokens for a task if the task is compromised, or revoke an entire delegation chain if privilege escalation is detected.

This app demonstrates all four revocation levels — **token**, **agent**, **task**, and **chain** — and validates that revoked tokens are actually dead. It uses the broker's admin API (`POST /v1/revoke`) which requires an admin token, not an app token.

After revocation, the app validates every affected token to confirm the broker rejects it. This is the verification step that proves your incident response actually worked.

---

## What You'll Learn

| Concept | Why It Matters |
|---------|---------------|
| **Four revocation levels** | Token (single JTI), Agent (SPIFFE ID), Task (task_id), Chain (root delegator) |
| **Admin authentication** | `POST /v1/admin/auth` — separate from app auth, uses the admin secret |
| **`POST /v1/revoke`** | The broker endpoint for credential invalidation |
| **Post-revoke validation** | Always verify that revoked tokens are actually rejected |
| **Blast radius control** | Revoking one token vs. an entire task vs. a whole delegation tree |
| **`validate()` returns generic errors** | The broker says "token is invalid or expired" — no details about why |

---

## Architecture

```
┌───────────────────────────────────────────────────────────────┐
│  Incident Response Script                                      │
│                                                                │
│  Phase 1: Create 4 agents (simulate a running system)          │
│    agent-reader    → scope: read:data:partition-1              │
│    agent-writer    → scope: write:data:partition-1             │
│    agent-analyzer  → scope: read:data:partition-2              │
│    agent-archiver  → scope: write:data:partition-3             │
│                                                                │
│  Phase 2: Demonstrate each revocation level                    │
│    Level 1 — Token: revoke agent-reader's current JTI          │
│    Level 2 — Agent: revoke all tokens for agent-writer         │
│    Level 3 — Task: revoke all tokens for task "incident-demo"  │
│    Level 4 — Chain: revoke delegation tree from agent-reader   │
│                                                                │
│  After each level: validate affected tokens → all dead         │
│  Validate unaffected tokens → still alive                      │
└───────────────────────────────────────────────────────────────┘
```

---

## The Code

```python
# incident_response.py
# Run: python incident_response.py

from __future__ import annotations

import os
import sys

import httpx

from agentwrit import AgentWritApp, Agent, validate


def admin_auth(broker_url: str, admin_secret: str) -> str:
    """Authenticate as admin using the operator secret."""
    resp = httpx.post(
        f"{broker_url}/v1/admin/auth",
        json={"secret": admin_secret},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()["access_token"]


def revoke(
    broker_url: str,
    admin_token: str,
    level: str,
    target: str,
) -> dict:
    """Revoke tokens at the specified level. Returns broker response."""
    resp = httpx.post(
        f"{broker_url}/v1/revoke",
        json={"level": level, "target": target},
        headers={"Authorization": f"Bearer {admin_token}"},
        timeout=10,
    )
    resp.raise_for_status()
    return resp.json()


def check_token(broker_url: str, token: str, label: str) -> bool:
    """Validate a token and print the result. Returns True if alive."""
    result = validate(broker_url, token)
    state = "ALIVE" if result.valid else "DEAD"
    print(f"    {label}: {state}")
    return result.valid


def main() -> None:
    broker_url = os.environ["AGENTWRIT_BROKER_URL"]
    admin_secret = os.environ.get("AA_ADMIN_SECRET", "dev-secret")

    app = AgentWritApp(
        broker_url=broker_url,
        client_id=os.environ["AGENTWRIT_CLIENT_ID"],
        client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
    )

    print("Incident Response — Revocation Demo")
    print("=" * 55)
    print()

    # ── Phase 1: Create agents (simulated running system) ───────
    print("Phase 1: Creating agents (simulating a running system)")
    print()

    task_id = "incident-demo"

    reader = app.create_agent(
        orch_id="incident-response",
        task_id=task_id,
        requested_scope=["read:data:partition-1"],
    )
    writer = app.create_agent(
        orch_id="incident-response",
        task_id=task_id,
        requested_scope=["write:data:partition-1"],
    )
    analyzer = app.create_agent(
        orch_id="incident-response",
        task_id=task_id,
        requested_scope=["read:data:partition-2"],
    )
    archiver = app.create_agent(
        orch_id="incident-response",
        task_id="other-task",  # Different task — should survive task-level revoke
        requested_scope=["write:data:partition-3"],
    )

    agents = {
        "reader": reader,
        "writer": writer,
        "analyzer": analyzer,
        "archiver": archiver,
    }

    for name, agent in agents.items():
        print(f"  {name:10s} → {agent.agent_id}")
        print(f"             task: {agent.task_id}, scope: {agent.scope}")
    print()

    # All tokens should be alive
    print("  Initial state (all alive):")
    for name, agent in agents.items():
        check_token(broker_url, agent.access_token, name)
    print()

    # ── Authenticate as admin ───────────────────────────────────
    admin_token = admin_auth(broker_url, admin_secret)
    print(f"Admin authenticated (for revocation operations)")
    print()

    # ── Level 1: Token-level revocation ─────────────────────────
    print("── Level 1: Token Revocation (single JTI) ──")
    print()
    print("  Scenario: reader's current token was leaked in a log file")
    print(f"  Revoking JTI for reader...")

    # Get the JTI by validating the token
    reader_claims = validate(broker_url, reader.access_token)
    reader_jti = reader_claims.claims.jti if reader_claims.claims else "unknown"
    print(f"  JTI: {reader_jti}")

    result = revoke(broker_url, admin_token, "token", reader_jti)
    print(f"  Revoked: {result['revoked']}, count: {result['count']}")
    print()

    print("  Post-revoke validation:")
    check_token(broker_url, reader.access_token, "reader")    # Should be DEAD
    check_token(broker_url, writer.access_token, "writer")    # Should be ALIVE
    check_token(broker_url, analyzer.access_token, "analyzer")  # Should be ALIVE
    check_token(broker_url, archiver.access_token, "archiver")  # Should be ALIVE
    print()

    # ── Level 2: Agent-level revocation ─────────────────────────
    print("── Level 2: Agent Revocation (all tokens for SPIFFE ID) ──")
    print()
    print("  Scenario: writer agent compromised via prompt injection")
    print(f"  Revoking all tokens for writer...")

    result = revoke(broker_url, admin_token, "agent", writer.agent_id)
    print(f"  Revoked: {result['revoked']}, count: {result['count']}")
    print()

    print("  Post-revoke validation:")
    check_token(broker_url, reader.access_token, "reader")     # Already dead from level 1
    check_token(broker_url, writer.access_token, "writer")     # Should be DEAD
    check_token(broker_url, analyzer.access_token, "analyzer")  # Should be ALIVE
    check_token(broker_url, archiver.access_token, "archiver")  # Should be ALIVE
    print()

    # ── Level 3: Task-level revocation ──────────────────────────
    print("── Level 3: Task Revocation (all tokens for task_id) ──")
    print()
    print(f"  Scenario: entire task '{task_id}' is suspect — data poisoning")
    print(f"  Revoking all tokens for task '{task_id}'...")

    result = revoke(broker_url, admin_token, "task", task_id)
    print(f"  Revoked: {result['revoked']}, count: {result['count']}")
    print()

    print("  Post-revoke validation:")
    check_token(broker_url, reader.access_token, "reader")      # Dead
    check_token(broker_url, writer.access_token, "writer")      # Dead
    check_token(broker_url, analyzer.access_token, "analyzer")  # Should be DEAD now
    check_token(broker_url, archiver.access_token, "archiver")  # Should be ALIVE (different task)
    print()

    # ── Level 4: Chain-level revocation ─────────────────────────
    print("── Level 4: Chain Revocation (delegation tree) ──")
    print()
    print("  Scenario: delegation chain exploited — privilege escalation detected")
    print("  Re-creating agents to demonstrate chain revocation...")

    # Create fresh agents for the delegation demo
    chain_root = app.create_agent(
        orch_id="incident-response",
        task_id="chain-demo",
        requested_scope=["read:data:*", "write:data:*"],
    )
    chain_child = app.create_agent(
        orch_id="incident-response",
        task_id="chain-demo",
        requested_scope=["read:data:*"],
    )

    # Root delegates to child
    delegated = chain_root.delegate(
        delegate_to=chain_child.agent_id,
        scope=["read:data:partition-1"],
    )

    print(f"  Chain root: {chain_root.agent_id}")
    print(f"  Chain child: {chain_child.agent_id}")
    print(f"  Delegated token: {delegated.access_token[:30]}...")
    print()

    print("  Before chain revoke:")
    check_token(broker_url, chain_root.access_token, "chain-root")
    check_token(broker_url, delegated.access_token, "delegated-to-child")
    print()

    # Revoke the entire chain rooted at chain_root
    result = revoke(broker_url, admin_token, "chain", chain_root.agent_id)
    print(f"  Chain revoked: {result['revoked']}, count: {result['count']}")
    print()

    print("  After chain revoke:")
    check_token(broker_url, chain_root.access_token, "chain-root")
    check_token(broker_url, delegated.access_token, "delegated-to-child")
    print()

    # Cleanup survivors
    archiver.release()
    chain_child.release()
    print("Surviving agents released.")


if __name__ == "__main__":
    main()
```

---

## Setup Requirements

This app uses the **universal sample app** registered in the [README setup](README.md#one-time-setup-for-all-sample-apps). If you've already registered it, skip to Running It.

### Which Ceiling Scopes This App Uses

| Ceiling Scope | What This App Requests | Why |
|--------------|----------------------|-----|
| `read:data:*` | Agents read various partitions | `read:data:partition-1`, `read:data:partition-2`, `read:data:*` (chain root) |
| `write:data:*` | Agents write to partitions, chain root delegates write | `write:data:partition-1`, `write:data:partition-3`, `write:data:*` (chain root) |

### Additional Requirement: Admin Secret

This app revokes tokens using the admin API, which requires the **operator's admin secret**. This is the same secret used to start the broker:

```bash
export AA_ADMIN_SECRET="dev-secret"  # match your broker's admin secret
```

### Additional Dependency

```bash
uv add httpx
```

## Running It

```bash
export AGENTWRIT_BROKER_URL="http://127.0.0.1:8080"
export AGENTWRIT_CLIENT_ID="<from registration>"
export AGENTWRIT_CLIENT_SECRET="<from registration>"
export AA_ADMIN_SECRET="dev-secret"

uv run python incident_response.py
```

---

## Expected Output

```
Incident Response — Revocation Demo
=======================================================

Phase 1: Creating agents (simulating a running system)

  reader     → spiffe://agentwrit.local/agent/incident-response/incident-demo/a1b2...
             task: incident-demo, scope: ['read:data:partition-1']
  writer     → spiffe://agentwrit.local/agent/incident-response/incident-demo/c3d4...
             task: incident-demo, scope: ['write:data:partition-1']
  analyzer   → spiffe://agentwrit.local/agent/incident-response/incident-demo/e5f6...
             task: incident-demo, scope: ['read:data:partition-2']
  archiver   → spiffe://agentwrit.local/agent/incident-response/other-task/g7h8...
             task: other-task, scope: ['write:data:partition-3']

  Initial state (all alive):
    reader: ALIVE
    writer: ALIVE
    analyzer: ALIVE
    archiver: ALIVE

Admin authenticated (for revocation operations)

── Level 1: Token Revocation (single JTI) ──

  Scenario: reader's current token was leaked in a log file
  Revoking JTI for reader...
  JTI: a1b2c3d4e5f6...
  Revoked: True, count: 1

  Post-revoke validation:
    reader: DEAD
    writer: ALIVE
    analyzer: ALIVE
    archiver: ALIVE

── Level 2: Agent Revocation (all tokens for SPIFFE ID) ──

  Scenario: writer agent compromised via prompt injection
  Revoking all tokens for writer...
  Revoked: True, count: 1

  Post-revoke validation:
    reader: DEAD
    writer: DEAD
    analyzer: ALIVE
    archiver: ALIVE

── Level 3: Task Revocation (all tokens for task_id) ──

  Scenario: entire task 'incident-demo' is suspect — data poisoning
  Revoking all tokens for task 'incident-demo'...
  Revoked: True, count: 2

  Post-revoke validation:
    reader: DEAD
    writer: DEAD
    analyzer: DEAD
    archiver: ALIVE              ← different task, unaffected

── Level 4: Chain Revocation (delegation tree) ──
  ...

Surviving agents released.
```

---

## Key Takeaways

1. **Four revocation levels, four blast radii.** Token revocation kills one credential. Agent revocation kills all tokens for one SPIFFE ID. Task revocation kills all tokens with that task_id. Chain revocation kills the root agent and all downstream delegated tokens. Choose the narrowest level that covers the incident.

2. **The archiver survives task-level revocation.** It has `task_id="other-task"`, not `task_id="incident-demo"`. This proves that task-level revocation is surgical — it only affects the specific task, not every agent in the system.

3. **Admin auth is separate from app auth.** Revocation requires an admin token (from `POST /v1/admin/auth`), not an app token. Your app cannot revoke its own agents — only the operator can. This is by design: a compromised app shouldn't be able to cover its tracks by revoking audit evidence.

4. **`validate()` returns generic errors for revoked tokens.** The broker says "token is invalid or expired" whether the token was revoked, expired, or malformed. This prevents information leakage — an attacker can't tell if a token was explicitly revoked or just expired.

5. **Always validate after revoking.** Don't assume the revocation worked. Call `validate()` on the affected tokens to confirm the broker actually rejects them. This is the verification step in your incident response playbook.
