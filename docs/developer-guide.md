# Developer Guide

Patterns for building real applications with the AgentWrit SDK. This guide assumes you've read [Getting Started](getting-started.md) and [Concepts](concepts.md), and that you've completed [Prerequisites](../README.md#prerequisites) — broker reachable, app credentials provisioned, env vars set.

---

## Agent Lifecycle Management

Every agent follows the same lifecycle: create, use, release. The pattern looks the same whether you're building a REST API, a batch job, or an LLM orchestrator.

### Basic Pattern

```python
import os
from agentwrit import AgentWritApp

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)

# Create the agent for a specific task
agent = app.create_agent(
    orch_id="my-service",
    task_id="process-order-123",
    requested_scope=["read:data:order-123", "write:data:order-123-result"],
)

try:
    # Do work with the agent's token. For HTTP calls, agent.bearer_header
    # gives you {"Authorization": "Bearer <token>"} in one shot:
    httpx.post("https://orders/api/process", headers=agent.bearer_header, json=payload)
finally:
    # Always release — even if the work failed
    agent.release()
```

Always release in a `finally` block. If your code crashes, the token expires naturally after its TTL, but explicit release is faster and cleaner.

### Long-Running Tasks

If your task runs longer than the token TTL (default 300 seconds), renew the token:

```python
agent = app.create_agent(
    orch_id="export-service",
    task_id="large-export",
    requested_scope=["read:data:export-batch"],
)

try:
    for chunk in large_dataset:
        process(chunk, agent.access_token)
        
        # Renew periodically — the agent_id stays the same
        agent.renew()
finally:
    agent.release()
```

After `renew()`:
- `agent.access_token` is a new JWT
- `agent.agent_id` is unchanged (same SPIFFE identity)
- The old token is revoked at the broker
- `agent.expires_in` is reset

> The broker may enforce a maximum total agent lifetime independent of per-token TTL. If `renew()` starts failing on long-running agents, check your broker's session policy.

### Short-Lived Tasks with Custom TTL

For quick tasks, set a short TTL to minimize exposure:

```python
agent = app.create_agent(
    orch_id="quick-check",
    task_id="verify-customer",
    requested_scope=["read:data:customer-7291"],
    max_ttl=30,  # Token expires in 30 seconds
)
# If you forget to release, the token dies in 30 seconds anyway
```

### Multiple Agents with Isolated Scopes

Create separate agents for separate tasks. Each agent has its own identity and scope — compromising one doesn't affect the others:

```python
reader = app.create_agent(
    orch_id="data-service",
    task_id="read-customers",
    requested_scope=["read:data:customers-west"],
)

writer = app.create_agent(
    orch_id="data-service",
    task_id="write-reports",
    requested_scope=["write:data:quarterly-report-q3"],
)

# reader cannot write, writer cannot read
# They have different SPIFFE IDs and different tokens
```

---

## Delegation

Delegation is how one agent passes a subset of its authority to another agent. The broker issues a new token for the delegate scoped to what was requested — equal to or narrower than the delegator's own scope. Delegation cannot widen authority; any scope the delegator doesn't hold is rejected.

### Single-Hop Delegation

Agent A has broad scope and delegates a subset to Agent B:

```python
agent_a = app.create_agent(
    orch_id="pipeline",
    task_id="orchestrator",
    requested_scope=["read:data:partition-7", "read:data:partition-8"],
)
agent_b = app.create_agent(
    orch_id="pipeline",
    task_id="worker-p7",
    requested_scope=["read:data:partition-7"],
)

# A delegates only partition-7 to B
delegated = agent_a.delegate(
    delegate_to=agent_b.agent_id,
    scope=["read:data:partition-7"],
)

# delegated.access_token is a NEW JWT for B with only partition-7
# delegated.expires_in is the TTL (default 60 seconds)
# delegated.delegation_chain records the hop
```

Pass `ttl=N` to override the delegation lifetime: `agent_a.delegate(delegate_to=..., scope=..., ttl=300)`. Omit it to take the broker's default (60s).

Always validate the delegated token to confirm the broker issued the scope you requested:

```python
from agentwrit import validate

result = validate(app.broker_url, delegated.access_token)
assert result.valid
assert result.claims.scope == ["read:data:partition-7"]
# partition-8 is NOT in the delegated token
```

### Multi-Hop Delegation (A → B → C)

> **SDK limitation:** `agent.delegate()` only signs with the agent's own *registration* token. To extend a chain — i.e., delegate from a token you *received* — you currently have to call `POST /v1/delegate` directly, as shown below. A future release may add `DelegatedToken.delegate()` to remove this escape hatch.

To build a real chain where each hop narrows further (a common pattern — delegation doesn't require narrowing, but most chain designs choose to), the second hop has to bypass the SDK and hit the broker endpoint with the delegated token:

```python
import httpx

# A has 3 scopes
agent_a = app.create_agent(
    orch_id="pipeline",
    task_id="manager",
    requested_scope=[
        "read:data:partition-7",
        "read:data:partition-8",
        "write:data:results",
    ],
)
agent_b = app.create_agent(
    orch_id="pipeline",
    task_id="analyst",
    requested_scope=["read:data:partition-7", "read:data:partition-8"],
)
agent_c = app.create_agent(
    orch_id="pipeline",
    task_id="reader",
    requested_scope=["read:data:partition-7"],
)

# Hop 1: A delegates 2 of 3 scopes to B (drops write)
delegated_ab = agent_a.delegate(
    delegate_to=agent_b.agent_id,
    scope=["read:data:partition-7", "read:data:partition-8"],
)

# Hop 2: Use the delegated token to delegate further (raw HTTP)
resp = httpx.post(
    f"{app.broker_url}/v1/delegate",
    json={
        "delegate_to": agent_c.agent_id,
        "scope": ["read:data:partition-7"],
    },
    headers={"Authorization": f"Bearer {delegated_ab.access_token}"},
)
delegated_bc = resp.json()

# C now has only partition-7, and the chain records both hops
```

### Delegation Failures

If an agent tries to delegate scope it doesn't have:

```python
from agentwrit.errors import AuthorizationError

try:
    agent_a.delegate(
        delegate_to=agent_b.agent_id,
        scope=["read:data:partition-9"],  # A doesn't have this
    )
except AuthorizationError as e:
    print(e.status_code)        # 403
    print(e.problem.error_code) # scope_violation
    print(e.problem.detail)     # delegated scope exceeds delegator scope
```

### Delegation Behavior

Verified against a live broker via the acceptance suite:

1. **Same-scope delegation is allowed.** The broker treats equal as a valid subset. If A has `["read:data:partition-7"]` and delegates `["read:data:partition-7"]` to B, the broker accepts it.

2. **The delegated token can have MORE scope than B's registration scope.** If A has 3 scopes and delegates all 3 to B (who was registered with only 1), B's delegated token carries all 3 scopes. The delegation doesn't check B's registration scope — it only checks that the delegated scope is a subset of A's scope.

3. **Delegation chain entries record the delegator's full scope** at the time of delegation, not just what was delegated. This is for audit trail purposes.

---

## Scope Gating

The app is responsible for checking scope before allowing agent actions. The broker sets the scope at creation time, but the app must enforce it at runtime.

### The Pattern

```python
from agentwrit import scope_is_subset

agent = app.create_agent(
    orch_id="customer-service",
    task_id="lookup",
    requested_scope=["read:data:customer-7291"],
)

def handle_action(action_scope: list[str]) -> bool:
    """Check if the agent is authorized for this action."""
    if scope_is_subset(action_scope, agent.scope):
        return True  # proceed
    return False  # block

# Authorized
handle_action(["read:data:customer-7291"])    # True

# Blocked — different identifier
handle_action(["read:data:all-customers"])     # False

# Blocked — different action
handle_action(["write:data:customer-7291"])   # False
```

### Validating with the Broker

For zero-trust enforcement, validate the token with the broker AND check scope:

```python
from agentwrit import validate, scope_is_subset

result = validate(app.broker_url, agent.access_token)
if result.valid and result.claims:
    # Token is live — now check scope
    if scope_is_subset(required_scope, result.claims.scope):
        # proceed
        ...
    else:
        # token is valid but doesn't have the right scope
        ...
else:
    # token is dead (expired, revoked, or fake)
    ...
```

---

## Error Handling

### Catching Specific Errors

```python
from agentwrit.errors import (
    AgentWritError,
    AuthenticationError,
    AuthorizationError,
    RateLimitError,
    TransportError,
)

try:
    agent = app.create_agent(
        orch_id="service",
        task_id="task",
        requested_scope=["read:data:resource"],
    )
except AuthenticationError as e:
    # 401 — app credentials are wrong
    # Check client_id and client_secret
    print(f"Auth failed: {e.problem.detail}")

except AuthorizationError as e:
    # 403 — scope outside app ceiling
    # Requested scope exceeds what the operator allowed
    print(f"Scope rejected: {e.problem.detail}")
    print(f"Error code: {e.problem.error_code}")

except RateLimitError as e:
    # 429 — too many requests
    print(f"Rate limited: {e.problem.detail}")

except TransportError as e:
    # Network failure — broker unreachable
    print(f"Cannot reach broker: {e}")
```

### Catching Everything

```python
from agentwrit.errors import AgentWritError

try:
    agent = app.create_agent(...)
except AgentWritError as e:
    # Catches any SDK error
    print(f"AgentWrit error: {e}")
```

### Released Agent Errors

Calling `renew()` or `delegate()` on a released agent raises `AgentWritError` immediately — the SDK catches this locally without hitting the broker:

```python
agent.release()

try:
    agent.renew()
except AgentWritError as e:
    print(e)  # "agent has been released and cannot be renewed"

try:
    agent.delegate(delegate_to="...", scope=["..."])
except AgentWritError as e:
    print(e)  # "agent has been released and cannot delegate"
```

### Invalid Tokens

If someone sends a fake, malformed, or expired token to your app, `validate()` handles it gracefully — it returns a result instead of raising:

```python
from agentwrit import validate

result = validate(app.broker_url, "completely-fake-not-a-jwt")
print(result.valid)  # False
print(result.error)  # "token is invalid or expired"
```

No exception is thrown. The broker returns `valid=False` with a generic error message for all invalid tokens (expired, revoked, malformed, or unknown).

---

## Health Check

Before doing any work, verify the broker is operational:

```python
health = app.health()
print(health.status)              # "ok"
print(health.version)             # "2.0.0"
print(health.uptime)              # seconds since broker started
print(health.db_connected)        # True if audit database is reachable
print(health.audit_events_count)  # total audit events recorded
```

`health()` calls `GET /v1/health` — a public endpoint that doesn't require authentication.

---

## Token Validation

`validate()` is available two ways:

### Module-Level Function

Any service can validate a token without having an `AgentWritApp`:

```python
from agentwrit import validate

result = validate("http://broker:8080", token)
```

This is how downstream services (the ones receiving agent tokens) verify them. They just need the broker URL.

### App Shortcut

If you already have an `AgentWritApp`, use the shortcut:

```python
result = app.validate(token)
```

Same behavior, but uses the app's broker URL and timeout.

### ValidateResult Fields

```python
result = validate(app.broker_url, agent.access_token)

if result.valid:
    print(result.claims.iss)       # broker-configured issuer (e.g., "agentwrit")
    print(result.claims.sub)       # SPIFFE ID
    print(result.claims.scope)     # granted scope list
    print(result.claims.orch_id)   # orchestrator ID
    print(result.claims.task_id)   # task ID
    print(result.claims.jti)       # unique token ID
    print(result.claims.exp)       # expiration (Unix timestamp)
    print(result.claims.iat)       # issued at (Unix timestamp)
else:
    print(result.error)            # "token is invalid or expired"
```

---

## Thread Safety

`AgentWritApp` is **not thread-safe for mutations**. The app performs lazy one-time authentication on first use, and `app.close()` mutates internal state. Do not share the same `AgentWritApp` instance across threads or `asyncio` event loops without synchronization.

The underlying `httpx.Client` **is thread-safe for concurrent requests** once the app is authenticated. This means multiple threads can safely call `app.create_agent()` or `agent.validate()` on the *same* authenticated instance, provided no thread calls `close()` while others are using it.

### Recommended Patterns

- **One app per thread** (safest):
  ```python
  import threading
  from agentwrit import AgentWritApp

  def worker():
      app = AgentWritApp(...)
      agent = app.create_agent(...)
      # ... use agent ...
      app.close()

  threads = [threading.Thread(target=worker) for _ in range(4)]
  for t in threads:
      t.start()
  ```

- **Shared app with explicit lifecycle**:
  Create one `AgentWritApp`, use it from many threads, and call `close()` only after all threads have finished.

- **Always call `app.close()`** when you're done to avoid connection leaks.

---

## Async / Await Support

The AgentWrit SDK is **synchronous only** in v0.3.0 (it uses `httpx`'s sync client). There is no native `async`/`await` support planned for this release.

If you are building on an async framework such as FastAPI, Starlette, or Sanic, wrap SDK calls with `asyncio.to_thread()` so they do not block the event loop:

```python
import asyncio
from agentwrit import AgentWritApp

app = AgentWritApp(...)

async def handle_request():
    agent = await asyncio.to_thread(
        app.create_agent,
        orch_id="api-gateway",
        task_id="request-123",
        requested_scope=["read:data:customer-123"],
        ttl=300,
    )
    # ... use agent ...
    await asyncio.to_thread(agent.release)
```

---

## Next Steps

| Guide | What You'll Learn |
|-------|-------------------|
| [Getting Started](getting-started.md) | Install and create your first agent |
| [Concepts](concepts.md) | Trust model, roles, scopes, and standards |
| [API Reference](api-reference.md) | Every class, method, parameter, and exception |
| [Testing Guide](testing-guide.md) | Unit tests, integration tests, running the test suite |
| [MedAssist Demo](../demo/) | See every capability in a working healthcare app |
