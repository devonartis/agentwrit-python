# AgentAuth Python SDK — What You Get and How to Use Every Piece

> You have three things: a **broker URL**, a **client_id**, a **client_secret**. Someone gave them to you.
> This document is every class, method, parameter, and exception the SDK gives you in return. Nothing else.

---

## Install

```bash
uv add git+https://github.com/devonartis/agentauth-python-sdk
```

```python
from agentauth import (
    AgentAuthApp,
    AgentAuthError,
    AuthenticationError,
    ScopeCeilingError,
    RateLimitError,
    BrokerUnavailableError,
)
```

---

## The one class: `AgentAuthApp`

### Constructor

```python
AgentAuthApp(
    broker_url: str,
    client_id: str,
    client_secret: str,
    *,
    max_retries: int = 3,
    verify: bool = True,
)
```

| Parameter       | Type    | Default | What it's for                                                                 |
|-----------------|---------|---------|-------------------------------------------------------------------------------|
| `broker_url`    | `str`   | —       | Base URL you were given. Trailing slash is stripped.                          |
| `client_id`     | `str`   | —       | You were given this.                                                          |
| `client_secret` | `str`   | —       | You were given this. Never logged, printed, or included in any SDK output.    |
| `max_retries`   | `int`   | `3`     | Retries for transient failures (429 rate limit, 5xx server error, connection errors). Exponential backoff. |
| `verify`        | `bool`  | `True`  | TLS certificate verification. Keep `True` in production.                       |

**What construction does:**
- Authenticates immediately (single HTTP call). Raises `AuthenticationError` right here on bad credentials — you find out at startup, not mid-request.
- Sets up an internal HTTP session (connection pooling, TLS verification, JSON content type).
- After success, the object is ready — the SDK handles internal credential renewal transparently for the lifetime of the object.

**Thread safety:** the object is safe to share across threads. All four public methods can be called concurrently without external locks.

**Example:**

```python
import os
from agentauth import AgentAuthApp

app = AgentAuthApp(
    broker_url=os.environ["AGENTAUTH_BROKER_URL"],
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)
```

---

### `app.get_token()`

```python
def get_token(
    self,
    agent_name: str,
    scope: list[str],
    *,
    task_id: str | None = None,
    orch_id: str | None = None,
) -> str
```

Obtain a scoped JWT. You hand this string to any HTTP client as a standard `Authorization: Bearer <token>` credential.

| Parameter     | Type                 | Default   | What it's for                                                         |
|---------------|----------------------|-----------|------------------------------------------------------------------------|
| `agent_name`  | `str`                | —         | Logical name. Part of the cache key.                                   |
| `scope`       | `list[str]`          | —         | Scope strings in `action:resource:identifier` format (e.g., `"read:data:customers"`). Must be within the allowed scopes your credentials give you. |
| `task_id`     | `str \| None`        | `None`    | Task identifier. Embedded in the JWT claims and in the SPIFFE subject. Defaults to `"default"` server-side. |
| `orch_id`     | `str \| None`        | `None`    | Orchestrator identifier. Embedded in the JWT claims and in the SPIFFE subject. Defaults to `"sdk"` server-side. |

**Returns:** `str` — a JWT string. Three base64-encoded parts separated by dots. Treat as opaque.

**Raises:**

| Exception                  | When                                                                   |
|----------------------------|------------------------------------------------------------------------|
| `ScopeCeilingError`        | A scope in `scope` is outside what your credentials are allowed to request |
| `AuthenticationError`      | Internal re-authentication failed (credentials no longer valid)        |
| `RateLimitError`           | Rate-limited; all retries exhausted                                    |
| `BrokerUnavailableError`   | All retries exhausted (5xx or connection errors)                        |
| `AgentAuthError`           | Any other broker error                                                 |

**Caching:** the cache key is the 4-tuple `(agent_name, frozenset(scope), task_id, orch_id)`. Second call with the same key returns the cached token — zero network calls — until the token hits 80% of its TTL, at which point the next call fetches a fresh one proactively.

**Examples:**

```python
# Minimal
token = app.get_token("my-agent", ["read:data:*"])

# With task context (recommended in production — embeds in audit trail)
token = app.get_token(
    agent_name="analyzer",
    scope=["read:data:customers"],
    task_id="q4-analysis",
    orch_id="data-pipeline",
)

# Scope order doesn't matter — these hit the same cache entry:
app.get_token("agent", ["read:data:*", "write:logs:*"])
app.get_token("agent", ["write:logs:*", "read:data:*"])  # cache hit

# Different scope sets = different cache entries:
app.get_token("agent", ["read:data:*"])                  # entry A
app.get_token("agent", ["read:data:*", "write:logs:*"])  # entry B
```

---

### `app.delegate()`

```python
def delegate(
    self,
    token: str,
    to_agent_id: str,
    scope: list[str],
    ttl: int = 60,
) -> str
```

Create a narrower-scoped token for another agent, derived from an existing token. Produces a new JWT that carries a cryptographically signed delegation chain proving who authorized whom.

| Parameter      | Type         | Default | What it's for                                                                  |
|----------------|--------------|---------|---------------------------------------------------------------------------------|
| `token`        | `str`        | —       | The delegating agent's JWT (the one you got from `get_token()` earlier). Used as Bearer auth to the delegate endpoint. |
| `to_agent_id`  | `str`        | —       | The SPIFFE ID of the agent receiving the delegation. Get this from `validate_token()` on that agent's own token (the `sub` claim). |
| `scope`        | `list[str]`  | —       | Scopes to grant. Must be a subset of `token`'s scope — can only narrow, never widen. |
| `ttl`          | `int`        | `60`    | Lifetime of the delegated token in seconds.                                      |

**Returns:** `str` — the delegated JWT.

**Raises:**

| Exception               | When                                               |
|-------------------------|----------------------------------------------------|
| `ScopeCeilingError`     | `scope` is not a subset of the delegator's scope    |
| `AgentAuthError`        | Other broker errors (delegate not registered, chain depth > 5, etc.) |

**Rules the server enforces:**
- Scope can only narrow. `read:data:*` can delegate `read:data:customers`, not `write:data:*`.
- Maximum delegation depth: 5 hops.
- `to_agent_id` must be a SPIFFE ID that corresponds to an already-registered agent.

**Example:**

```python
# Orchestrator has broad scope
orch_token = app.get_token("orchestrator", ["read:data:*"], task_id="job-A")

# Worker has its own token (registers on its own cache key)
worker_token = app.get_token("worker", ["read:data:customers"], task_id="job-A")

# Get worker's SPIFFE ID from its claims
worker_id = app.validate_token(worker_token)["claims"]["sub"]

# Orchestrator delegates a narrower slice of its scope to worker
delegated = app.delegate(
    token=orch_token,
    to_agent_id=worker_id,
    scope=["read:data:customers"],   # narrower than orch's read:data:*
    ttl=120,
)

# `delegated` is a JWT proving orchestrator authorized worker for this specific task
```

---

### `app.revoke_token()`

```python
def revoke_token(self, token: str) -> None
```

Self-revoke a token. Use this when the work is done — closes the exposure window and writes a `token_released` event to the audit trail.

| Parameter | Type   | What it's for                     |
|-----------|--------|-----------------------------------|
| `token`   | `str`  | The JWT to revoke. Used as Bearer auth to the release endpoint. |

**Returns:** `None`.

**Raises:** `AgentAuthError` (and subclasses) if the broker rejects the call.

**Side effect:** evicts the token from the SDK's internal cache, so the next `get_token()` call with the same cache key will register a fresh agent and issue a new JWT.

**Idempotency:** calling `revoke_token()` on an already-revoked token raises (the broker returns 403). Use `try`/`finally` and swallow errors on cleanup if you want pure idempotency.

**Idiomatic use:**

```python
token = app.get_token("worker", ["write:data:reports"], task_id=request_id)
try:
    do_the_work(token)
finally:
    app.revoke_token(token)
```

---

### `app.validate_token()`

```python
def validate_token(self, token: str) -> dict
```

Check a token's validity and inspect its claims. Also useful for extracting the SPIFFE ID from another agent's token (needed for `delegate()`).

| Parameter | Type   | What it's for               |
|-----------|--------|------------------------------|
| `token`   | `str`  | JWT string to validate.      |

**Returns:** `dict` in one of two shapes:

Valid token:
```python
{
    "valid": True,
    "claims": {
        "iss": "agentauth",
        "sub": "spiffe://agentauth.local/agent/<orch>/<task>/<instance>",
        "exp": 1707600000,                  # Unix timestamp
        "iat": 1707599700,
        "jti": "a1b2c3d4...",               # unique token ID
        "scope": ["read:data:*"],
        "task_id": "q4-analysis",
        "orch_id": "data-pipeline",
        # ... other JWT claims
    },
}
```

Invalid token:
```python
{
    "valid": False,
    "error": "token is invalid or expired",  # generic — don't parse text
}
```

**Raises:** `AgentAuthError` only on broker communication failure. **An invalid token is NOT raised as an exception** — it returns `{"valid": False, ...}`. Always check the `valid` field.

**The error message is intentionally generic.** The broker does not distinguish between expired, revoked, malformed, or otherwise invalid tokens in its responses (prevents information leakage).

**Example — extracting claims:**

```python
result = app.validate_token(token)
if result["valid"]:
    claims = result["claims"]
    print(f"Subject: {claims['sub']}")        # SPIFFE ID
    print(f"Scopes:  {claims['scope']}")
    print(f"Expires: {claims['exp']}")
    print(f"Task:    {claims['task_id']}")
else:
    print(f"Invalid: {result['error']}")
```

**Example — getting a SPIFFE ID for delegation:**

```python
worker_token = app.get_token("worker", ["read:data:*"], task_id="job-A")
worker_spiffe_id = app.validate_token(worker_token)["claims"]["sub"]
# now you can pass worker_spiffe_id as to_agent_id in app.delegate(...)
```

---

## Exceptions

All SDK exceptions inherit from `AgentAuthError` so you can catch broadly or narrowly. Every exception carries `status_code` and `error_code` attributes from the underlying HTTP response.

```python
from agentauth import (
    AgentAuthError,
    AuthenticationError,
    ScopeCeilingError,
    RateLimitError,
    BrokerUnavailableError,
)
```

### `AgentAuthError` (base)

Base class. Catch this to handle any SDK error generically.

| Attribute       | Type              | What it carries                                   |
|-----------------|-------------------|----------------------------------------------------|
| `status_code`   | `int \| None`     | HTTP status code from the broker response          |
| `error_code`    | `str \| None`     | Machine-readable error code (e.g., `"scope_violation"`, `"unauthorized"`) |

### `AuthenticationError`

HTTP 401. Raised at construction time on bad credentials, and whenever internal re-authentication fails.

| Attribute       | Type              | What it carries                                   |
|-----------------|-------------------|----------------------------------------------------|
| `client_id`     | `str \| None`     | The `client_id` that was used (for debugging context). `client_secret` is NEVER included. |
| `status_code`   | `int \| None`     | HTTP status code                                   |
| `error_code`    | `str \| None`     | Broker error code                                  |

Common causes: wrong `client_id`/`client_secret`, deactivated credentials.

### `ScopeCeilingError`

HTTP 403 with `error_code` of `"scope_violation"` or `"forbidden"`. Raised by `get_token()` and `delegate()` when you request a scope you're not allowed to hold.

| Attribute          | Type                | What it carries                                    |
|--------------------|---------------------|-----------------------------------------------------|
| `requested_scope`  | `list[str] \| None` | The scopes that were rejected                       |
| `status_code`      | `int \| None`       | HTTP status code                                    |
| `error_code`       | `str \| None`       | Broker error code                                   |

**Fix:** request a narrower scope. If you genuinely need that scope, your credentials need a broader allowance — talk to whoever gave you `client_id`/`client_secret`.

### `RateLimitError`

HTTP 429. Raised only after all retries have been exhausted (the SDK retries automatically with exponential backoff and respects `Retry-After` headers).

| Attribute       | Type              | What it carries                                     |
|-----------------|-------------------|------------------------------------------------------|
| `retry_after`   | `int \| None`     | Seconds to wait, from the `Retry-After` header       |
| `status_code`   | `int \| None`     | Always 429                                           |
| `error_code`    | `str \| None`     | Broker error code                                    |

### `BrokerUnavailableError`

Raised when the broker is unreachable or returns 5xx after all retries. Catch-all for transient infrastructure failures.

| Attribute       | Type              | What it carries                                     |
|-----------------|-------------------|------------------------------------------------------|
| `status_code`   | `int \| None`     | HTTP status code (or `None` for connection errors)   |
| `error_code`    | `str \| None`     | Broker error code                                    |

---

## Automatic Retry Behavior

The SDK handles transient failures for you before raising exceptions.

| Condition                          | What the SDK does                                       | Up to                |
|------------------------------------|---------------------------------------------------------|----------------------|
| HTTP 2xx / 3xx / 4xx (except 429)  | Returns immediately, no retry                           | 1 attempt            |
| HTTP 429 (rate limit)              | Sleep per `Retry-After` header, then retry              | `max_retries` attempts |
| HTTP 5xx (server error)            | Exponential backoff: 1s, 2s, 4s, …                      | `max_retries` attempts |
| Connection error / timeout         | Exponential backoff: 1s, 2s, 4s, …                      | `max_retries` attempts |

After retries are exhausted, you see `RateLimitError` (for 429) or `BrokerUnavailableError` (for 5xx / connection).

**Construction-time authentication is NOT retried.** If credentials are bad, `AuthenticationError` fires immediately. Intentional — retrying bad credentials is never useful.

---

## Caching Behavior

Agent tokens are cached in memory by the 4-tuple key: `(agent_name, frozenset(scope), task_id, orch_id)`.

| Behavior              | Detail                                                       |
|-----------------------|---------------------------------------------------------------|
| Cache hit             | Returns cached JWT, zero network calls                        |
| Scope order           | Order-invariant — `["a", "b"]` and `["b", "a"]` hit same key  |
| Proactive renewal     | At 80% of TTL, next `get_token()` fetches a fresh JWT         |
| Expiry eviction       | Expired entries removed on next access                        |
| Revocation eviction   | `revoke_token()` evicts the cached entry                      |
| Concurrency           | Per-key locking — 10 threads on cold cache produce 1 registration |
| Persistence           | In-memory only — cleared on process restart                    |

---

## Complete Worked Example

```python
import os
import requests
from agentauth import (
    AgentAuthApp,
    AgentAuthError,
    ScopeCeilingError,
)

# Construct once at startup — raises AuthenticationError if creds are wrong
app = AgentAuthApp(
    broker_url=os.environ["AGENTAUTH_BROKER_URL"],
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)

def run_job(job_id: str):
    # Issue a scoped credential for this job
    try:
        read_token = app.get_token(
            agent_name="data-reader",
            scope=["read:data:customers"],
            task_id=job_id,
            orch_id="analytics-pipeline",
        )
    except ScopeCeilingError as e:
        # Your credentials don't allow this scope
        raise RuntimeError(f"scope not allowed: {e}") from e

    try:
        # Use it as a standard Bearer credential
        resp = requests.get(
            "https://api.internal/customers",
            headers={"Authorization": f"Bearer {read_token}"},
            timeout=30,
        )
        resp.raise_for_status()
        customers = resp.json()

        # Do work
        process(customers)

    finally:
        # Always release when done — audit trail + closes exposure window
        try:
            app.revoke_token(read_token)
        except AgentAuthError:
            pass  # best-effort on cleanup

if __name__ == "__main__":
    run_job(job_id="2026-Q4-credit-review")
```

---

## Method Reference (one-screen)

| Method                | Returns  | Raises                                    | Purpose                                |
|-----------------------|----------|-------------------------------------------|----------------------------------------|
| `AgentAuthApp(...)`   | instance | `AuthenticationError`, `AgentAuthError`   | Construct + authenticate                |
| `get_token(...)`      | `str`    | `ScopeCeilingError`, `AgentAuthError`     | Issue a scoped agent JWT                |
| `delegate(...)`       | `str`    | `ScopeCeilingError`, `AgentAuthError`     | Narrow scope, hand off to another agent |
| `revoke_token(...)`   | `None`   | `AgentAuthError`                          | Self-revoke a token                    |
| `validate_token(...)` | `dict`   | `AgentAuthError` (only on broker failure) | Check validity + read claims           |

That's the entire public API.
