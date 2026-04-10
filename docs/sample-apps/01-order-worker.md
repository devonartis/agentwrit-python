# App 1: E-Commerce Order Worker

## The Scenario

You run an e-commerce platform. When a customer places an order, a background worker picks it up and processes it: reading the customer's profile, checking inventory, and writing the order confirmation. This worker needs database access — but only for that specific customer, only for the duration of that order, and only with the permissions (read customer data, write order records) that order processing requires.

Without AgentAuth, that worker would use a shared database credential stored in an environment variable. Every worker shares the same key. If one worker is compromised, every customer's data is exposed. The key lives forever because rotating it breaks all running workers.

With AgentAuth, the worker gets an ephemeral identity scoped to exactly one customer and one task. The credential lasts minutes, not months. When the order is done, the worker releases the credential immediately — even if the token was leaked, it's already dead.

---

## What You'll Learn

| Concept | Why It Matters |
|---------|---------------|
| **Agent lifecycle** — create → validate → use → release | The fundamental pattern you'll use in every AgentAuth app |
| **`create_agent()`** with task-specific scope | How to bind a credential to one unit of work |
| **`validate()`** for token inspection | How downstream services verify agent credentials |
| **`release()`** in a `finally` block | Why explicit cleanup shrinks your attack window |
| **`Agent.bearer_header`** | The convenience property for passing tokens to HTTP calls |

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Order Worker Script                         │
│                                              │
│  1. Connect to broker (AgentAuthApp)         │
│  2. Create agent scoped to one customer      │
│  3. Validate the token → inspect claims      │
│  4. Simulate: read customer profile          │
│  5. Simulate: write order confirmation       │
│  6. Release the agent token                  │
│  7. Validate again → confirm token is dead   │
└─────────────────────────────────────────────┘
         │                        │
         ▼                        ▼
   ┌──────────┐           ┌──────────────┐
   │  Broker  │           │  "Database"  │
   │ (tokens) │           │  (mock data) │
   └──────────┘           └──────────────┘
```

The worker creates one agent with two scopes:
- `read:data:customer-{id}` — can read that customer's profile
- `write:data:order-{id}` — can write that specific order's record

No other customer. No other order. No admin access. No write access to customer profiles.

---

## The Code

```python
# order_worker.py
# Run: python order_worker.py --customer cust-7291 --order ord-4823

from __future__ import annotations

import argparse
import sys

from agentauth import (
    Agent,
    AgentAuthApp,
    scope_is_subset,
    validate,
)
from agentauth.errors import AgentAuthError


def process_order(
    app: AgentAuthApp,
    customer_id: str,
    order_id: str,
) -> None:
    """Process a single e-commerce order with an ephemeral agent."""

    # ── Step 1: Create the agent ────────────────────────────────
    # Scope is derived from the ORDER being processed — never hardcoded.
    # Each order gets its own agent with its own isolated scope.
    requested_scope = [
        f"read:data:customer-{customer_id}",
        f"write:data:order-{order_id}",
    ]

    agent = app.create_agent(
        orch_id="order-worker",
        task_id=f"process-{order_id}",
        requested_scope=requested_scope,
    )

    print(f"Agent created: {agent.agent_id}")
    print(f"  Scope:   {agent.scope}")
    print(f"  Expires: {agent.expires_in}s")
    print(f"  Token:   {agent.access_token[:30]}...")
    print()

    # ── Step 2: Validate the token ──────────────────────────────
    # Any service that receives this token can validate it.
    # Here we validate immediately to show what claims look like.
    result = validate(app.broker_url, agent.access_token)

    if result.valid and result.claims is not None:
        print("Token is valid. Claims:")
        print(f"  Issuer:  {result.claims.iss}")
        print(f"  Subject: {result.claims.sub}")
        print(f"  Scope:   {result.claims.scope}")
        print(f"  Task:    {result.claims.task_id}")
        print(f"  Orch:    {result.claims.orch_id}")
        print(f"  JTI:     {result.claims.jti}")
    else:
        print(f"Token invalid: {result.error}")
        agent.release()
        return
    print()

    try:
        # ── Step 3: Use the agent for work ──────────────────────
        # Before every action, check scope. This is YOUR responsibility
        # as the app developer — the broker sets scope at creation time,
        # but you enforce it at runtime.

        # Action: Read customer profile
        read_scope = [f"read:data:customer-{customer_id}"]
        if scope_is_subset(read_scope, agent.scope):
            print(f"[READ] Customer profile for {customer_id}: John Doe, Premium tier")
        else:
            print(f"[DENIED] Cannot read customer {customer_id}")

        # Action: Write order confirmation
        write_scope = [f"write:data:order-{order_id}"]
        if scope_is_subset(write_scope, agent.scope):
            print(f"[WRITE] Order {order_id} confirmed for customer {customer_id}")
        else:
            print(f"[DENIED] Cannot write order {order_id}")

        # Action: Try to read a DIFFERENT customer (blocked)
        other_scope = [f"read:data:customer-cust-9999"]
        if scope_is_subset(other_scope, agent.scope):
            print(f"[READ] Customer cust-9999: this should NOT happen")
        else:
            print(f"[BLOCKED] Cannot access customer cust-9999 — scope isolation working")

        # Action: Try to write to a DIFFERENT order (blocked)
        other_order_scope = [f"write:data:order-ord-0000"]
        if scope_is_subset(other_order_scope, agent.scope):
            print(f"[WRITE] Order ord-0000: this should NOT happen")
        else:
            print(f"[BLOCKED] Cannot write order ord-0000 — scope isolation working")

        print()

    finally:
        # ── Step 4: Release the token ───────────────────────────
        # Always release in a finally block. If the work above crashed,
        # the token still gets cleaned up.
        agent.release()
        print("Agent released. Token is now dead at the broker.")

    # ── Step 5: Confirm the token is dead ───────────────────────
    dead_result = validate(app.broker_url, agent.access_token)
    if not dead_result.valid:
        print(f"Confirmed: token rejected — \"{dead_result.error}\"")
    else:
        print("WARNING: token is still valid after release!")
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(description="E-Commerce Order Worker")
    parser.add_argument("--customer", required=True, help="Customer ID (e.g. cust-7291)")
    parser.add_argument("--order", required=True, help="Order ID (e.g. ord-4823)")
    args = parser.parse_args()

    import os

    app = AgentAuthApp(
        broker_url=os.environ["AGENTAUTH_BROKER_URL"],
        client_id=os.environ["AGENTAUTH_CLIENT_ID"],
        client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
    )

    print(f"Processing order {args.order} for customer {args.customer}")
    print("=" * 55)
    print()

    process_order(app, args.customer, args.order)


if __name__ == "__main__":
    main()
```

---

## Setup Requirements

This app uses the **universal sample app** registered in the [README setup](README.md#one-time-setup-for-all-sample-apps). If you've already registered it, skip to Running It.

### Which Ceiling Scopes This App Uses

| Ceiling Scope | What This App Requests | Why |
|--------------|----------------------|-----|
| `read:data:*` | `read:data:customer-{id}` | Read one customer's profile |
| `write:data:*` | `write:data:order-{id}` | Write one order's confirmation |

The ceiling uses wildcards (`*`) so the app can create agents for **any** customer or order ID. Each agent still gets a narrow scope for one specific customer and one specific order.

> **If the broker returns `AuthorizationError (403)`, the app's ceiling doesn't include `read:data:*` or `write:data:*`.** Re-register the app with the correct ceiling (see [README setup](README.md#one-time-setup-for-all-sample-apps)).

### Quick Registration (if not done yet)

```bash
./broker/scripts/stack_up.sh
```

Then follow the [One-Time Setup](README.md#one-time-setup-for-all-sample-apps) in the README.

## Running It

```bash
export AGENTAUTH_BROKER_URL="http://127.0.0.1:8080"
export AGENTAUTH_CLIENT_ID="<from registration>"
export AGENTAUTH_CLIENT_SECRET="<from registration>"

uv run python order_worker.py --customer cust-7291 --order ord-4823
```

---

## Expected Output

```
Processing order ord-4823 for customer cust-7291
=======================================================

Agent created: spiffe://agentauth.local/agent/order-worker/process-ord-4823/a3f7...
  Scope:   ['read:data:customer-cust-7291', 'write:data:order-ord-4823']
  Expires: 300s
  Token:   eyJhbGciOiJFZERTQSIsInR5cCI6...

Token is valid. Claims:
  Issuer:  agentauth
  Subject: spiffe://agentauth.local/agent/order-worker/process-ord-4823/a3f7...
  Scope:   ['read:data:customer-cust-7291', 'write:data:order-ord-4823']
  Task:    process-ord-4823
  Orch:    order-worker
  JTI:     8b2c4e7f...

[READ] Customer profile for cust-7291: John Doe, Premium tier
[WRITE] Order ord-4823 confirmed for customer cust-7291
[BLOCKED] Cannot access customer cust-9999 — scope isolation working
[BLOCKED] Cannot write order ord-0000 — scope isolation working

Agent released. Token is now dead at the broker.
Confirmed: token rejected — "token is invalid or expired"
```

---

## Key Takeaways

1. **Scope comes from the task, not from config files.** The customer ID and order ID come from the command line — the worker's authority is derived from what it's processing, not from a static permission list.

2. **`scope_is_subset()` is your runtime gate.** The broker sets scope at creation. You must check it before every action. This two-part model (broker issues, app enforces) is the core pattern.

3. **`release()` in a `finally` block.** If the work crashes, the token still gets cleaned up. If you forget `release()` entirely, the token expires after its TTL (300 seconds by default). Explicit release is faster and creates a cleaner audit trail.

4. **Cross-scope access is impossible.** The agent scoped to `customer-cust-7291` cannot read `customer-cust-9999`. The `scope_is_subset()` check catches this locally without hitting the broker — but if you passed the token to a downstream service, that service would validate against the broker and get the same rejection.

5. **Every agent gets a unique SPIFFE identity.** Two orders processed by the same script get different `agent_id` values. In the audit trail, you can tell exactly which agent processed which order.
