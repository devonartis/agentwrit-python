# App 2: Multi-Tenant Data Pipeline

## The Scenario

You run a SaaS analytics platform with three tenants: a hospital chain, a bank, and a retailer. Every night, a data pipeline extracts each tenant's analytics data, transforms it, and writes reports. Each tenant's data must be completely isolated — the hospital's patient analytics must never be accessible by the agent processing the bank's financial data, even though both agents run in the same pipeline.

This app creates three agents — one per tenant — each with scopes limited to that tenant's data. The pipeline processes all three tenants in sequence, proving that each agent can only touch its own data.

---

## What You'll Learn

| Concept | Why It Matters |
|---------|---------------|
| **Multiple agents from one `AgentAuthApp`** | A single app can create many agents — each with different scopes |
| **Scope isolation between agents** | Agents with different scopes cannot access each other's data |
| **`scope_is_subset()` for multi-tenant boundaries** | How to enforce tenant isolation at the application layer |
| **Batch agent lifecycle** | Create → use → release for each agent in a loop |
| **Unique SPIFFE IDs per agent** | Every agent gets a distinct identity for audit purposes |

---

## Architecture

```
┌──────────────────────────────────────────────────────┐
│  Data Pipeline Script                                 │
│                                                       │
│  for tenant in [hospital, bank, retail]:              │
│    1. create_agent(scope: tenant-specific)            │
│    2. extract_data(agent, tenant)   ← scope check     │
│    3. transform_data(agent, tenant) ← scope check     │
│    4. write_report(agent, tenant)   ← scope check     │
│    5. release(agent)                                  │
│                                                       │
│  Verify: hospital agent cannot read bank data         │
│  Verify: bank agent cannot write hospital reports     │
└──────────────────────────────────────────────────────┘
```

Each tenant agent gets scopes like:
- Hospital: `read:analytics:hospital`, `write:reports:hospital`
- Bank: `read:analytics:bank`, `write:reports:bank`
- Retail: `read:analytics:retail`, `write:reports:retail`

---

## The Code

```python
# data_pipeline.py
# Run: python data_pipeline.py

from __future__ import annotations

import os
import sys
import time

from agentauth import AgentAuthApp, Agent, scope_is_subset, validate
from agentauth.errors import AgentAuthError


# ── Tenant Definitions ──────────────────────────────────────────
# In a real system, these come from a database. Here we define them
# statically to keep the app self-contained.

TENANTS: dict[str, dict[str, str]] = {
    "hospital": {
        "name": "Metro Health System",
        "data_type": "patient analytics",
        "read_scope": "read:analytics:hospital",
        "write_scope": "write:reports:hospital",
    },
    "bank": {
        "name": "First National Bank",
        "data_type": "financial analytics",
        "read_scope": "read:analytics:bank",
        "write_scope": "write:reports:bank",
    },
    "retail": {
        "name": "ShopWave Corp",
        "data_type": "sales analytics",
        "read_scope": "read:analytics:retail",
        "write_scope": "write:reports:retail",
    },
}

# Mock data stores per tenant (simulates separate databases)
MOCK_DATA: dict[str, dict[str, str]] = {
    "hospital": {"patient_visits": "12,847", "avg_stay": "3.2 days", "readmit_rate": "4.1%"},
    "bank": {"transactions": "2.4M", "avg_balance": "$8,420", "fraud_rate": "0.02%"},
    "retail": {"orders": "847K", "avg_order": "$67.30", "return_rate": "8.4%"},
}


def run_pipeline_for_tenant(app: AgentAuthApp, tenant_id: str) -> None:
    """Run the full ETL pipeline for one tenant using a scoped agent."""

    tenant = TENANTS[tenant_id]
    requested_scope = [tenant["read_scope"], tenant["write_scope"]]

    print(f"── {tenant['name']} ({tenant_id}) ──")
    print(f"   Data type: {tenant['data_type']}")

    # Create an agent scoped to THIS tenant only
    agent = app.create_agent(
        orch_id="nightly-pipeline",
        task_id=f"etl-{tenant_id}-{int(time.time())}",
        requested_scope=requested_scope,
    )

    print(f"   Agent:    {agent.agent_id}")
    print(f"   Scope:    {agent.scope}")
    print(f"   Expires:  {agent.expires_in}s")

    try:
        # ── Extract ────────────────────────────────────────────
        extract_scope = [tenant["read_scope"]]
        if scope_is_subset(extract_scope, agent.scope):
            data = MOCK_DATA[tenant_id]
            print(f"   [EXTRACT] Pulled {tenant['data_type']}: {data}")
        else:
            print(f"   [DENIED]   Cannot read {tenant_id} data")
            return

        # ── Transform (still needs read scope) ─────────────────
        if scope_is_subset(extract_scope, agent.scope):
            report = {k: v.upper() for k, v in data.items()}
            print(f"   [TRANSFORM] Processed data for report")
        else:
            print(f"   [DENIED]   Cannot transform — no read access")
            return

        # ── Load / Write Report ────────────────────────────────
        write_scope = [tenant["write_scope"]]
        if scope_is_subset(write_scope, agent.scope):
            print(f"   [LOAD]     Report written to reports/{tenant_id}/latest.json")
        else:
            print(f"   [DENIED]   Cannot write report for {tenant_id}")
            return

    finally:
        agent.release()
        print(f"   [RELEASE]  Agent released for {tenant_id}")

    print()


def run_cross_tenant_check(app: AgentAuthApp) -> None:
    """Prove that a tenant agent cannot access another tenant's data."""

    print("── Cross-Tenant Isolation Test ──")
    print()

    # Create an agent for the hospital tenant
    hospital_agent = app.create_agent(
        orch_id="nightly-pipeline",
        task_id="cross-tenant-test",
        requested_scope=[
            TENANTS["hospital"]["read_scope"],
            TENANTS["hospital"]["write_scope"],
        ],
    )

    print(f"Hospital agent scope: {hospital_agent.scope}")
    print()

    # Try to read bank data with hospital agent
    bank_read = [TENANTS["bank"]["read_scope"]]
    if scope_is_subset(bank_read, hospital_agent.scope):
        print("  FAIL: Hospital agent can read bank data!")
        sys.exit(1)
    else:
        print(f"  [BLOCKED] Hospital agent cannot read bank data")
        print(f"            Required: {bank_read}")
        print(f"            Held:     {hospital_agent.scope}")

    # Try to write retail reports with hospital agent
    retail_write = [TENANTS["retail"]["write_scope"]]
    if scope_is_subset(retail_write, hospital_agent.scope):
        print("  FAIL: Hospital agent can write retail reports!")
        sys.exit(1)
    else:
        print(f"  [BLOCKED] Hospital agent cannot write retail reports")
        print(f"            Required: {retail_write}")
        print(f"            Held:     {hospital_agent.scope}")

    # Confirm hospital agent CAN read its own data
    hospital_read = [TENANTS["hospital"]["read_scope"]]
    if scope_is_subset(hospital_read, hospital_agent.scope):
        print(f"  [ALLOWED] Hospital agent can read its own data ✓")
    else:
        print("  FAIL: Hospital agent cannot read its own data!")
        sys.exit(1)

    hospital_agent.release()
    print()
    print("Cross-tenant isolation verified.")


def main() -> None:
    app = AgentAuthApp(
        broker_url=os.environ["AGENTAUTH_BROKER_URL"],
        client_id=os.environ["AGENTAUTH_CLIENT_ID"],
        client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
    )

    print("Nightly Analytics Pipeline")
    print("=" * 55)
    print()

    # Process each tenant
    for tenant_id in TENANTS:
        run_pipeline_for_tenant(app, tenant_id)

    # Prove isolation
    run_cross_tenant_check(app)

    print()
    print("Pipeline complete. All tenants processed with isolated scopes.")


if __name__ == "__main__":
    main()
```

---

## Setup Requirements

This app uses the **universal sample app** registered in the [README setup](README.md#one-time-setup-for-all-sample-apps). If you've already registered it, skip to Running It.

### Which Ceiling Scopes This App Uses

| Ceiling Scope | What This App Requests | Why |
|--------------|----------------------|-----|
| `read:analytics:*` | `read:analytics:hospital`, `read:analytics:bank`, `read:analytics:retail` | Each tenant agent reads its own analytics data |
| `write:reports:*` | `write:reports:hospital`, `write:reports:bank`, `write:reports:retail` | Each tenant agent writes its own report |

The ceiling uses wildcards so the app can create agents for **any** tenant. Each agent still gets a scope limited to one specific tenant.

> **If the broker returns `AuthorizationError (403)`, the app's ceiling doesn't include `read:analytics:*` or `write:reports:*`.** Re-register with the universal ceiling (see [README setup](README.md#one-time-setup-for-all-sample-apps)).

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

uv run python data_pipeline.py
```

---

## Expected Output

```
Nightly Analytics Pipeline
=======================================================

── Metro Health System (hospital) ──
   Data type: patient analytics
   Agent:    spiffe://agentauth.local/agent/nightly-pipeline/etl-hospital-.../a1b2...
   Scope:    ['read:analytics:hospital', 'write:reports:hospital']
   Expires:  300s
   [EXTRACT] Pulled patient analytics: {'patient_visits': '12,847', ...}
   [TRANSFORM] Processed data for report
   [LOAD]     Report written to reports/hospital/latest.json
   [RELEASE]  Agent released for hospital

── First National Bank (bank) ──
   Data type: financial analytics
   Agent:    spiffe://agentauth.local/agent/nightly-pipeline/etl-bank-.../c3d4...
   Scope:    ['read:analytics:bank', 'write:reports:bank']
   Expires:  300s
   [EXTRACT] Pulled financial analytics: {'transactions': '2.4M', ...}
   [TRANSFORM] Processed data for report
   [LOAD]     Report written to reports/bank/latest.json
   [RELEASE]  Agent released for bank

── ShopWave Corp (retail) ──
   Data type: sales analytics
   ...

── Cross-Tenant Isolation Test ──

Hospital agent scope: ['read:analytics:hospital', 'write:reports:hospital']

  [BLOCKED] Hospital agent cannot read bank data
            Required: ['read:analytics:bank']
            Held:     ['read:analytics:hospital', 'write:reports:hospital']
  [BLOCKED] Hospital agent cannot write retail reports
            Required: ['write:reports:retail']
            Held:     ['read:analytics:hospital', 'write:reports:hospital']
  [ALLOWED] Hospital agent can read its own data ✓

Cross-tenant isolation verified.

Pipeline complete. All tenants processed with isolated scopes.
```

---

## Key Takeaways

1. **One app, many agents.** A single `AgentAuthApp` instance creates as many agents as you need. Each agent has its own scope, identity, and token. The app's scope ceiling limits what any agent can request.

2. **Scope segments are your tenant boundary.** The identifier segment of the scope (`read:analytics:hospital` vs `read:analytics:bank`) is what enforces tenant isolation. This works because wildcards only apply in the identifier position — `read:analytics:*` would match all tenants, but a specific identifier matches only that tenant.

3. **`scope_is_subset()` is local and fast.** You don't need a broker call to check scope — the SDK does it locally. This means you can check scope before every database query, API call, or file read without adding latency.

4. **Each agent gets a unique SPIFFE ID.** When you audit the pipeline later, you can trace exactly which agent processed which tenant. The `task_id` includes the tenant name, making correlation trivial.

5. **Release each agent when its work is done.** Don't hold tokens open for the entire pipeline if they're only needed for one tenant. Create → process → release per tenant keeps the attack window minimal.
