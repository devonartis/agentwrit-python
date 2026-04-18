# App 5: CI/CD Deployment Runner

## The Scenario

You run a deployment pipeline with three stages: an **orchestrator** reads the deployment config, an **analyst** reviews the target environment, and a **deployer** pushes the actual code. Each stage needs less authority than the one before it. The orchestrator has broad access to configs and deploy targets. It delegates a narrow slice to the analyst, who delegates an even narrower slice to the deployer.

This creates a three-hop delegation chain: **Orchestrator → Analyst → Deployer**. Each hop narrows the scope. The deployer can only push to one specific service in one specific environment — it cannot read configs, it cannot deploy other services, and it cannot touch staging.

This app demonstrates the SDK's multi-hop delegation limitation: `agent.delegate()` always uses the agent's **registration token**, not a received delegated token. For the second hop, you must use raw HTTP with the delegated token as the Bearer credential.

---

## What You'll Learn

| Concept | Why It Matters |
|---------|---------------|
| **Multi-hop delegation (A→B→C)** | Attenuating scope across three agents — each hop in this example narrows further |
| **Raw HTTP for second delegation hop** | The SDK's `delegate()` uses the registration token; multi-hop needs the delegated token |
| **Delegation chain depth** | The chain records every hop — depth is limited to 5 |
| **Validating at each hop** | Confirming the broker issued the scope you requested at each step |
| **`AuthorizationError` on scope violation** | What happens when a delegation tries to escalate scope |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│  Deployment Runner Script                                         │
│                                                                   │
│  Orchestrator scope:                                              │
│    read:config:*, read:deploy:*, write:deploy:*                   │
│                                                                   │
│  Hop 1 (SDK): Orchestrator → Analyst                              │
│    Delegated: read:config:production, read:deploy:web-service     │
│    Dropped: write:deploy:* (analyst is read-only)                 │
│                                                                   │
│  Hop 2 (Raw HTTP): Analyst → Deployer                             │
│    Delegated: write:deploy:web-service                             │
│    Dropped: read:config:* (deployer doesn't need config)          │
│                                                                   │
│  Result:                                                          │
│    Orchestrator — full access                                     │
│    Analyst — can read config and deploy status for one service     │
│    Deployer — can ONLY push web-service to production              │
└──────────────────────────────────────────────────────────────────┘
```

---

## The Code

```python
# deploy_runner.py
# Run: python deploy_runner.py

from __future__ import annotations

import os
import sys

import httpx

from agentwrit import (
    AgentWritApp,
    DelegatedToken,
    scope_is_subset,
    validate,
)
from agentwrit.errors import AuthorizationError


def main() -> None:
    app = AgentWritApp(
        broker_url=os.environ["AGENTWRIT_BROKER_URL"],
        client_id=os.environ["AGENTWRIT_CLIENT_ID"],
        client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
    )
    broker_url = app.broker_url

    print("CI/CD Deployment Runner — Multi-Hop Delegation")
    print("=" * 55)
    print()

    # ── Create all three agents ─────────────────────────────────
    orchestrator = app.create_agent(
        orch_id="deploy-pipeline",
        task_id="release-v2.4.1",
        requested_scope=[
            "read:config:*",
            "read:deploy:*",
            "write:deploy:*",
        ],
    )
    print(f"Orchestrator created")
    print(f"  ID:    {orchestrator.agent_id}")
    print(f"  Scope: {orchestrator.scope}")
    print()

    analyst = app.create_agent(
        orch_id="deploy-pipeline",
        task_id="review-v2.4.1",
        requested_scope=[
            "read:config:*",
            "read:deploy:*",
        ],
    )
    print(f"Analyst created")
    print(f"  ID:    {analyst.agent_id}")
    print(f"  Scope: {analyst.scope}")
    print()

    deployer = app.create_agent(
        orch_id="deploy-pipeline",
        task_id="push-v2.4.1",
        requested_scope=[
            "write:deploy:*",
        ],
    )
    print(f"Deployer created")
    print(f"  ID:    {deployer.agent_id}")
    print(f"  Scope: {deployer.scope}")
    print()

    # ── Hop 1: Orchestrator → Analyst (SDK) ─────────────────────
    # Orchestrator delegates a narrow slice: only production config
    # and only the web-service deploy target.
    hop1_scope = [
        "read:config:production",
        "read:deploy:web-service",
    ]

    print(f"Hop 1: Orchestrator → Analyst")
    print(f"  Delegating: {hop1_scope}")

    delegated_ab: DelegatedToken = orchestrator.delegate(
        delegate_to=analyst.agent_id,
        scope=hop1_scope,
        ttl=120,
    )

    print(f"  Success! Chain depth: {len(delegated_ab.delegation_chain)}")
    print(f"  Delegated token: {delegated_ab.access_token[:30]}...")
    print()

    # Validate hop 1
    hop1_result = validate(broker_url, delegated_ab.access_token)
    if hop1_result.valid and hop1_result.claims is not None:
        print(f"  Hop 1 validated scope: {hop1_result.claims.scope}")
        if hop1_result.claims.delegation_chain:
            print(f"  Chain entries: {len(hop1_result.claims.delegation_chain)}")
    print()

    # ── Hop 2: Analyst → Deployer (Raw HTTP) ────────────────────
    # The SDK's analyst.delegate() would use the analyst's REGISTRATION
    # token, not the delegated token from hop 1. For a true multi-hop
    # chain, we must use the delegated token as the Bearer credential.
    hop2_scope = [
        "write:deploy:web-service",
    ]

    print(f"Hop 2: Analyst → Deployer (raw HTTP)")
    print(f"  Delegating: {hop2_scope}")
    print(f"  Using delegated token from hop 1 as Bearer")

    resp = httpx.post(
        f"{broker_url}/v1/delegate",
        json={
            "delegate_to": deployer.agent_id,
            "scope": hop2_scope,
            "ttl": 60,
        },
        headers={"Authorization": f"Bearer {delegated_ab.access_token}"},
        timeout=10,
    )

    if resp.status_code != 200:
        print(f"  FAILED: {resp.status_code} — {resp.text}")
        sys.exit(1)

    hop2_data = resp.json()
    print(f"  Success! Token: {hop2_data['access_token'][:30]}...")
    hop2_chain = hop2_data.get("delegation_chain", [])
    print(f"  Chain depth: {len(hop2_chain)}")
    for i, entry in enumerate(hop2_chain):
        print(f"    [{i}] {entry['agent']} → scope: {entry['scope']}")
    print()

    # Validate hop 2
    hop2_result = validate(broker_url, hop2_data["access_token"])
    if hop2_result.valid and hop2_result.claims is not None:
        print(f"  Hop 2 validated scope: {hop2_result.claims.scope}")
        if hop2_result.claims.delegation_chain:
            print(f"  Chain entries: {len(hop2_result.claims.delegation_chain)}")
    print()

    # ── Scope Isolation Checks ──────────────────────────────────
    print("── Scope Isolation ──")
    print()

    # Orchestrator can read all configs
    if scope_is_subset(["read:config:staging"], orchestrator.scope):
        print(f"  Orchestrator CAN read staging config ✓")
    if scope_is_subset(["write:deploy:payment-svc"], orchestrator.scope):
        print(f"  Orchestrator CAN deploy payment-svc ✓")

    # Delegated analyst scope is narrow
    analyst_scope = hop1_scope
    if not scope_is_subset(["read:config:staging"], analyst_scope):
        print(f"  Analyst CANNOT read staging config (only production) ✓")
    if not scope_is_subset(["write:deploy:web-service"], analyst_scope):
        print(f"  Analyst CANNOT write deploy (read-only) ✓")
    if scope_is_subset(["read:config:production"], analyst_scope):
        print(f"  Analyst CAN read production config ✓")

    # Delegated deployer scope is narrowest
    deployer_delegated = hop2_scope
    if not scope_is_subset(["read:config:production"], deployer_delegated):
        print(f"  Deployer CANNOT read configs ✓")
    if not scope_is_subset(["write:deploy:payment-svc"], deployer_delegated):
        print(f"  Deployer CANNOT deploy payment-svc ✓")
    if scope_is_subset(["write:deploy:web-service"], deployer_delegated):
        print(f"  Deployer CAN deploy web-service ✓")

    print()

    # ── Cleanup ─────────────────────────────────────────────────
    orchestrator.release()
    analyst.release()
    deployer.release()
    print("All agents released.")


if __name__ == "__main__":
    main()
```

---

## Setup Requirements

This app uses the **universal sample app** registered in the [README setup](README.md#one-time-setup-for-all-sample-apps). If you've already registered it, skip to Running It.

### Which Ceiling Scopes This App Uses

| Ceiling Scope | What This App Requests | Why |
|--------------|----------------------|-----|
| `read:config:*` | Orchestrator reads config, analyst reads production config | Config review |
| `read:deploy:*` | Orchestrator and analyst read deploy status | Pre-deploy checks |
| `write:deploy:*` | Orchestrator deploys anything, deployer deploys one service | Push code |

> **Why `read:config:*` and not `read:config:production`?** The app ceiling is broad — the orchestrator might deploy to staging, production, or any environment. The narrowing happens at the agent level and through delegation. The orchestrator delegates `read:config:production` (not `*`) to the analyst.

### Additional Dependency

This app uses `httpx` for the raw HTTP delegation hop. Install it:

```bash
uv add httpx
```

## Running It

```bash
export AGENTWRIT_BROKER_URL="http://127.0.0.1:8080"
export AGENTWRIT_CLIENT_ID="<from registration>"
export AGENTWRIT_CLIENT_SECRET="<from registration>"

uv run python deploy_runner.py
```

---

## Expected Output

```
CI/CD Deployment Runner — Multi-Hop Delegation
=======================================================

Orchestrator created
  ID:    spiffe://agentwrit.local/agent/deploy-pipeline/release-v2.4.1/a1b2...
  Scope: ['read:config:*', 'read:deploy:*', 'write:deploy:*']

Analyst created
  ID:    spiffe://agentwrit.local/agent/deploy-pipeline/review-v2.4.1/c3d4...
  Scope: ['read:config:*', 'read:deploy:*']

Deployer created
  ID:    spiffe://agentwrit.local/agent/deploy-pipeline/push-v2.4.1/e5f6...
  Scope: ['write:deploy:*']

Hop 1: Orchestrator → Analyst
  Delegating: ['read:config:production', 'read:deploy:web-service']
  Success! Chain depth: 1
  Delegated token: eyJhbGciOiJFZERTQSIsInR5cCI6...

  Hop 1 validated scope: ['read:config:production', 'read:deploy:web-service']
  Chain entries: 1

Hop 2: Analyst → Deployer (raw HTTP)
  Delegating: ['write:deploy:web-service']
  Using delegated token from hop 1 as Bearer
  Success! Token: eyJhbGciOiJFZERTQSIsInR5cCI6...
  Chain depth: 2
    [0] spiffe://.../release-v2.4.1/a1b2... → scope: ['read:config:*', ...]
    [1] spiffe://.../review-v2.4.1/c3d4... → scope: ['read:config:production', ...]

  Hop 2 validated scope: ['write:deploy:web-service']
  Chain entries: 2

── Scope Isolation ──

  Orchestrator CAN read staging config ✓
  Orchestrator CAN deploy payment-svc ✓
  Analyst CANNOT read staging config (only production) ✓
  Analyst CANNOT write deploy (read-only) ✓
  Analyst CAN read production config ✓
  Deployer CANNOT read configs ✓
  Deployer CANNOT deploy payment-svc ✓
  Deployer CAN deploy web-service ✓

All agents released.
```

---

## Key Takeaways

1. **The SDK's `delegate()` only works for single-hop delegation.** It always uses the agent's registration token. For multi-hop chains (A→B→C), the second hop must use the delegated token directly as a Bearer credential via raw HTTP.

2. **The chain records every hop.** After two hops, the `delegation_chain` has two entries — one for each delegation. Each entry records the delegator's SPIFFE ID, their scope at the time, and a timestamp. This creates a complete audit trail of who authorized what.

3. **Maximum depth is 5 hops.** The broker enforces a depth limit. A→B→C→D→E→F is the deepest chain allowed. If you try a 6th hop, the broker returns 403.

4. **No hop can widen scope.** The orchestrator has `read:config:*` and delegates `read:config:production` (narrower) — a design choice this example makes. The analyst cannot re-delegate `read:config:staging`: it doesn't hold that scope, so the broker rejects the delegation. Equal-scope delegation is accepted (narrowing is a pattern, not a rule); any widening is rejected.

5. **All three agents must be registered first.** Delegation targets a SPIFFE ID that already exists in the broker. You can't delegate to an agent you haven't created yet.
