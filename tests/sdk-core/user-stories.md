# SDK Core: Acceptance Test Stories

Extracted from the approved spec at `.plans/phase-1/SDK-Core-Spec.md`.
Broker API contract verified against `/Users/divineartis/proj/authAgent2/docs/api.md` (develop branch).

Each story follows the TEST-TEMPLATE.md banner format: Who / What / Why / How to run / Expected.

---

## Developer Stories

---

### SDK-S1: Developer Initializes the Client

Who: The developer.

What: The developer creates an `AgentAuthApp` with their broker URL, client_id,
and client_secret. The SDK authenticates the app with the broker behind the scenes
by calling `POST /v1/app/auth`. The developer doesn't need to know about app JWTs,
token types, or operational scopes -- they just pass three strings and get a working
client back.

Why: This is the entry point for every SDK interaction. If initialization fails or
requires extra steps, the entire "3 lines to a token" value proposition breaks down.
The developer would have to manually call `/v1/app/auth` and manage app JWT renewal
themselves.

Setup: Broker running in Docker (develop branch of `github.com/devonartis/agentAuth`).
Test app registered with `read:data:*,write:data:*` scope ceiling via `aactl app register`.
Environment variables set: `AGENTAUTH_BROKER_URL`, `AGENTAUTH_CLIENT_ID`, `AGENTAUTH_CLIENT_SECRET`.

Code:
```python
from agentauth import AgentAuthApp

client = AgentAuthApp(
    broker_url=os.environ["AGENTAUTH_BROKER_URL"],
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)
```

Expected: Client object is created without raising any exception. The SDK has
internally obtained an app JWT from `POST /v1/app/auth` and cached it for
subsequent calls.

---

### SDK-S2: Developer Gets a Token in Three Lines

Who: The developer.

What: The developer calls `client.get_token("my-agent", ["read:data:*"])` and gets
back a valid JWT. Behind the scenes, the SDK executes the full 8-step flow: (1) use
cached app JWT, (2) create a launch token via `POST /v1/app/launch-tokens`, (3)
generate an Ed25519 keypair in memory, (4) request a nonce from `GET /v1/challenge`,
(5) sign the nonce with the private key, (6) register the agent via `POST /v1/register`
with the launch token, nonce, public key, signature, orch_id, task_id, and requested
scope, (7) receive the agent JWT, (8) cache it.

Why: This is the entire value proposition of the SDK. Without it, the developer writes
40-80 lines of code involving `requests`, `cryptography.hazmat`, base64 encoding, hex
decoding, and HTTP error handling. The nonce has a 30-second TTL that's easy to miss.
The Ed25519 key encoding (raw 32-byte vs DER) is the #1 mistake per the broker's
troubleshooting docs.

Setup: Same as SDK-S1. Client already initialized.

Code:
```python
token = client.get_token("my-agent", ["read:data:*"])
```

Expected: `token` is a non-empty string. It has three dot-separated parts (JWT format).
Validating it via `POST /v1/token/validate` returns `valid: true` with claims containing
`scope: ["read:data:*"]` and a SPIFFE-format `sub` like
`spiffe://agentauth.local/agent/{orch}/{task}/{instance}`.

---

### SDK-S3: Token Caching and Automatic Renewal

Who: The developer.

What: The developer calls `get_token` twice with the same agent name and scope. The
second call returns the cached token instantly without hitting the broker again. When
the token approaches expiry (80% of TTL), the SDK automatically renews it by calling
`POST /v1/token/renew` with the existing agent JWT as Bearer auth, and the developer's
next `get_token` call gets the fresh token.

Why: Without caching, every `get_token` call triggers a full 8-step flow -- that's 3
HTTP calls and a key generation. For an agent that checks its token in a loop, this
would hammer the broker and waste time. Without renewal, the developer must track
expiry timestamps and re-register manually.

Setup: Same as SDK-S1. Client initialized. One initial `get_token` call completed.

Code:
```python
token1 = client.get_token("my-agent", ["read:data:*"])
token2 = client.get_token("my-agent", ["read:data:*"])
# token2 should be the same object (cached), no new broker calls
```

Expected: `token1 == token2` (same cached token). The SDK did not make additional
HTTP calls for the second request. When renewal fires (at 80% TTL), the next call
returns a new valid JWT with a later expiry.

---

### SDK-S4: Retry with Exponential Backoff

Who: The developer.

What: When a broker request fails due to a transient error (network timeout, 5xx
response), the SDK retries automatically with exponential backoff: 1s, 2s, 4s
(default 3 retries). On 429 (rate limited), the SDK respects the `Retry-After`
header from the broker. The SDK does NOT retry 4xx errors other than 429, because
those indicate client errors (bad credentials, scope violations) that won't succeed
on retry.

Why: The broker runs in Docker or on a remote server. Network blips, container
restarts, and load spikes happen. Without retry logic, a single transient failure
crashes the developer's application. But retrying client errors (401, 403) would
be wrong -- those need the developer to fix their input.

Setup: Same as SDK-S1. For the 429 test, trigger rate limiting by sending rapid
requests. For the 5xx test, this may require broker manipulation or mocking at the
HTTP layer.

Code:
```python
# 429 test: rapid-fire to trigger rate limit
# The SDK should back off and eventually succeed
token = client.get_token("my-agent", ["read:data:*"])

# Configurable retry:
client = AgentAuthApp(broker_url, client_id, client_secret, max_retries=5)
```

Expected: On transient failures, the SDK retries up to `max_retries` times with
exponential backoff. On 429, the SDK waits for `Retry-After` seconds before retrying.
On permanent 4xx errors (401, 403), the SDK raises immediately without
retry. If all retries are exhausted, `BrokerUnavailableError` is raised.

---

### SDK-S5: Clear Error Messages for Scope Violations

Who: The developer.

What: The developer requests a scope that exceeds their app's ceiling. The broker
returns a 403 with `error_code: "scope_violation"` in RFC 7807 format. The SDK
parses this and raises `ScopeCeilingError` with a message that tells the developer
exactly what went wrong -- including the scope they asked for and what their ceiling
is.

Why: Scope errors are the most common developer mistake after key encoding issues.
The broker's raw error response is a JSON blob with `type`, `title`, `status`,
`detail`, `error_code`. A developer debugging their first integration needs a
Python exception that says "You asked for `write:admin:*` but your app's ceiling
is `['read:data:*', 'write:data:*']`" -- not a generic 403 message.

Setup: Same as SDK-S1. Test app registered with `read:data:*,write:data:*` ceiling.

Code:
```python
from agentauth.errors import ScopeCeilingError

try:
    token = client.get_token("my-agent", ["admin:everything:*"])
except ScopeCeilingError as e:
    print(e)  # Should mention the requested scope and the ceiling
```

Expected: `ScopeCeilingError` is raised. The exception message includes the
requested scope and is actionable (the developer knows what to fix). The exception
has attributes for programmatic access (e.g., `e.requested_scope`, `e.detail`).
No 403 is raised as a generic error.

---

### SDK-S7: Delegation

Who: The developer.

What: The developer has an agent token and wants to grant a subset of its permissions
to another registered agent. They call `client.delegate(token, to_agent_id, scope, ttl)`.
The SDK calls `POST /v1/delegate` with the agent's JWT as Bearer auth, the delegate's
SPIFFE ID, the attenuated scope, and the TTL. The broker enforces that the delegated
scope is a subset of the delegator's scope and returns a new JWT for the delegate.

Why: Delegation is how multi-agent workflows share permissions without over-provisioning.
Agent A (orchestrator) can give Agent B (worker) just `read:data:results` even though
Agent A holds `read:data:*`. The broker enforces scope attenuation -- the SDK just needs
to pass the right parameters and return the result.

Setup: Two agents registered. Agent A has `read:data:*` scope. Agent B is registered
but needs a delegated token.

Code:
```python
delegated_token = client.delegate(
    token=agent_a_token,
    to_agent_id="spiffe://agentauth.local/agent/pipeline/task-001/writer",
    scope=["read:data:results"],
    ttl=120,
)
```

Expected: `delegated_token` is a valid JWT string. Validating it via
`POST /v1/token/validate` shows `scope: ["read:data:results"]` and the delegate's
SPIFFE ID as `sub`. The `delegation_chain` is populated.

---

### SDK-S8: Self-Revocation

Who: The developer.

What: The developer's agent is done with its task and wants to clean up. They call
`client.revoke_token(token)`. The SDK calls `POST /v1/token/release` with the agent's
JWT as Bearer auth. The broker revokes the token's JTI and returns 204. After
revocation, the token is no longer valid -- `POST /v1/token/validate` returns
`valid: false`.

Why: Ephemeral credentials should be explicitly released when no longer needed. This
is a security best practice -- it reduces the window of exposure. The broker logs a
`token_released` audit event, giving operators visibility into agent lifecycle. An
agent that doesn't revoke its token still has it expire naturally, but explicit
revocation is cleaner.

Setup: Same as SDK-S1. Agent registered with a valid token.

Code:
```python
client.revoke_token(token)
# Token is now invalid
```

Expected: `revoke_token` returns without error. Subsequent `POST /v1/token/validate`
for the same token returns `valid: false`. The broker's audit log contains a
`token_released` event for this agent.

---

## Security Stories

---

### SDK-S9: Ed25519 Keys Are Ephemeral

Who: The security reviewer.

What: The security reviewer wants to verify that the SDK never persists Ed25519
private keys to disk. During `get_token`, the SDK generates an Ed25519 keypair
using `cryptography.hazmat.primitives.asymmetric.ed25519`, uses the private key
to sign the nonce, sends the public key to the broker, and then the private key
exists only in memory. There is no `key.pem`, no keystore, no environment variable
with the private key.

Why: Ephemeral keys are a core security invariant of the AgentAuth design (from the
Ephemeral Agent Credentialing v1.2 pattern). If private keys are persisted, they can
be stolen and used to impersonate agents. The entire point of challenge-response is
that the private key never leaves the process -- the broker only ever sees the public
key.

Setup: Read the SDK source code. Run `get_token` and inspect the process.

Verification:
```python
# 1. Grep the codebase for file write operations involving keys
# 2. Verify generate_keypair() returns in-memory objects only
# 3. Verify no serialization of private keys anywhere in the codebase
# 4. Run get_token, then search /tmp, working dir, and home dir for .pem/.key files
```

Expected: No private key material is ever written to disk. `generate_keypair()`
returns `(Ed25519PrivateKey, base64_public_key_string)` -- the private key is a
Python object in memory only. No file I/O involving private keys exists anywhere
in the SDK source.

---

### SDK-S10: Client Secret Never Logged or Exposed

Who: The security reviewer.

What: The security reviewer wants to verify that `client_secret` never appears in
logs, error messages, exception strings, `__repr__` output, or debug traces. If the
developer passes a wrong secret, the error message should say "Authentication failed:
invalid credentials" -- NOT "Authentication failed with secret 'secret_xyz...'". The
SDK must also not include the secret in any HTTP request logging if debug logging is
enabled.

Why: Credential leakage through logs is a top security risk. Developers copy-paste
error messages into Slack, GitHub issues, and Stack Overflow. If the secret is in
the error, it's leaked. The broker returns 401 on bad credentials -- the SDK must
translate this to `AuthenticationError` without including the secret.

Setup: Initialize a client with a wrong secret. Enable debug logging. Inspect all output.

Verification:
```python
# 1. Create client with bad secret, catch AuthenticationError, verify secret not in str(e)
# 2. Grep the SDK source for any logging of client_secret
# 3. Check __repr__ and __str__ of AgentAuthApp -- secret must not appear
# 4. If SDK has debug logging, verify the secret is redacted
```

Expected: `client_secret` never appears in any string output from the SDK. The
`AgentAuthApp.__repr__` shows `broker_url` and `client_id` but masks or omits
the secret. `AuthenticationError` messages reference the client_id but never the
secret.

---

### SDK-S11: TLS Certificate Validation Enabled by Default

Who: The security reviewer.

What: The security reviewer wants to verify that the SDK validates the broker's TLS
certificate by default when connecting over HTTPS. The SDK uses `requests` which
validates TLS by default, but the reviewer wants to confirm that no code path sets
`verify=False`. If a developer needs to disable verification for local development
(e.g., self-signed certs), they must explicitly opt in.

Why: Man-in-the-middle attacks on the broker connection could intercept app JWTs,
agent tokens, and client secrets. TLS validation is the first line of defense. Silently
disabling it (as some SDKs do for "convenience") would undermine the entire security
model.

Setup: Read the SDK source code. Check all `requests.Session` and `requests.post/get`
calls.

Verification:
```python
# 1. Grep the SDK source for verify=False
# 2. Verify requests.Session does not have verify=False set
# 3. If there's an option to disable TLS verification, confirm it requires explicit opt-in
```

Expected: No `verify=False` in the SDK source. The `requests.Session` uses default
TLS verification. If a `verify` parameter exists on `AgentAuthApp.__init__`, it
defaults to `True`.

---

## Operator Stories

---

### SDK-S12: SDK Uses Standard Broker API

Who: The operator.

What: The operator wants to verify that the SDK uses the exact same broker API
endpoints as any other HTTP client. The SDK does not call hidden endpoints, use
special headers, or bypass any broker middleware. The operator can monitor, rate-limit,
and audit SDK traffic using the same tools they use for all broker clients.

Why: Operators need a single monitoring and security model for all broker traffic.
If the SDK used backdoor endpoints or special authentication, operators would need
separate monitoring, separate rate limiting, and separate audit rules. The broker's
design principle is that all clients are equal.

Setup: Run the SDK against the broker with audit logging enabled. Query
`GET /v1/audit/events` to see what the broker recorded.

Verification:
```python
# 1. Run client.get_token() once
# 2. Query GET /v1/audit/events with admin token
# 3. Verify events include: app_authenticated, agent_registered, token_issued
# 4. Verify the endpoints called match the documented API (no hidden paths)
```

Expected: The broker's audit log shows standard events: `app_authenticated` (from
`POST /v1/app/auth`), `agent_registered` (from `POST /v1/register`). No unknown
event types or endpoints appear. The SDK's User-Agent or request patterns are
indistinguishable from a manual curl caller (except possibly a User-Agent header).

---

### SDK-S13: Rate Limiting Respected

Who: The operator.

What: The operator wants to verify that when the broker returns 429 (rate limited)
with a `Retry-After` header, the SDK backs off correctly instead of hammering the
broker. The SDK should wait the specified time before retrying. This applies
especially to `POST /v1/app/auth` (rate-limited: 10 req/min per client_id, burst 3)
and all other endpoints.

Why: One developer's runaway script shouldn't impact other clients. If the SDK
ignores rate limits and retries immediately, it makes the congestion worse and may
get the app's client_id blocked. Respecting `Retry-After` is both good citizenship
and required by the broker's rate limiting design.

Setup: Trigger rate limiting by sending rapid auth requests. Observe SDK behavior.

Verification:
```python
# 1. Send rapid-fire POST /v1/app/auth requests to trigger 429
# 2. Verify the SDK waits for Retry-After duration before retrying
# 3. Verify the SDK raises RateLimitError with retry_after attribute if retries exhausted
# 4. Verify the SDK does NOT retry immediately on 429
```

Expected: On 429, the SDK pauses for the `Retry-After` duration, then retries. If
the rate limit persists after all retries, `RateLimitError` is raised with a
`retry_after` attribute. The SDK never sends more requests than the rate limit allows
during backoff.

---

## Phase 2: Cache Correctness Fixes (v0.3.0)

Stories for the cache correctness fixes in `.plans/specs/2026-04-05-v0.3.0-phase2-cache-correctness-spec.md`.
Findings addressed: G13 (task_id/orch_id keying), G14 (eviction on release), G15 (per-key locking), G16 (TokenExpiredError removal).

---

### SDK-P2-S1: Task-Scoped Cache Entries Are Isolated (G13)

Who: The developer calling `get_token()` with different `task_id` values.

What: The developer calls `get_token("analyst", ["read:data:*"], task_id="q4-2026")`, receives a token,
then calls `get_token("analyst", ["read:data:*"], task_id="q1-2026")`. Before v0.3.0, the second call
returns the SAME token from cache as the first (aliased by `(agent_name, frozenset(scope))` alone).
After this fix, the cache key includes `task_id` and `orch_id`, so the second call performs a fresh
registration and returns a DIFFERENT token with a different SPIFFE ID.

Why: The broker embeds `task_id` and `orch_id` in JWT claims AND in the SPIFFE subject
(`spiffe://.../agent/{orch}/{task}/{instance}`). When the cache aliases these calls, a token minted
for task "q4-2026" gets served to a caller working on task "q1-2026" — breaking task isolation and
corrupting the audit trail. Two distinct tasks appear to share one agent identity.

Setup: Broker running. Test app with `read:data:*` ceiling. `AgentAuthApp` initialized.

Code:
```python
result_q4 = app.get_token("analyst", ["read:data:*"], task_id="q4-2026")
result_q1 = app.get_token("analyst", ["read:data:*"], task_id="q1-2026")
assert result_q4.token != result_q1.token
assert result_q4.agent_id != result_q1.agent_id  # different SPIFFE IDs
```

Expected: `result_q4` and `result_q1` are distinct `TokenResult` objects with distinct JWTs and
distinct SPIFFE IDs. Mock session verifies `/v1/register` was called twice (not once).

---

### SDK-P2-S2: Released Tokens Are Evicted from Cache (G14)

Who: The developer cleaning up after a task.

What: The developer obtains a token via `get_token`, uses it, then calls `release_token()` to
explicitly release it (Phase 5 renames `revoke_token` → `release_token`; Phase 2 keeps the old name
but adds cache eviction to it). A subsequent `get_token()` call with the same arguments should
perform a fresh broker registration, NOT return the released (dead) token from cache.

Why: Before this fix, after `revoke_token()` succeeds the cache entry remains. The next `get_token`
call returns the revoked token with zero broker calls. The caller then uses that dead token on a
downstream API and gets a confusing 401 with no obvious cause. Cache must evict on release.

Setup: Broker running. App initialized. A token issued and cached.

Code:
```python
result1 = app.get_token("worker", ["read:data:*"], task_id="t1")
app.revoke_token(result1.token)  # cache entry evicted
result2 = app.get_token("worker", ["read:data:*"], task_id="t1")
assert result2.token != result1.token  # fresh registration
```

Expected: `result2.token` differs from `result1.token`. Mock session verifies
`/v1/register` called twice. `cache.get("worker", ["read:data:*"], task_id="t1")` after the revoke
returns None.

---

### SDK-P2-S3: Concurrent `get_token()` Produces Exactly One Registration (G15)

Who: An internal concurrent caller (e.g., a multi-threaded pipeline).

What: Ten threads simultaneously call `app.get_token("shared", scope, task_id="T")` on a cold cache.
Before this fix, the cache-miss path was not serialized per key — all 10 threads completed the full
launch-token → challenge → register flow, each receiving a different SPIFFE ID from the broker.
After this fix, a per-key lock serializes the miss path: exactly 1 thread registers, the other 9
acquire the lock in turn, re-check the cache (populated now), and return the cached result.

Why: Without serialization, duplicate SPIFFE identities are minted under load. The last writer's
cache entry wins; the other 9 tokens are orphaned — valid at the broker, unreferenced in SDK,
cannot be revoked. Over time this leaks identities and confuses the broker's audit trail with
phantom registrations.

Setup: App initialized. Mocked broker responses (each `/v1/register` returns a distinct SPIFFE ID).

Code:
```python
from concurrent.futures import ThreadPoolExecutor
results = []
with ThreadPoolExecutor(max_workers=10) as pool:
    futures = [pool.submit(lambda: app.get_token("shared", ["read:*"], task_id="T"))
               for _ in range(10)]
    results = [f.result() for f in futures]

# All 10 results should be identical
assert all(r.token == results[0].token for r in results)
# Only one registration should have happened
assert mock_session.register_call_count == 1
```

Expected: All 10 threads receive the same `TokenResult`. Mock broker sees exactly 1 call to
`/v1/register`. No orphaned tokens.

---

### SDK-P2-S4: `TokenExpiredError` Is Removed from Public API (G16)

Who: The developer catching SDK exceptions.

What: Before this fix, `TokenExpiredError` was exported from `agentauth` and documented in the
README — but the SDK never raised it anywhere in the source. A developer writing
`except TokenExpiredError:` handlers would never see those handlers fire. After this fix, the
class is deleted entirely. The caller uses `TokenResult.expires_at` (from Phase 3) to check
expiry directly.

Why: Exporting an exception the SDK never raises is a silent API lie — it trains developers
to write handlers that do nothing and creates the false impression that the SDK proactively
signals expiry. v0.3.0 makes expiry checkable via `TokenResult.expires_at`, so the exception
is redundant.

Setup: Verify deletion is complete.

Code:
```bash
grep -rn "TokenExpiredError" src/ tests/ docs/ README.md
# Must return zero matches

python -c "from agentauth import TokenExpiredError"
# Must raise ImportError
```

Expected: `grep` returns nothing. `from agentauth import TokenExpiredError` raises `ImportError`.
The class does not appear in `agentauth.__all__` or the package docstring.

---

## Story-to-Test Mapping

### Source modules (small files, one concern each)

| Module | Source File | What It Does |
|--------|-----------|-------------|
| errors | `src/agentauth/errors.py` | Exception hierarchy + RFC 7807 parsing |
| crypto | `src/agentauth/crypto.py` | Ed25519 keygen + nonce signing |
| retry | `src/agentauth/retry.py` | HTTP retry with backoff + 429 handling |
| client (auth) | `src/agentauth/app.py` | `__init__`, `_authenticate_app`, `_ensure_app_token` |
| client (get_token) | `src/agentauth/app.py` | `get_token` with challenge-response flow |
| client (ops) | `src/agentauth/app.py` | `delegate`, `revoke_token`, `validate_token` |
| token cache | `src/agentauth/token.py` | In-memory token cache with renewal tracking |

### Unit tests (one file per concern)

| Story | Unit Test File | Key Assertion |
|-------|---------------|---------------|
| SDK-S5 | `test_errors.py` | ScopeCeilingError with actionable message |
| SDK-S9 | `test_crypto.py` | No file I/O for private keys |
| SDK-S10 | `test_errors.py` | Secret not in any string output |
| SDK-S4, S13 | `test_retry.py` | Retries on 5xx/429, no retry on 4xx, respects Retry-After |
| SDK-S1 | `test_client_auth.py` | Client init calls /v1/app/auth, bad creds raise AuthenticationError |
| SDK-S2 | `test_client_get_token.py` | get_token calls 3 endpoints, errors raise correct exceptions |
| SDK-S7, S8 | `test_client_ops.py` | delegate/revoke/validate call correct endpoints |
| SDK-S3 | `test_token_cache.py` | Cache hit, scope-order invariant, renewal threshold, expiry eviction |
| SDK-S11 | code review | No verify=False in source |

### Integration tests (broker required)

| Story | Integration Test File | Key Assertion |
|-------|---------------------|---------------|
| SDK-S1 | `test_app_auth.py` | Client initializes against real broker |
| SDK-S2 | `test_get_token.py` | JWT returned, validates with broker |
| SDK-S3 | `test_get_token.py` | Same token on second call |
| SDK-S7 | `test_delegation.py` | Delegated JWT has attenuated scope |
| SDK-S8 | `test_revocation.py` | Token invalid after revoke |
| SDK-S12 | `test_app_auth.py` | Audit events match standard flow |

---

## Evidence Directory

After implementation and testing, evidence goes in:
```
tests/sdk-core/evidence/
  README.md              -- summary table with verdicts
  story-1-init.md        -- SDK-S1 evidence
  story-2-get-token.md   -- SDK-S2 evidence
  story-3-caching.md     -- SDK-S3 evidence
  ...etc
```

Each evidence file uses the banner format from TEST-TEMPLATE.md.
