# API Reference

Complete reference for the AgentWrit Python SDK public API.

---

## AgentWritApp

```python
from agentwrit import AgentWritApp
```

The application container. Authenticates your app with the broker and creates agents.

### Constructor

```python
AgentWritApp(
    broker_url: str,
    client_id: str,
    client_secret: str,
    *,
    timeout: float = 10.0,
    user_agent: str | None = None,
)
```

Creates an app instance. Authentication is lazy — the SDK does not contact the broker until the first `create_agent()` call.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `broker_url` | `str` | required | Base URL of the AgentWrit broker (e.g., `http://localhost:8080`) |
| `client_id` | `str` | required | Application identifier from broker registration |
| `client_secret` | `str` | required | Application secret. Never logged, printed, or included in any SDK output. |
| `timeout` | `float` | `10.0` | HTTP request timeout in seconds |
| `user_agent` | `str \| None` | `None` | Custom User-Agent header. If `None`, uses the SDK default. |

### create_agent()

```python
app.create_agent(
    orch_id: str,
    task_id: str,
    requested_scope: list[str],
    *,
    private_key: Ed25519PrivateKey | None = None,
    max_ttl: int = 300,
    label: str | None = None,
) -> Agent
```

Creates an ephemeral agent. Handles the full registration flow internally: app auth, launch token, Ed25519 keygen, challenge-response, registration.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `orch_id` | `str` | required | Orchestrator identifier. Appears in the SPIFFE ID and JWT claims. |
| `task_id` | `str` | required | Task identifier. Appears in the SPIFFE ID and JWT claims. |
| `requested_scope` | `list[str]` | required | Scopes to request. Must be within the app's scope ceiling. |
| `private_key` | `Ed25519PrivateKey \| None` | `None` | Supply your own key. If `None`, SDK generates one. |
| `max_ttl` | `int` | `300` | Maximum token TTL in seconds. Broker may issue a shorter TTL. |
| `label` | `str \| None` | `None` | Custom agent name for the launch token. Defaults to `orch_id/task_id`. |

**Returns:** `Agent`

**Raises:**

| Exception | When |
|-----------|------|
| `AuthenticationError` | App credentials are invalid (401) |
| `AuthorizationError` | Scope exceeds app ceiling (403) |
| `RateLimitError` | Too many requests (429) |
| `TransportError` | Broker unreachable |

### health()

```python
app.health() -> HealthStatus
```

Checks broker health. No authentication required.

**Returns:** `HealthStatus`

### validate()

```python
app.validate(token: str) -> ValidateResult
```

Shortcut for `agentwrit.validate(app.broker_url, token)`.

**Returns:** `ValidateResult`

### close()

```python
app.close() -> None
```

Closes the underlying HTTP transport. Call this when you're done with the app to release connections.

---

## Agent

```python
from agentwrit import Agent
```

An ephemeral agent created by `AgentWritApp.create_agent()`. Holds the agent JWT and lifecycle methods.

### Properties

| Property | Type | Description |
|----------|------|-------------|
| `agent_id` | `str` | SPIFFE URI (e.g., `spiffe://agentwrit.local/agent/orch/task/instance`) |
| `access_token` | `str` | JWT string (EdDSA-signed) |
| `expires_in` | `int` | Token TTL in seconds (snapshot from creation or last renewal) |
| `scope` | `list[str]` | Granted scope list |
| `orch_id` | `str` | Orchestrator identifier |
| `task_id` | `str` | Task identifier |
| `bearer_header` | `dict[str, str]` | `{"Authorization": "Bearer <token>"}` for HTTP requests |

### renew()

```python
agent.renew() -> None
```

Renews the agent's token in place. The broker revokes the old token and issues a new one. The `agent_id` does not change.

After calling `renew()`:
- `agent.access_token` is a new JWT
- `agent.expires_in` is reset
- `agent.agent_id` is unchanged
- The old token is revoked at the broker

**Raises:** `AgentWritError` if the agent has been released.

### release()

```python
agent.release() -> None
```

Self-revokes the agent's token. After release, the token is rejected by the broker. Idempotent — second call is a no-op.

**Raises:** Nothing. Second call is safe.

### delegate()

```python
agent.delegate(
    delegate_to: str,
    scope: list[str],
    *,
    ttl: int | None = None,
) -> DelegatedToken
```

Creates a scope-attenuated delegation token for another registered agent.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `delegate_to` | `str` | required | SPIFFE ID of the target agent (must already be registered) |
| `scope` | `list[str]` | required | Scopes to delegate. Must be a subset of this agent's scope. |
| `ttl` | `int \| None` | `None` | Delegation TTL in seconds. Broker defaults to 60 if omitted. |

**Returns:** `DelegatedToken`

**Raises:**

| Exception | When |
|-----------|------|
| `AgentWritError` | Agent has been released |
| `AuthorizationError` | Scope exceeds delegator's scope (403) |

---

## Module-Level Functions

### validate()

```python
from agentwrit import validate

validate(
    broker_url: str,
    token: str,
    *,
    timeout: float = 10.0,
) -> ValidateResult
```

Validates a token with the broker. Any service can call this without having an `AgentWritApp`.

| Parameter | Type | Default | Description |
|-----------|------|---------|-------------|
| `broker_url` | `str` | required | Base URL of the broker |
| `token` | `str` | required | JWT string to validate |
| `timeout` | `float` | `10.0` | HTTP timeout in seconds |

**Returns:** `ValidateResult`

### scope_is_subset()

```python
from agentwrit import scope_is_subset

scope_is_subset(
    requested: list[str],
    allowed: list[str],
) -> bool
```

Client-side scope check. Returns `True` if every scope in `requested` is covered by at least one scope in `allowed`.

Rules:
- Scopes must be 3-segment format: `action:resource:identifier`
- Action and resource must match exactly
- Wildcard `*` only works in the identifier (3rd) position
- Non-3-segment scopes: exact string match only
- Empty `requested` always returns `True`
- Empty `allowed` always returns `False` (unless `requested` is also empty)

---

## Data Classes

All data classes are frozen (immutable) and importable from `agentwrit` or `agentwrit.models`.

### ValidateResult

```python
from agentwrit import ValidateResult
```

| Field | Type | Description |
|-------|------|-------------|
| `valid` | `bool` | Whether the token is valid |
| `claims` | `AgentClaims \| None` | Token claims if valid, `None` if invalid |
| `error` | `str \| None` | Error message if invalid, `None` if valid |

### AgentClaims

```python
from agentwrit import AgentClaims
```

| Field | Type | Description |
|-------|------|-------------|
| `iss` | `str` | Issuer — identifies the broker that issued the token |
| `sub` | `str` | Subject — SPIFFE URI of the agent |
| `aud` | `list[str]` | Audience (may be empty) |
| `exp` | `int` | Expiration (Unix timestamp) |
| `nbf` | `int` | Not before (Unix timestamp) |
| `iat` | `int` | Issued at (Unix timestamp) |
| `jti` | `str` | Unique token ID (32 hex chars) |
| `scope` | `list[str]` | Granted scope |
| `task_id` | `str` | Task identifier |
| `orch_id` | `str` | Orchestrator identifier |
| `sid` | `str \| None` | Session ID (optional) |
| `delegation_chain` | `list[DelegationRecord] \| None` | Delegation chain (optional) |
| `chain_hash` | `str \| None` | SHA-256 hash of delegation chain (optional) |

### DelegatedToken

```python
from agentwrit import DelegatedToken
```

| Field | Type | Description |
|-------|------|-------------|
| `access_token` | `str` | JWT for the delegate agent |
| `expires_in` | `int` | TTL in seconds |
| `delegation_chain` | `list[DelegationRecord]` | Complete chain including new entry |

### DelegationRecord

```python
from agentwrit import DelegationRecord
```

| Field | Type | Description |
|-------|------|-------------|
| `agent` | `str` | SPIFFE ID of the delegating agent |
| `scope` | `list[str]` | Scope held by delegator at time of delegation |
| `delegated_at` | `str` | RFC 3339 timestamp |

### HealthStatus

```python
from agentwrit import HealthStatus
```

| Field | Type | Description |
|-------|------|-------------|
| `status` | `str` | Broker status (always `"ok"` when reachable) |
| `version` | `str` | Broker version (e.g., `"2.0.0"`) |
| `uptime` | `int` | Seconds since broker started |
| `db_connected` | `bool` | Whether audit database is reachable |
| `audit_events_count` | `int` | Total audit events recorded |

### ProblemDetail

```python
from agentwrit import ProblemDetail
```

RFC 7807 structured error from the broker.

| Field | Type | Description |
|-------|------|-------------|
| `type` | `str` | Error type URI (e.g., `urn:agentwrit:error:scope_violation`) |
| `title` | `str` | Human-readable title (e.g., `"Forbidden"`) |
| `detail` | `str` | Human-readable explanation |
| `instance` | `str` | The API endpoint that returned the error |
| `status` | `int \| None` | HTTP status code |
| `error_code` | `str \| None` | Machine-readable error code (e.g., `"scope_violation"`) |
| `request_id` | `str \| None` | Broker-generated trace ID |
| `hint` | `str \| None` | Optional guidance for resolution |

### RegisterResult

```python
from agentwrit import RegisterResult
```

| Field | Type | Description |
|-------|------|-------------|
| `agent_id` | `str` | SPIFFE URI of the registered agent |
| `access_token` | `str` | Agent JWT |
| `expires_in` | `int` | Token TTL in seconds |

---

## Exceptions

All exceptions are importable from `agentwrit` or `agentwrit.errors`.

### Hierarchy

```
AgentWritError
├── ProblemResponseError      (broker returned RFC 7807 error)
│   ├── AuthenticationError   (401 — invalid credentials)
│   ├── AuthorizationError    (403 — scope violation, delegation rejected)
│   └── RateLimitError        (429 — too many requests)
├── TransportError            (network failure — broker unreachable)
└── CryptoError               (Ed25519 key generation or signing failure)
```

### ProblemResponseError

Base class for all broker error responses. Has:

| Attribute | Type | Description |
|-----------|------|-------------|
| `problem` | `ProblemDetail` | Structured error info |
| `status_code` | `int` | HTTP status code |

### AuthenticationError

Raised on HTTP 401. App credentials are invalid.

### AuthorizationError

Raised on HTTP 403. Scope violation — either:
- Requested scope exceeds app ceiling (during `create_agent()`)
- Delegated scope exceeds delegator's scope (during `delegate()`)

### RateLimitError

Raised on HTTP 429. Broker rate limit exceeded.

### TransportError

Network failure — DNS resolution, connection refused, timeout.

### CryptoError

Ed25519 key generation or nonce signing failure. Client-side error.

### AgentWritError

Base exception. Catch this to handle any SDK error. Also raised directly when calling `renew()` or `delegate()` on a released agent.

---

## Broker Endpoint Mapping

| SDK Method | HTTP | Endpoint | Auth |
|-----------|------|----------|------|
| `AgentWritApp()` (lazy) | `POST` | `/v1/app/auth` | `client_id` + `client_secret` in body |
| `create_agent()` | `POST` | `/v1/app/launch-tokens` | `Bearer {app_token}` |
| `create_agent()` | `GET` | `/v1/challenge` | None |
| `create_agent()` | `POST` | `/v1/register` | `launch_token` in body |
| `agent.renew()` | `POST` | `/v1/token/renew` | `Bearer {agent_token}` |
| `agent.release()` | `POST` | `/v1/token/release` | `Bearer {agent_token}` |
| `agent.delegate()` | `POST` | `/v1/delegate` | `Bearer {agent_token}` |
| `validate()` | `POST` | `/v1/token/validate` | None (public) |
| `health()` | `GET` | `/v1/health` | None (public) |
