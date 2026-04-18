# Sample Apps: Mini-Max

> **Purpose:** Teach the AgentWrit Python SDK through 10 real apps that solve actual problems.
> Each app is a working service or script. They teach by building, not by repeating concepts.
> **Audience:** Developers integrating AgentWrit into AI agent applications.
> **Prerequisites:** Python 3.10+, a running broker, app credentials from your operator.

---

## Broker Setup

**Before running any app, read the [Broker Setup Guide](sample-apps-broker-setup.md).**

Each app needs the broker configured with a **scope ceiling** that covers the scopes it requests. If the ceiling is too narrow, the broker returns `403` and no token is issued. The app cannot discover its own ceiling — the operator sets it, and the broker enforces it.

### Quick Reference: What Each App Needs

| App | Ceiling Must Include | Scopes App Requests |
|-----|----------------------|---------------------|
| 1 | `read:files:*`, `write:files:*` | `read:files:report-q3` |
| 2 | `read:customers:*` | `read:customers:customer-42`, `read:customers:customer-99` |
| 3 | `read:customers:*`, `write:orders:*`, `delete:customers:*`, `read:audit:all` | `read:customers:customer-42`, `write:orders:customer-42` |
| 4 | `read:data:*`, `write:data:*` | `read:data:source-batch-*`, `write:data:dest-batch-*` |
| 5 | N/A (admin auth only — no SDK) | None — uses raw HTTP admin auth |
| 6 | `read:data:*` | `read:data:sync-source` |
| 7 | `read:data:*` | `read:data:invoices:{tenant}`, `read:data:reports:{tenant}` |
| 8 | `send:webhooks:*` | `send:webhooks:order-confirmation` |
| 9 | `read:data:test`, `admin:revoke:*`, `read:logs:*` | `read:data:test` (succeeds), others intentionally fail |
| 10 | `read:monitoring:*` | `read:monitoring:alerts` |

**Run App 9 first** — it tests the ceiling. If denied tests pass, your ceiling is correctly set.

---

## Setup (once)

```bash
export AGENTWRIT_BROKER_URL="http://localhost:8080"
export AGENTWRIT_CLIENT_ID="your-client-id"
export AGENTWRIT_CLIENT_SECRET="your-client-secret"
```

---

## App 1: File Access Gate

**What it solves:** You have a storage service. You want agents to access only the files they are scoped for. The app acts as a gate — it validates the agent token before serving any file.

**What you learn:** How to use `validate()` to guard a resource server. How to extract scope from JWT claims and enforce it at the file level.

**Broker ceiling required:** `read:files:*`, `write:files:*`
**Scopes this app requests:** `read:files:report-q3`

```python
# app1_file_gate.py
"""
File access gate. Agents present tokens; this service checks their scope
before serving files.

Run:
  python app1_file_gate.py

Simulates:
  - Agent requests /files/report-q3  → allowed (scope: read:files:report-q3)
  - Agent requests /files/audit-log   → denied  (scope: read:files:report-q3 only)
"""
import os
from agentwrit import AgentWritApp, validate, scope_is_subset

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)

# Create a file-reading agent
agent = app.create_agent(
    orch_id="file-service",
    task_id="read-reports",
    requested_scope=["read:files:report-q3"],
)

# Simulate two file access requests
requests = [
    ("GET", "/files/report-q3"),
    ("GET", "/files/audit-log"),
    ("GET", "/files/report-q3"),  # same file again
]

for method, path in requests:
    # Extract the file identifier from the path
    file_id = path.replace("/files/", "")
    required_scope = [f"read:files:{file_id}"]

    # Gate 1: validate token at the broker
    result = validate(os.environ["AGENTWRIT_BROKER_URL"], agent.access_token)
    if not result.valid:
        print(f"{method} {path} → 401 TOKEN_INVALID")
        continue

    # Gate 2: check scope
    if result.claims and scope_is_subset(required_scope, result.claims.scope):
        print(f"{method} {path} → 200 OK")
    else:
        print(f"{method} {path} → 403 FORBIDDEN (scope too narrow)")

agent.release()
```

**The real-world pattern this teaches:**
- Resource servers (APIs, file stores, databases) receive Bearer tokens
- They call `validate()` to confirm the token is live
- They call `scope_is_subset()` to confirm the token covers the requested resource
- This is how you retrofit AgentWrit onto any existing service

---

## App 2: Customer API Gateway

**What it solves:** You have a REST API that serves customer data. You want agents to call it with scoped tokens. The gateway validates the token and scopes before forwarding the request.

**What you learn:** How to build a token-gated API proxy. How to extract the resource identifier from the request URL and match it against the token's scope.

**Broker ceiling required:** `read:customers:*`
**Scopes this app requests:** `read:customers:customer-42`, `read:customers:customer-99`

```python
# app2_api_gateway.py
"""
API gateway that proxies requests to a downstream customer API.
Only agents with matching scope can pass through.

This pattern wraps any existing REST API with AgentWrit security.
The downstream API never sees untrusted tokens — this gateway enforces scope.
"""
import os
import httpx
from agentwrit import AgentWritApp, validate, scope_is_subset

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)

DOWNSTREAM = "http://api.internal/v1"

def proxy_request(token: str, method: str, url: str, downstream_url: str) -> dict:
    """Validate token, check scope, then proxy to downstream."""
    # 1. Validate at broker
    result = validate(os.environ["AGENTWRIT_BROKER_URL"], token)
    if not result.valid:
        return {"status": 401, "body": "token invalid"}

    # 2. Extract resource ID from path — e.g. /customers/customer-42
    segments = url.strip("/").split("/")
    if len(segments) >= 2 and segments[0] == "customers":
        resource_id = segments[1]
        required_scope = [f"read:customers:{resource_id}"]
    else:
        return {"status": 400, "body": "unrecognized path"}

    # 3. Enforce scope
    if not scope_is_subset(required_scope, result.claims.scope):
        return {"status": 403, "body": f"scope {required_scope} not granted"}

    # 4. Proxy to downstream with the agent's token
    downstream_headers = {"Authorization": f"Bearer {token}"}
    resp = httpx.request(method, downstream_url, headers=downstream_headers, timeout=10)
    return {"status": resp.status_code, "body": resp.text}


agent = app.create_agent(
    orch_id="crm-gateway",
    task_id="fetch-customer-42",
    requested_scope=["read:customers:customer-42"],
)

test_cases = [
    ("GET", "/customers/customer-42", "http://api.internal/v1/customers/customer-42"),
    ("GET", "/customers/customer-99", "http://api.internal/v1/customers/customer-99"),
]

for method, url, downstream in test_cases:
    result = proxy_request(agent.access_token, method, url, downstream)
    print(f"{method} {url} → {result['status']}")

agent.release()
```

**The real-world pattern this teaches:**
- Agents hold tokens scoped to specific resources
- Your gateway sits in front of real infrastructure
- Before any request reaches downstream, the gateway validates and scopes
- This is how you add AgentWrit to an existing microservices architecture without changing downstream services

---

## App 3: LLM Tool Executor

**What it solves:** You have an LLM that decides which tools to call. You want to enforce that tool calls are only allowed if the agent has the right scope. The executor intercepts tool calls and gates them.

**What you learn:** How to build a scope-gated tool executor. The LLM decides what to do; the executor decides if it's allowed. This is the core pattern behind the MedAssist demo.

**Broker ceiling required:** `read:customers:*`, `write:orders:*`, `delete:customers:*`, `read:audit:all`
**Scopes this app requests:** `read:customers:customer-42`, `write:orders:customer-42`
**Note:** `delete:customers:*` and `read:audit:all` must be in the ceiling so the app can demonstrate denials — the app intentionally does not request them.

```python
# app3_llm_executor.py
"""
LLM tool executor with scope gating.
The LLM picks tools; this executor checks scope before running them.
The LLM can ask for anything — this decides what's actually allowed.
"""
import os
from agentwrit import AgentWritApp, scope_is_subset

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)

TOOLS = {
    "read_customer": {
        "scope": "read:customers:{}",
        "fn": lambda args: f"Customer: {args['customer_id']}, Balance: $120",
    },
    "write_order": {
        "scope": "write:orders:{}",
        "fn": lambda args: f"Order placed for {args['customer_id']}",
    },
    "read_audit": {
        "scope": "read:audit:all",
        "fn": lambda args: "Audit trail: 42 events",
    },
    "delete_customer": {
        "scope": "delete:customers:{}",
        "fn": lambda args: f"Customer {args['customer_id']} deleted",
    },
}


def execute_tool(agent_scope: list[str], tool_name: str, args: dict) -> str:
    """Check scope then execute the tool."""
    if tool_name not in TOOLS:
        return f"ERROR: unknown tool '{tool_name}'"

    tool = TOOLS[tool_name]
    identifier = args.get("customer_id", "*")
    required_scope = [tool["scope"].format(identifier)]

    if scope_is_subset(required_scope, agent_scope):
        return tool["fn"](args)
    else:
        return f"ACCESS DENIED: '{tool_name}' requires {required_scope}"


agent = app.create_agent(
    orch_id="llm-executor",
    task_id="agent-customer-42",
    requested_scope=["read:customers:customer-42", "write:orders:customer-42"],
)

print(f"Agent scope: {agent.scope}\n")

calls = [
    ("read_customer", {"customer_id": "customer-42"}),
    ("write_order", {"customer_id": "customer-42"}),
    ("delete_customer", {"customer_id": "customer-42"}),  # no delete scope
    ("read_audit", {}),  # no audit scope
    ("read_customer", {"customer_id": "customer-99"}),  # wrong customer
]

for tool_name, args in calls:
    result = execute_tool(agent.scope, tool_name, args)
    print(f"[{tool_name}] {args} → {result}")

agent.release()
```

**The real-world pattern this teaches:**
- The LLM is untrusted for security decisions — it picks actions, not authorization
- Every tool call is intercepted and scope-checked before execution
- Scope templates (`read:customers:{}`) are resolved at runtime with the real identifier
- This is the foundation of any LLM-driven workflow that needs security

---

## App 4: Data Pipeline Runner

**What it solves:** You have a batch job that reads from one partition, transforms data, and writes to another. You need separate agents for each stage, each with minimal scope.

**What you learn:** How to create multiple agents with different scopes for different pipeline stages. How to handle failure at any stage and release all agents cleanly.

**Broker ceiling required:** `read:data:*`, `write:data:*`
**Scopes this app requests:** `read:data:source-batch-101`, `read:data:source-batch-102`, `write:data:dest-batch-101`, `write:data:dest-batch-102`

```python
# app4_pipeline_runner.py
"""
Data pipeline with stage-separated agents.
Stage 1: read from partition
Stage 2: transform data
Stage 3: write results

Each stage gets only the scope it needs. If any stage fails, all agents are released.
"""
import os
from agentwrit import AgentWritApp, scope_is_subset

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)


def run_pipeline(batch_id: str) -> dict:
    reader = app.create_agent(
        orch_id="batch-pipeline",
        task_id=f"{batch_id}-read",
        requested_scope=[f"read:data:source-{batch_id}"],
    )
    transformer = app.create_agent(
        orch_id="batch-pipeline",
        task_id=f"{batch_id}-transform",
        requested_scope=[f"read:data:source-{batch_id}"],
    )
    writer = app.create_agent(
        orch_id="batch-pipeline",
        task_id=f"{batch_id}-write",
        requested_scope=[f"write:data:dest-{batch_id}"],
    )

    agents = [reader, transformer, writer]
    results = {}

    try:
        print(f"Running pipeline for batch: {batch_id}")

        if scope_is_subset([f"read:data:source-{batch_id}"], reader.scope):
            print(f"  [READER]   reading from source-{batch_id}")
            results["data"] = f"<data from source-{batch_id}>"

        if scope_is_subset([f"read:data:source-{batch_id}"], transformer.scope):
            print(f"  [TRANSFORMER] processing {results.get('data', '')}")
            results["transformed"] = results["data"].upper() if results.get("data") else ""

        if scope_is_subset([f"write:data:dest-{batch_id}"], writer.scope):
            print(f"  [WRITER]   writing to dest-{batch_id}")
            results["written"] = True
        else:
            raise PermissionError("Writer agent lacks write scope")

        print(f"  Pipeline complete: {results}")
        return results

    except Exception as e:
        print(f"  Pipeline failed: {e}")
        raise
    finally:
        for agent in agents:
            agent.release()
        print(f"  All agents released for batch {batch_id}")


run_pipeline("batch-101")
run_pipeline("batch-102")
```

**The real-world pattern this teaches:**
- Large tasks are split across specialized agents, each with minimal scope
- Failure in any stage triggers cleanup — `finally` blocks ensure all agents release
- A compromised reader cannot write — its scope doesn't allow it
- This pattern is production-grade: error handling, cleanup, and scope isolation together

---

## App 5: Audit Log Reader

**What it solves:** You need to read the broker's audit trail to investigate what agents did.

**What you learn:** Admin auth is not part of the SDK — it uses raw HTTP or `aactl`. The SDK only handles app-level operations. This app does not use `AgentWritApp`.

**Broker ceiling required:** N/A — no agent scopes, no SDK
**What it uses:** `AGENTWRIT_ADMIN_SECRET` for admin auth. `GET /v1/audit/events` with an admin Bearer token.

```python
# app5_audit_reader.py
"""
Audit log reader — queries the broker's hash-chained audit trail.
Shows who did what, when, and whether it succeeded.

Requires admin credentials (AGENTWRIT_ADMIN_SECRET). The SDK does not handle admin auth.
"""
import os
import httpx

BROKER_URL = os.environ["AGENTWRIT_BROKER_URL"]
ADMIN_SECRET = os.environ["AGENTWRIT_ADMIN_SECRET"]

# Step 1: Authenticate as admin (raw HTTP — not part of the SDK)
auth_resp = httpx.post(
    f"{BROKER_URL}/v1/admin/auth",
    json={"secret": ADMIN_SECRET},
    timeout=10,
)
auth_resp.raise_for_status()
admin_token = auth_resp.json()["access_token"]

print("=== Last 20 audit events ===")
events_resp = httpx.get(
    f"{BROKER_URL}/v1/audit/events",
    params={"limit": 20},
    headers={"Authorization": f"Bearer {admin_token}"},
    timeout=10,
)
events_resp.raise_for_status()
events = events_resp.json()

for event in events.get("events", []):
    ts = event.get("timestamp", "")
    event_type = event.get("event_type", "")
    agent_id = event.get("agent_id", "-")
    task_id = event.get("task_id", "-")
    outcome = event.get("outcome", "")

    status = "✓" if outcome == "success" else "✗" if outcome == "denied" else " "
    print(f"{status} [{ts}] {event_type:<30} agent={agent_id[-30:]} task={task_id}")

print(f"\nTotal events: {events.get('total', '?')}")

print("\n=== Token revocation events ===")
revoke_resp = httpx.get(
    f"{BROKER_URL}/v1/audit/events",
    params={"event_type": "token_revoked", "limit": 10},
    headers={"Authorization": f"Bearer {admin_token}"},
    timeout=10,
)
revoke_events = revoke_resp.json().get("events", [])
if revoke_events:
    for ev in revoke_events:
        print(f"  Revoked: {ev.get('detail', '')} at {ev.get('timestamp', '')}")
else:
    print("  No revocation events found")
```

**The real-world pattern this teaches:**
- Operators and compliance teams need to query the audit trail programmatically
- Admin auth uses `AGENTWRIT_ADMIN_SECRET` — not part of the SDK, done via raw HTTP or `aactl`
- Filtering by event type, agent, and time range lets you find specific incidents
- This is how you build automated compliance reporting

---

## App 6: Token Lifecycle Manager

**What it solves:** You have long-running background tasks. This app spawns an agent, runs a renewal loop that keeps the token fresh, and cleans up on exit.

**What you learn:** How to implement a renewal loop that handles expiry, how to handle revocation mid-task, and how to release cleanly on shutdown.

**Broker ceiling required:** `read:data:*`
**Scopes this app requests:** `read:data:sync-source`

```python
# app6_token_lifecycle.py
"""
Token lifecycle manager for long-running workers.
Spawns an agent, keeps the token fresh with renewal, handles revocation,
and releases on shutdown.

This is the pattern for background workers, cron jobs, and streaming pipelines.
"""
import os
import signal
import sys
import time
from agentwrit import AgentWritApp, validate
from agentwrit.errors import AgentWritError

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)

shutdown = False


def handle_signal(signum, frame):
    global shutdown
    print("\nShutdown signal received — releasing agent and exiting")
    shutdown = True


signal.signal(signal.SIGINT, handle_signal)
signal.signal(signal.SIGTERM, handle_signal)


def worker_loop(agent, interval: int = 60):
    """Run the worker, renewing the token every `interval` seconds."""
    iterations = 0
    while not shutdown:
        result = validate(os.environ["AGENTWRIT_BROKER_URL"], agent.access_token)
        if not result.valid:
            print(f"[{iterations}] Token invalid: {result.error} — stopping")
            break

        print(f"[{iterations}] Working... scope={agent.scope}")
        time.sleep(1)
        iterations += 1

        if agent.expires_in > 0:
            sleep_fraction = agent.expires_in * 0.8
            if time.time() % (sleep_fraction * 2) < 1:
                try:
                    agent.renew()
                    print(f"[{iterations}] Token renewed, new TTL={agent.expires_in}s")
                except AgentWritError as e:
                    print(f"[{iterations}] Renewal failed: {e} — stopping")
                    break


print("Creating worker agent...")
worker = app.create_agent(
    orch_id="background-worker",
    task_id="data-sync-worker",
    requested_scope=["read:data:sync-source"],
    max_ttl=300,
)

print(f"Worker agent: {worker.agent_id}")
print(f"Initial TTL:  {worker.expires_in}s")
print("Running worker loop (Ctrl+C to stop)...")

try:
    worker_loop(worker)
finally:
    worker.release()
    print("Worker agent released — cleanup complete")
```

**The real-world pattern this teaches:**
- Background workers need token renewal loops, not one-shot registrations
- The renewal loop validates first — if the token is dead, stop work immediately
- Signal handling ensures clean shutdown and release on SIGINT/SIGTERM
- This is how you build production-grade workers that run for hours or days

---

## App 7: Multi-Tenant Agent Factory

**What it solves:** You run a SaaS app where each customer (tenant) gets their own scoped agents. The factory creates agents on demand, each scoped to their tenant ID, without cross-contaminating data access.

**What you learn:** How to use tenant IDs as scope identifiers. How to create a factory that spawns scoped agents per tenant without hardcoding.

**Broker ceiling required:** `read:data:*`
**Scopes this app requests:** `read:data:invoices:{tenant_id}`, `read:data:reports:{tenant_id}`
**Note:** Tenant IDs (`acme-corp`, `globex`) are substituted at runtime. The ceiling must include `read:data:*` — specific tenant identifiers are not in the ceiling.

```python
# app7_tenant_factory.py
"""
Multi-tenant agent factory.
Each tenant gets agents scoped to their own data.
Tenants cannot see each other's data — enforced by scope, not code.
"""
import os
from agentwrit import AgentWritApp, scope_is_subset

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)


class TenantAgentFactory:
    """Creates per-tenant agents with isolated scopes."""

    def __init__(self, app: AgentWritApp):
        self.app = app
        self._cache: dict[str, object] = {}

    def get_agent(self, tenant_id: str, resource: str) -> object:
        """Get or create a scoped agent for a tenant/resource pair."""
        cache_key = f"{tenant_id}:{resource}"

        if cache_key not in self._cache:
            agent = self.app.create_agent(
                orch_id=f"tenant-{tenant_id}",
                task_id=f"access-{resource}",
                requested_scope=[f"read:data:{resource}:{tenant_id}"],
            )
            self._cache[cache_key] = agent
            print(f"  Created agent for {cache_key}: {agent.agent_id}")
        else:
            print(f"  Reusing cached agent for {cache_key}")

        return self._cache[cache_key]

    def release_all(self):
        for key, agent in list(self._cache.items()):
            agent.release()
            print(f"  Released: {key}")
        self._cache.clear()


def demo_tenant_access(factory: TenantAgentFactory):
    tenants = [
        ("acme-corp", "invoices"),
        ("globex", "invoices"),
        ("acme-corp", "reports"),
    ]

    for tenant_id, resource in tenants:
        agent = factory.get_agent(tenant_id, resource)

        required = [f"read:data:{resource}:{tenant_id}"]
        if scope_is_subset(required, agent.scope):
            print(f"  ✓ {tenant_id} can read {resource}")
        else:
            print(f"  ✗ {tenant_id} DENIED for {resource}")

        wrong_tenant = "acme-corp" if tenant_id != "acme-corp" else "globex"
        cross_scope = [f"read:data:{resource}:{wrong_tenant}"]
        if not scope_is_subset(cross_scope, agent.scope):
            print(f"  ✓ {tenant_id} CANNOT read {wrong_tenant}'s {resource} (isolated)")
        else:
            print(f"  ✗ ISOLATION FAILURE: {tenant_id} CAN read {wrong_tenant}'s data")

        print()


factory = TenantAgentFactory(app)
try:
    demo_tenant_access(factory)
finally:
    factory.release_all()
```

**The real-world pattern this teaches:**
- SaaS multi-tenancy is enforced by scope, not by code separation
- The factory caches agents per tenant to avoid re-registration overhead
- Cross-tenant isolation is provable — the scope system guarantees it
- This is how you build a secure shared infrastructure where tenants trust each other to be isolated

---

## App 8: Outbound Webhook Dispatcher

**What it solves:** Your AI agent needs to call external webhooks. You use the agent's scoped token as the Bearer credential so the webhook endpoint can validate it.

**What you learn:** How to use `Agent.access_token` as a Bearer credential for outbound HTTP calls. How to let the receiver validate the token.

**Broker ceiling required:** `send:webhooks:*`
**Scopes this app requests:** `send:webhooks:order-confirmation`

```python
# app8_webhook_dispatcher.py
"""
Outbound webhook dispatcher.
Agents send webhooks with their scoped token as Bearer auth.
The receiving service validates the token before processing the payload.

In production: replace WEBHOOK_URL with your real endpoint.
"""
import os
import httpx
from agentwrit import AgentWritApp, validate, scope_is_subset

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)

WEBHOOK_URL = "http://webhook-receiver.internal/hooks/deliver"

agent = app.create_agent(
    orch_id="notification-service",
    task_id="send-order-confirmation",
    requested_scope=["send:webhooks:order-confirmation"],
)


def dispatch_webhook(token: str, url: str, payload: dict) -> dict:
    required_scope = ["send:webhooks:order-confirmation"]

    result = validate(os.environ["AGENTWRIT_BROKER_URL"], token)
    if not result.valid:
        return {"sent": False, "reason": "token invalid"}

    if not scope_is_subset(required_scope, result.claims.scope):
        return {"sent": False, "reason": f"scope not granted: {required_scope}"}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
        "X-Agent-ID": result.claims.sub,
    }
    resp = httpx.post(url, json=payload, headers=headers, timeout=10)
    return {"sent": True, "status": resp.status_code, "body": resp.text[:100]}


payload = {
    "event": "order.confirmed",
    "order_id": "ord-9876",
    "customer_id": "customer-42",
    "items": [{"sku": "WIDGET-1", "qty": 3}],
}

result = dispatch_webhook(agent.access_token, WEBHOOK_URL, payload)
print(f"Webhook dispatch: {result}")

agent.release()
```

**The real-world pattern this teaches:**
- Agents don't just receive tokens — they use them as credentials for outbound calls
- The webhook receiver calls `validate()` to verify the token before processing
- This creates a two-way trust model: inbound tokens are validated, outbound tokens are too
- This is how you build event-driven architectures where AI agents trigger external systems

---

## App 9: Scope Ceiling Guard

**What it solves:** You want to see what happens when your app requests a scope outside its ceiling. The broker blocks it with `403` before issuing any token.

**What you learn:** How the broker enforces the scope ceiling. How to catch `AuthorizationError` when a scope is out of bounds. Why this is a security property.

**Broker ceiling required:** `read:data:test`, `admin:revoke:*`, `read:logs:*`
**Scopes this app requests:**
- `read:data:test` — inside ceiling → succeeds
- `admin:revoke:*` — inside ceiling (for this demo) → succeeds
- `read:logs:system` — inside ceiling (for this demo) → succeeds

**Note:** This demo's ceiling intentionally includes operator scopes so you can see the `403` errors. In production, those scopes would be outside your app's ceiling.

```python
# app9_scope_ceiling_guard.py
"""
Scope ceiling guard — demonstrates how the broker blocks out-of-bounds agents.

Your operator set a scope ceiling when registering your app.
Attempting to create an agent with scope outside that ceiling returns 403.
This app shows the error, its type, and why it's correct behavior.

WARNING: This app intentionally triggers errors to demonstrate error handling.
"""
import os
from agentwrit import AgentWritApp
from agentwrit.errors import AuthorizationError

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)


def create_with_scope(requested_scope: list[str]) -> bool:
    try:
        app.create_agent(
            orch_id="ceiling-test",
            task_id="test-scope",
            requested_scope=requested_scope,
        )
        return True
    except AuthorizationError as e:
        print(f"  Caught:       {type(e).__name__}")
        print(f"  HTTP status:  {e.status_code}")
        print(f"  Error code:   {e.problem.error_code}")
        print(f"  Detail:       {e.problem.detail}")
        return False


print("=== Testing scope ceiling ===\n")

print("Test 1: read:data:test (inside ceiling)")
result = create_with_scope(["read:data:test"])
if result:
    print("  → PASSED: scope was within ceiling")

print("\nTest 2: admin:revoke:asterisk (inside ceiling for this demo)")
result = create_with_scope(["admin:revoke:asterisk"])
if result:
    print("  → PASSED: scope was within ceiling (ceiling is too wide for production)")
else:
    print("  → BLOCKED: this scope is operator-only in production")

print("\nTest 3: read:logs:system (inside ceiling for this demo)")
result = create_with_scope(["read:logs:system"])
if result:
    print("  → PASSED: scope was within ceiling (ceiling is too wide for production)")
else:
    print("  → BLOCKED: 'logs' is not in your app's ceiling")

print("\n=== Ceiling enforcement summary ===")
print("The broker enforces the ceiling BEFORE consuming the launch token.")
print("A scope violation does NOT waste a single-use launch token.")
print("The operator's ceiling is the root of trust — apps cannot widen beyond it.")
```

**The real-world pattern this teaches:**
- The scope ceiling is a security boundary set by the operator
- Apps cannot escape their ceiling — this is enforced by the broker, not the SDK
- Scope ceiling violations happen at creation time, before any token is issued
- This is how operators control blast radius: if an app is compromised, it can only create agents within its ceiling

---

## App 10: Renewal Loop with Revocation Detection

**What it solves:** You have an agent that runs continuously. Revocation might happen mid-task (operator revokes during an incident). This app detects revocation and stops gracefully.

**What you learn:** How to combine `renew()` with `validate()` to detect revocation in a loop. How to build a loop that self-terminates when the token becomes invalid.

**Broker ceiling required:** `read:monitoring:*`
**Scopes this app requests:** `read:monitoring:alerts`
**Revocation test:** While the loop runs, revoke the agent in a separate terminal with `aactl revoke --level agent --target <spiffe-id>`

```python
# app10_renewal_with_revocation_detection.py
"""
Renewal loop with revocation detection.
The agent runs continuously, renewing its token as it approaches expiry.
If the token is revoked (by operator or release), the loop stops.

This is the pattern for any agent that needs to run beyond a single TTL window
while remaining responsive to revocation commands.
"""
import os
import time
from agentwrit import AgentWritApp, validate
from agentwrit.errors import AgentWritError

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)


def run_agent_loop(task_id: str, ttl: int = 300):
    agent = app.create_agent(
        orch_id="monitoring-service",
        task_id=task_id,
        requested_scope=["read:monitoring:alerts"],
        max_ttl=ttl,
    )

    print(f"Agent: {agent.agent_id}")
    print(f"TTL:   {agent.expires_in}s")
    print("Loop running... (Ctrl+C to stop)\n")

    iteration = 0
    max_iterations = 20
    last_renewal = time.time()
    renewal_interval = agent.expires_in * 0.8

    while iteration < max_iterations:
        result = validate(os.environ["AGENTWRIT_BROKER_URL"], agent.access_token)

        if not result.valid:
            print(f"[ITER {iteration}] Token invalid: {result.error}")
            print(f"[ITER {iteration}] Stopping loop — token is dead")
            return "revoked" if result.error else "expired"

        print(f"[ITER {iteration}] alive | TTL={agent.expires_in}s | scope={agent.scope}")

        elapsed = time.time() - last_renewal
        if elapsed >= renewal_interval:
            try:
                agent.renew()
                last_renewal = time.time()
                renewal_interval = agent.expires_in * 0.8
                print(f"[ITER {iteration}] renewed | new TTL={agent.expires_in}s")
            except AgentWritError as e:
                print(f"[ITER {iteration}] renew() failed: {e} — stopping")
                return "error"

        time.sleep(0.5)
        iteration += 1

    print("Loop complete (max iterations reached)")
    agent.release()
    return "complete"


outcome = run_agent_loop("continuous-monitor-001")
print(f"\nFinal outcome: {outcome}")
```

**To test revocation detection:**

In a second terminal, while the loop is running, revoke the agent:

```bash
export AGENTWRIT_BROKER_URL="http://localhost:8080"
export AGENTWRIT_ADMIN_SECRET="your-admin-secret"
aactl revoke --level agent --target "spiffe://agentwrit.local/agent/monitoring-service/continuous-monitor-001/..."
```

The loop will detect the dead token, print `"Token invalid: token_revoked"`, and stop.

**The real-world pattern this teaches:**
- Continuous agents must validate before every iteration — not just at the start
- Revocation detection prevents a compromised or revoked agent from continuing work
- The loop self-terminates on revocation — no zombie agents running on dead tokens
- This is the production pattern for any agent that runs longer than a single TTL

---

## Summary Table

| App | Problem Solved | Key Pattern |
|-----|----------------|-------------|
| 1 | File access with token validation | `validate()` + `scope_is_subset()` as a gate |
| 2 | Token-gated API proxy | Extract resource from URL, validate, proxy |
| 3 | LLM tool executor | LLM picks actions; executor checks scope first |
| 4 | Multi-stage pipeline | Separate agents per stage, cleanup on failure |
| 5 | Audit log investigation | Admin auth via raw HTTP, filter by type/agent |
| 6 | Long-running worker | Renewal loop, signal handling, clean shutdown |
| 7 | Multi-tenant SaaS | Tenant ID as scope identifier, factory pattern |
| 8 | Outbound webhook caller | Agent token as Bearer for downstream services |
| 9 | Scope ceiling enforcement | Catch `AuthorizationError`, understand ceiling |
| 10 | Renewal with revocation detection | Validate in loop, stop on dead token |

---

## Next Steps

| Guide | What You'll Learn |
|-------|-------------------|
| [Developer Guide](developer-guide.md) | Delegation chains, error handling, multi-agent patterns |
| [MedAssist Demo](../demo/) | Full multi-agent healthcare pipeline with LLM tool-calling |
| [API Reference](api-reference.md) | Every class, method, parameter, and exception |
