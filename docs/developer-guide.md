# Developer Guide

A comprehensive guide to building Python applications with the AgentAuth SDK. This covers credential management, multi-agent delegation, error handling, and framework integration.

## Table of Contents

- [Part 1: Agent Credentials](#part-1-agent-credentials)
- [Part 2: Multi-Agent Delegation](#part-2-multi-agent-delegation)
- [Part 3: Credential Lifecycle](#part-3-credential-lifecycle)
- [Part 4: Error Handling](#part-4-error-handling)
- [Part 5: Security Properties](#part-5-security-properties)
- [Part 6: Framework Integration](#part-6-framework-integration)
- [Complete Example](#complete-example)

---

## Part 1: Agent Credentials

### Connecting to the Broker

Every application starts by creating an `AgentAuthApp`. This authenticates your application with the broker — think of it as logging in your application (not your agent).

```python
import os
from agentauth import AgentAuthApp

client = AgentAuthApp(
    broker_url=os.environ["AGENTAUTH_BROKER_URL"],
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)
```

If the credentials are wrong, `AuthenticationError` is raised immediately — fail-fast at startup, not at runtime.

### Getting a Token

```python
token = client.get_token("data-reader", ["read:data:*"])
```

Behind the scenes, the SDK executes the full 8-step protocol:

```mermaid
graph LR
    A["1️⃣ Cache<br/>check"] --> B["2️⃣ App<br/>auth"]
    B --> C["3️⃣ Launch<br/>token"]
    C --> D["4️⃣ Ed25519<br/>keygen"]
    D --> E["5️⃣ Get<br/>challenge"]
    E --> F["6️⃣ Sign<br/>nonce"]
    F --> G["7️⃣ Register<br/>agent"]
    G --> H["8️⃣ Cache<br/>result"]

    style A fill:#dbeafe,stroke:#3b82f6,stroke-width:2px
    style D fill:#d1fae5,stroke:#10b981,stroke-width:2px
    style F fill:#d1fae5,stroke:#10b981,stroke-width:2px
    style H fill:#dcfce7,stroke:#22c55e,stroke-width:2px
```

The returned `token` is a JWT string. Use it as a standard Bearer credential:

```python
import requests

response = requests.get(
    "https://your-api/data/customers",
    headers={"Authorization": f"Bearer {token}"},
)
```

### Token Caching

Call `get_token` again with the same arguments — the SDK returns the cached token without contacting the broker:

```python
token1 = client.get_token("data-reader", ["read:data:*"])
token2 = client.get_token("data-reader", ["read:data:*"])
assert token1 == token2  # Same JWT, no broker call on the second request
```

Different scopes or agent names produce different tokens:

```python
read_token = client.get_token("reader", ["read:data:*"])
write_token = client.get_token("writer", ["write:data:*"])
# Different tokens with different scopes and different SPIFFE identities
```

```mermaid
graph TB
    subgraph Cache["🗃️ In-Memory Token Cache"]
        direction TB
        E1["<b>Key:</b> ('reader', frozenset({'read:data:*'}))<br/><b>Value:</b> JWT-abc123 · <i>expires in 4m</i>"]
        E2["<b>Key:</b> ('writer', frozenset({'write:data:*'}))<br/><b>Value:</b> JWT-def456 · <i>expires in 2m</i>"]
        E3["<b>Key:</b> ('reader', frozenset({'read:data:reports'}))<br/><b>Value:</b> JWT-ghi789 · <i>expires in 5m</i>"]
    end

    P1["Scope order invariant<br/>['a','b'] == ['b','a']"]
    P2["Auto-renewal at 80% TTL"]
    P3["Thread-safe via threading.Lock"]

    Cache --- P1
    Cache --- P2
    Cache --- P3

    style Cache fill:#f0f9ff,stroke:#0ea5e9,stroke-width:2px
    style P1 fill:#f5f5f5,stroke:#999
    style P2 fill:#f5f5f5,stroke:#999
    style P3 fill:#f5f5f5,stroke:#999
```

### Task and Orchestrator IDs

You can tag tokens with metadata that appears in the SPIFFE identity and audit log:

```python
token = client.get_token(
    "data-reader",
    ["read:data:*"],
    task_id="quarterly-analysis",
    orch_id="analytics-pipeline",
)
# SPIFFE ID: spiffe://agentauth.local/agent/analytics-pipeline/quarterly-analysis/{instance}
```

If omitted, `task_id` defaults to `"default"` and `orch_id` defaults to `"sdk"`.

---

## Part 2: Multi-Agent Delegation

In multi-agent pipelines, an orchestrator agent might need to give a worker agent a subset of its own permissions.

### Delegating Scope

Agent A has `read:data:*` but Agent B only needs `read:data:results`:

```python
# Orchestrator gets its credential
orchestrator_token = client.get_token(
    "orchestrator",
    ["read:data:*"],
    task_id="pipeline-001",
)

# Worker registers and gets its own credential
worker_token = client.get_token(
    "worker",
    ["read:data:logs"],
    task_id="pipeline-001",
)

# Get the worker's SPIFFE ID from its token claims
worker_claims = client.validate_token(worker_token)
worker_id = worker_claims["claims"]["sub"]

# Orchestrator delegates narrower scope to the worker
delegated_token = client.delegate(
    token=orchestrator_token,
    to_agent_id=worker_id,
    scope=["read:data:results"],  # Must be subset of orchestrator's scope
    ttl=120,
)
```

### Delegation Rules

```mermaid
graph TD
    O["<b>Orchestrator</b><br/>read:data:*"]

    O -->|"✅ subset"| WA["<b>Worker A</b><br/>read:data:results"]
    O -->|"✅ subset"| WB["<b>Worker B</b><br/>read:data:logs"]
    O -.->|"❌ not in scope"| WC["<b>Worker C</b><br/>write:data:records"]

    WA -->|"✅ subset"| SW["<b>Sub-worker</b><br/>read:data:results"]
    WA -.->|"❌ wider than A"| SW2["<b>Sub-worker</b><br/>read:data:*"]

    style O fill:#3b82f6,color:#fff,stroke:#1d4ed8,stroke-width:2px
    style WA fill:#22c55e,color:#fff,stroke:#16a34a,stroke-width:2px
    style WB fill:#22c55e,color:#fff,stroke:#16a34a,stroke-width:2px
    style WC fill:#ef4444,color:#fff,stroke:#dc2626,stroke-width:2px
    style SW fill:#f59e0b,color:#fff,stroke:#d97706,stroke-width:2px
    style SW2 fill:#ef4444,color:#fff,stroke:#dc2626,stroke-width:2px
```

- Scope can only **narrow** at each hop, never widen
- Maximum delegation depth is 5 hops
- Each link in the chain is cryptographically signed
- Revoking Agent A's token invalidates all downstream delegations

---

## Part 3: Credential Lifecycle

### Revoking When Done

When your agent finishes its task, revoke its credentials:

```python
client.revoke_token(token)
```

After revocation, the token is immediately invalid:

```python
result = client.validate_token(token)
assert result["valid"] is False  # Broker rejects it
```

### Why Revoke?

Tokens expire naturally (default 5 minutes), but explicit revocation provides additional security:

- **Shrinks the attack window** — if a token is stolen, it is already dead
- **Signals task completion** — the broker logs `token_released` in the audit trail
- **Demonstrates intent** — the agent explicitly surrendered access

### Online Validation

Validate any token against the broker at any time:

```python
result = client.validate_token(token)

if result["valid"]:
    claims = result["claims"]
    print(f"Subject: {claims['sub']}")      # SPIFFE ID
    print(f"Scope: {claims['scope']}")       # Granted scope
    print(f"Expires: {claims['exp']}")       # Expiration timestamp
else:
    print(f"Invalid: {result.get('error')}")  # "token revoked", "token expired", etc.
```

---

## Part 4: Error Handling

### Exception Hierarchy

All SDK exceptions inherit from `AgentAuthError`, so you can catch broadly or narrowly:

```mermaid
graph TD
    Base["<b>AgentAuthError</b><br/><i>Base exception</i>"]

    Base --> Auth["<b>AuthenticationError</b><br/>HTTP 401 · Bad credentials"]
    Base --> Scope["<b>ScopeCeilingError</b><br/>HTTP 403 · Scope exceeds ceiling"]
    Base --> Rate["<b>RateLimitError</b><br/>HTTP 429 · Too many requests"]
    Base --> Unavail["<b>BrokerUnavailableError</b><br/>5xx · Connection failure"]

    style Base fill:#dc2626,color:#fff,stroke:#991b1b,stroke-width:2px
    style Auth fill:#ef4444,color:#fff,stroke:#dc2626
    style Scope fill:#ef4444,color:#fff,stroke:#dc2626
    style Rate fill:#ef4444,color:#fff,stroke:#dc2626
    style Unavail fill:#ef4444,color:#fff,stroke:#dc2626
```

```python
from agentauth import AgentAuthError, ScopeCeilingError

try:
    token = client.get_token("agent", scope)
except ScopeCeilingError as e:
    # Fix the scope or contact your operator
    print(f"Scope too broad: {e}")
except AgentAuthError:
    # Catch everything else from the SDK
    ...
```

### Scope Ceiling Violations

If you request a scope your app is not allowed to have:

```python
from agentauth import ScopeCeilingError

try:
    token = client.get_token("rogue", ["admin:everything:*"])
except ScopeCeilingError as e:
    print(e)
    # "requested scopes exceed app ceiling; allowed: [read:data:* write:data:*]"
```

### Broker Unavailability

The SDK retries transient failures with exponential backoff automatically. You only see `BrokerUnavailableError` if all retries are exhausted:

```python
from agentauth import BrokerUnavailableError

try:
    token = client.get_token("agent", ["read:data:*"])
except BrokerUnavailableError:
    # All retries exhausted — broker is down
    ...
```

### Rate Limiting

The SDK respects `Retry-After` headers automatically. `RateLimitError` is raised only when all retries are exhausted:

```python
from agentauth import RateLimitError

try:
    token = client.get_token("agent", ["read:data:*"])
except RateLimitError as e:
    print(f"Retry after {e.retry_after} seconds")
```

### Retry Behavior Summary

```mermaid
flowchart TD
    Req["📡 HTTP Request"] --> Check{"Response<br/>Status?"}

    Check -->|"2xx · 3xx · 4xx<br/>(not 429)"| OK["✅ Return Response"]
    Check -->|"429"| RL["⏳ Sleep per Retry-After"]
    Check -->|"5xx"| BK["⏳ Exponential Backoff<br/>1s → 2s → 4s"]
    Check -->|"Connection Error"| BK2["⏳ Exponential Backoff<br/>1s → 2s → 4s"]

    RL --> Retry{"Retries<br/>remaining?"}
    BK --> Retry
    BK2 --> Retry

    Retry -->|"Yes"| Req
    Retry -->|"No (was 429)"| RLE["❌ RateLimitError"]
    Retry -->|"No (was 5xx/conn)"| BUE["❌ BrokerUnavailableError"]

    style OK fill:#dcfce7,stroke:#22c55e,stroke-width:2px
    style RLE fill:#fee2e2,stroke:#ef4444,stroke-width:2px
    style BUE fill:#fee2e2,stroke:#ef4444,stroke-width:2px
    style Req fill:#dbeafe,stroke:#3b82f6,stroke-width:2px
```

---

## Part 5: Security Properties

When you use this SDK, these security properties are enforced automatically:

| Property | What It Means For You |
|----------|----------------------|
| **Ephemeral keys** | Every `get_token` call generates a fresh Ed25519 keypair in memory. The private key never touches disk. Even if your process is dumped, the key only exists in volatile memory. |
| **Task-scoped tokens** | Agents can only access what they request, within the app's scope ceiling. No master keys. |
| **Short TTLs** | Tokens expire in minutes. A stolen token is useless quickly. |

| **Scope attenuation** | Delegation can only narrow permissions. An agent cannot grant more access than it has. |
| **Thread safety** | Token cache and app auth state are protected by locks. Safe for concurrent agents. |
| **TLS by default** | Broker connections verify TLS certificates. No silent `verify=False`. |
| **No secret leakage** | `client_secret` never appears in error messages, repr output, or logs. |

---

## Part 6: Framework Integration

### FastAPI

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends
from agentauth import AgentAuthApp

# Initialize once at startup
client: AgentAuthApp | None = None

@asynccontextmanager
async def lifespan(app: FastAPI):
    global client
    client = AgentAuthApp(broker_url, client_id, client_secret)
    yield

app = FastAPI(lifespan=lifespan)

def get_client() -> AgentAuthApp:
    assert client is not None
    return client

@app.post("/analyze")
def analyze(client: AgentAuthApp = Depends(get_client)):
    token = client.get_token("analyzer", ["read:data:*"])
    # Use the token...
    return {"status": "complete"}
```

### Flask

```python
from flask import Flask
from agentauth import AgentAuthApp

app = Flask(__name__)

# Initialize once at module level
client = AgentAuthApp(broker_url, client_id, client_secret)

@app.route("/analyze", methods=["POST"])
def analyze():
    token = client.get_token("analyzer", ["read:data:*"])
    # Use the token...
    return {"status": "complete"}
```

### Background Workers (Celery)

```python
from celery import Celery
from agentauth import AgentAuthApp

app = Celery("tasks", broker="redis://localhost:6379")

# Initialize per-worker (one client per process)
client = AgentAuthApp(broker_url, client_id, client_secret)

@app.task
def process_data(task_id: str):
    token = client.get_token(
        "worker",
        ["read:data:*"],
        task_id=task_id,
    )
    try:
        # Do work with the token...
        pass
    finally:
        client.revoke_token(token)
```

---

## Complete Example

A data pipeline agent that reads, analyzes, writes, and cleans up:

```python
"""Data pipeline agent with credential lifecycle management."""

import os
import requests as http
from agentauth import AgentAuthApp

# Connect to the broker
client = AgentAuthApp(
    broker_url=os.environ["AGENTAUTH_BROKER_URL"],
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)

# Step 1: Get read credentials
read_token = client.get_token(
    "data-reader",
    ["read:data:*"],
    task_id="quarterly-analysis",
    orch_id="analytics-pipeline",
)
print(f"Read token issued: {read_token[:40]}...")

# Step 2: Use the read token to access data
data = http.get(
    "https://api.internal/customers",
    headers={"Authorization": f"Bearer {read_token}"},
).json()
print(f"Read {len(data)} customer records")

# Step 3: Get write credentials
write_token = client.get_token(
    "risk-writer",
    ["write:data:records"],
    task_id="quarterly-analysis",
)

# Step 4: Write results
http.post(
    "https://api.internal/risk-assessments",
    headers={"Authorization": f"Bearer {write_token}"},
    json={"customer": "TechStart Inc", "risk": "medium"},
)

# Step 5: Revoke all credentials when done
client.revoke_token(read_token)
client.revoke_token(write_token)
print("All credentials revoked. Pipeline complete.")
```

---

## Next Steps

| Guide | What You'll Learn |
|-------|-------------------|
| [API Reference](api-reference.md) | Complete method signatures and exception reference |
| [Concepts](concepts.md) | Architecture, security model, and standards alignment |
