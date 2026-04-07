# Python SDK — Architecture Decision Records

> **Companion to:** [Python SDK PRD/SPEC](./python-sdk-prd.md)
>
> **Relationship to broker decisions:** The broker's design decisions are documented in [Design Decisions](../design-decisions.md). This document covers decisions specific to the Python SDK's API design, boundaries, and implementation strategy. The SDK decisions are constrained by the broker decisions — they don't override them.
>
> **Format:** Each ADR follows the pattern: Context (the problem), Decision (what we chose), Consequences (what follows from the choice). Decisions are numbered SDK-001 through SDK-011 to distinguish from the broker's Decision 1–11.

---

## SDK-001: Exclude All Operator/Admin APIs

### Context

The broker has three actor roles: Admin (operator), App, and Agent. The admin API surface includes app registration (`POST /v1/admin/apps`), admin-level launch token creation (`POST /v1/admin/launch-tokens`), revocation across four granularity levels (`POST /v1/revoke`), and audit event queries (`GET /v1/audit/events`). All of these require the admin secret.

The initial SDK design included these endpoints. The assumption was that a comprehensive SDK should wrap the entire API.

### Decision

**The Python SDK excludes every admin/operator endpoint.** The SDK's scope begins after the operator hands the developer three things: `client_id`, `client_secret`, and `broker_url`. The developer never holds the admin secret, never registers apps, never performs operator-level revocation, and never queries audit events.

### Consequences

- The SDK is simpler and its threat model is narrower. A compromised SDK installation cannot perform admin operations.
- Operators who want Python automation for admin tasks must use raw HTTP or wait for a future operator-specific package (`agentauth-admin`).
- The SDK's entry point is unambiguous: `AgentAuthApp(broker_url, client_id, client_secret)`. There is no `AdminClient` or `AdminSecret` parameter.
- The 8 endpoints in scope are: `POST /v1/app/auth`, `POST /v1/app/launch-tokens`, `GET /v1/challenge`, `POST /v1/register`, `POST /v1/token/validate`, `POST /v1/token/renew`, `POST /v1/token/release`, `POST /v1/delegate`.

---

## SDK-002: App as Container, Not Peer

### Context

Early drafts modeled `App` and `Agent` as peer classes — both were independent clients that talked to the broker separately. This was architecturally wrong.

In the broker's implementation, the app is the source of agent authority. Without an app registration, there is no scope ceiling. Without app auth, there is no app JWT. Without an app JWT, there is no launch token. Without a launch token, the agent cannot register in the production path.

The SPIFFE ID format (`spiffe://{trustDomain}/agent/{orchID}/{taskID}/{instanceID}`) does not include the app, which initially suggested the agent was independent. But the `AppID` field on `LaunchTokenRecord` and `AgentRecord` preserves the provenance chain, and the scope ceiling enforcement at launch token creation (`ScopeIsSubset(allowed_scope, appRec.ScopeCeiling)`) makes the app the gatekeeper.

### Decision

**`AgentAuthApp` is the container. Agents are created by and live inside it.** The class hierarchy reflects the authority chain: `AgentAuthApp` is the developer's entry point, `Agent` is created via `app.create_agent()` and holds a back-reference to its parent app.

### Consequences

- `Agent` objects cannot be constructed directly by the developer. They are always produced by `AgentAuthApp.create_agent()`.
- The `Agent` holds an internal `_app` reference for transport reuse and for operations that need the app context (like re-authentication if needed).
- The SDK's architecture diagram places agents inside the app subgraph, matching the runtime trust model.
- This inverts the initial design where `Agent` was a standalone class. Code that previously created agents independently must now go through an `AgentAuthApp` instance.

---

## SDK-003: App JWT Management Is Internal

### Context

To create launch tokens, the developer needs an app JWT (obtained via `POST /v1/app/auth` with `client_id` and `client_secret`). The app JWT expires. In the manual integration path (documented in `getting-started-developer.md`), the developer must manage this JWT themselves — check expiry, re-authenticate, handle token rotation.

This is ceremony that adds no value. The developer already proved they have the credentials by constructing `AgentAuthApp`. Managing the app session is a transport concern, not a business concern.

### Decision

**The SDK manages the app JWT lifecycle internally.** `AgentAuthApp.__init__()` stores the credentials. The first call that needs an app JWT triggers `POST /v1/app/auth`. Subsequent calls reuse the cached JWT. When the JWT expires, the SDK re-authenticates automatically before retrying the operation.

### Consequences

- The developer never sees an app JWT, never handles its expiry, and never calls an "authenticate" method.
- The `_AppSession` internal model is not part of the public API.
- If the `client_secret` is revoked by the operator, the next operation that triggers re-authentication will fail with an `AuthenticationError`. The developer handles this at the operation level, not at a session management level.
- Thread safety of the internal app session must be considered in the implementation (e.g., a lock around re-authentication to prevent thundering herd).

---

## SDK-004: Launch Tokens Are Internal to `create_agent()`

### Context

Agent registration requires a launch token. In the manual path, the developer must:

1. Authenticate as the app
2. Create a launch token with appropriate scope
3. Generate an Ed25519 keypair
4. Fetch a challenge nonce
5. Sign the nonce
6. Call register with the launch token and signed nonce

This is a 6-step ceremony for what is conceptually one operation: "create an agent with these scopes for this task."

### Decision

**`create_agent()` handles the entire ceremony internally.** The developer calls `app.create_agent(orch_id, task_id, requested_scope)` and gets back an `Agent`. Launch tokens, challenges, nonce signing, and the Ed25519 handshake are internal.

An advanced/lower-level API (`get_challenge()`, `register()`) is available for developers who need to split the registration across processes or handle custom key management, but the standard API hides it.

### Consequences

- The developer's happy path is one method call.
- Launch tokens are never exposed in the standard API. The `_LaunchToken` model is internal.
- The tight timing window (30-second nonce expiry, 30-second launch token TTL) is handled by the SDK performing all steps in rapid succession within `create_agent()`.
- If any step fails (e.g., scope exceeds ceiling at launch token creation), the error surfaces from `create_agent()` with a clear exception, not from an intermediate step the developer doesn't understand.
- The advanced API exists as an escape hatch, not the recommended path.

### Review: Do Any Intermediate Values Leak?

During review, we audited every intermediate value produced inside `create_agent()` to confirm nothing is needed outside the method boundary:

| Intermediate value | Source | Needed after registration? | Why |
|---|---|---|---|
| App JWT | `POST /v1/app/auth` | No (by the developer) | Managed internally by `AgentAuthApp` for all operations, not just agent creation |
| Launch token | `POST /v1/app/launch-tokens` | **No** | Single-use. The broker consumes it during registration. It ceases to exist. |
| Ed25519 private key | Generated locally | **No** (for any current broker endpoint) | `renew()`, `release()`, and `delegate()` all authenticate with the Bearer JWT, not the private key |
| Challenge nonce | `GET /v1/challenge` | **No** | Single-use, expires in 30 seconds, consumed during `POST /v1/register` |
| Signature + public key | Computed locally | **No** | Sent once during registration, never referenced again |
| agent_id, access_token, expires_in, scope | `POST /v1/register` | **Yes** | These become the `Agent` object's public attributes |

The Ed25519 private key deserved the closest scrutiny. After the challenge-response handshake, every subsequent broker call (`POST /v1/token/renew`, `POST /v1/token/release`, `POST /v1/delegate`) authenticates using the **agent's JWT as a Bearer token** — not the Ed25519 key. The broker verifies that JWT using **its own signing key**. The agent's Ed25519 key proved ownership exactly once during registration, then the JWT takes over as the credential. This is the core design pattern from the broker: exchange a cryptographic proof for a short-lived token, then use the token for everything.

Specifically for token renewal: `POST /v1/token/renew` takes no request body. The broker reads the JWT from the `Authorization` header, verifies it with the broker's signing key, revokes the old JTI, and issues a new JWT with the same scope, subject, and original TTL. The agent's private key is not involved.

The SDK stores the private key internally (`Agent._private_key`) as a defensive measure in case a future broker feature requires re-attestation (e.g., re-proving key ownership after a certain number of renewals). But no current endpoint needs it post-registration.

**Conclusion:** `create_agent()` is a clean boundary. Every intermediate value is either consumed (launch token, nonce) or internal (app JWT, private key). The only output is the `Agent` object. No state leaks.

---

## SDK-005: `agent_name` Is Auto-Generated, Not Required

### Context

The broker's `CreateLaunchTokenReq` has an `agent_name` field. Early SDK drafts made this a required parameter for `create_agent()`, implying it was part of the agent's identity.

Investigation of the broker code (`internal/store/sql_store.go`) revealed that `agent_name` is stored only on the `LaunchTokenRecord`. It does not appear in the SPIFFE ID, the agent's JWT claims, or the `AgentRecord`. It is purely a human-readable audit label — useful for operators reviewing launch token logs, but irrelevant to the agent's identity or authorization.

### Decision

**`agent_name` is auto-generated from `f"{orch_id}/{task_id}"`.** An optional `label` parameter on `create_agent()` allows the developer to override it for their own audit convenience.

### Consequences

- `create_agent()` has three required parameters: `orch_id`, `task_id`, `requested_scope`. This is the minimum information the developer must provide.
- The developer is not misled into thinking they are "naming" the agent. The agent's identity comes from the broker (SPIFFE ID with broker-generated `instanceID`).
- Operators still get a meaningful label in their launch token audit logs.
- If a developer wants a custom label (e.g., `"customer-search-agent"`), they can pass `label="customer-search-agent"`.

---

## SDK-006: Agents Cannot Validate Themselves

### Context

The initial design gave `Agent` a `validate()` method — a convenience shortcut for `agentauth.validate(broker_url, self.access_token)`. This seemed ergonomic: the agent could check if its own token was still valid.

The problem: the agent is an AI process that could be compromised by prompt injection. If a compromised agent can call `self.validate()` and get back `ValidateResult(valid=True, claims=...)`, what does that prove? Nothing. The compromised agent could:

1. Skip the validation call entirely
2. Call it but ignore the result
3. Report the result dishonestly to whatever downstream system asked

Validation is a **trust check performed by a trusted party on an untrusted party.** The app is the trusted party. The agent is the untrusted party. The untrusted party cannot meaningfully validate itself.

### Decision

**`Agent` has no `validate()` method.** Token validation is exclusively the app's responsibility. The app calls `app.validate(agent.access_token)` or the module-level `validate(broker_url, token)` before granting the agent access to tools.

### Consequences

- The `Agent` class has three methods: `renew()`, `release()`, and `delegate()`. All three are operations where the broker is the enforcer — the agent cannot escalate through any of them.
- `validate()` exists as a module-level function and as a convenience method on `AgentAuthApp`. Both are called by the app's code, never by the agent's code.
- The "tool-gating pattern" is explicit: the app validates the agent's token, checks the agent's scope against the tool's requirements, then grants or denies access. This is documented as the primary security pattern in the SDK.
- This is a departure from the "convenience shortcut on both classes" design. The asymmetry is intentional and reflects the trust model.

---

## SDK-007: `validate()` and `scope_is_subset()` Are Module-Level Functions

### Context

Early designs placed `validate()` and `scope_is_subset()` as methods on a class — first on both `App` and `Agent`, then only on `App`. The problem with class methods: these operations are stateless. `validate()` takes a broker URL and a token string. `scope_is_subset()` takes two lists of scope strings. Neither requires an instance of anything.

Resource servers (tools, APIs, downstream services) that receive an agent's bearer token also need to validate it and check scope. These resource servers don't have an `AgentAuthApp` instance — they just have the broker URL and the token from the incoming request.

### Decision

**`validate()` and `scope_is_subset()` are module-level functions** in the `agentauth` package. `AgentAuthApp.validate()` exists as a convenience shortcut that passes its own `broker_url` and `timeout`, but the underlying function is importable directly.

```python
from agentauth import validate, scope_is_subset

result = validate("https://broker.example.com", token_from_request)
if result.valid and scope_is_subset(["read:data:customers"], result.claims.scope):
    grant_access()
```

### Consequences

- Resource servers can use `validate()` without constructing an `AgentAuthApp`. They just need `pip install agentauth` and the broker URL.
- The functions are stateless and testable in isolation — no mocking of class internals needed.
- `AgentAuthApp.validate(token)` is a thin wrapper: `return validate(self.broker_url, token, timeout=self._timeout)`. This keeps the app-centric API ergonomic while not locking the functionality into a class.
- `scope_is_subset()` is a pure function with no network calls. It mirrors the broker's `authz.ScopeIsSubset` logic for local pre-flight checks.

---

## SDK-008: `renew()` Mutates the Agent In-Place

### Context

When an agent's token is renewed via `POST /v1/token/renew`, the broker revokes the old JTI and issues a new token with the same scope, TTL, and subject. The agent is the same agent — same SPIFFE ID, same scope — just with a fresh token.

Two design options:
- **Option A: Return a new `Agent` object.** The old object becomes stale. The developer must replace their reference.
- **Option B: Mutate the existing `Agent` in-place.** Update `access_token` and `expires_in`. The developer's reference stays valid.

### Decision

**`renew()` mutates the `Agent` in-place.** It updates `self.access_token` and `self.expires_in`. The `agent_id` and `scope` remain unchanged.

### Consequences

- The developer does not need to track which variable holds the "current" agent. `agent.renew()` just works, and subsequent calls using `agent.bearer_header` use the new token.
- Code that passes the `Agent` to other functions doesn't break after renewal — those functions still hold a valid reference.
- The old token is invalid after renewal (the broker revoked it). If the developer captured `agent.access_token` as a string before renewal, that string is now a revoked token. This is documented behavior but could surprise developers who cache tokens externally.
- `release()` sets an internal flag that prevents further `renew()` or `delegate()` calls.

---

## SDK-009: Broker-Side Token Validation Only (No Local JWT Verification)

### Context

JWTs can be verified two ways:
1. **Remote:** Call the broker's `POST /v1/token/validate` endpoint.
2. **Local:** Fetch the broker's public key (via `GET /v1/jwks` or `GET /.well-known/openid-configuration`) and verify the JWT signature locally.

Local verification is faster (no network round-trip) but requires the SDK to manage signing key material — fetching JWKS, caching it, handling key rotation, and dealing with the race between key rotation and token issuance.

### Decision

**MVP uses remote validation only.** All calls to `validate()` hit `POST /v1/token/validate` on the broker.

### Consequences

- Every validation requires a network call. For high-throughput tool-gating, this adds latency.
- The SDK does not need to handle JWKS fetching, caching, or key rotation logic. This is significant complexity avoided.
- The broker's revocation list is always checked. Remote validation catches revoked tokens that local verification would miss (since revocation is not encoded in the JWT itself).
- Local JWT verification is explicitly listed as future work. When implemented, it should be opt-in (e.g., `validate(token, mode="local")`) and documented with the caveat that it cannot detect revocation.

---

## SDK-010: Sync-First, No Async in MVP

### Context

Python has two I/O paradigms: synchronous (blocking) and asynchronous (`asyncio`). Supporting both requires either:

- Two complete API surfaces (`AgentAuthApp` and `AsyncAgentAuthApp`) with nearly identical logic
- A sync wrapper around an async core (fragile, leaks event loop concerns)
- An async wrapper around a sync core (defeats the purpose of async)

`httpx` supports both paradigms, so the transport layer can be swapped later.

### Decision

**The MVP is synchronous only.** All methods block until the HTTP response arrives.

### Consequences

- The API surface is exactly one class per concept: `AgentAuthApp`, `Agent`. No `AsyncAgentAuthApp`, no `AsyncAgent`.
- Developers using `asyncio` must use `asyncio.to_thread()` or similar wrappers, which is suboptimal but functional.
- Async support is deferred to a future milestone, likely as `agentauth.aio.AgentAuthApp` with the same API signatures but `async def` methods.
- `httpx` was chosen partly because it supports both sync and async, making the future migration straightforward.

---

## SDK-011: `httpx` for Transport, `cryptography` for Ed25519

### Context

The manual integration examples in `getting-started-developer.md` use `requests` for HTTP and `cryptography` for Ed25519. Two library decisions for the SDK:

**HTTP transport:**

| Option | Pros | Cons |
|--------|------|------|
| `requests` | Widely known, simple API | No async support, no HTTP/2, connection pool management is manual |
| `httpx` | Sync and async, HTTP/2, modern timeout model, connection pooling | Less widely known (but growing) |
| `aiohttp` | Best async support | Async-only, no sync path |
| `urllib3` | Low-level, full control | Too low-level for an SDK, poor developer ergonomics |

**Crypto:**

| Option | Pros | Cons |
|--------|------|------|
| `cryptography` | Standard, audited, Ed25519 support, already in manual examples | Large dependency |
| `PyNaCl` | Good Ed25519 API | Additional dependency with C bindings |
| `ed25519` (pure Python) | No C dependency | Slow, unmaintained |

### Decision

**`httpx` for HTTP. `cryptography` for Ed25519.**

### Consequences

- `httpx` gives us a clean migration path to async without changing the transport layer. Its timeout model (`httpx.Timeout`) handles connect, read, write, and pool timeouts separately, which matters for the tight registration window.
- `cryptography` is already what developers use in the manual path. Migrating to the SDK doesn't require learning a new crypto library.
- Both are well-maintained, widely used, and have binary wheels for all major platforms.
- The SDK's dependency footprint is two runtime dependencies: `httpx` and `cryptography`. This is lightweight for a security SDK.

---

## SDK-012: `orch_id` and `task_id` Guidance Is an SDK Responsibility

### Context

The SPIFFE identity format is `spiffe://{trustDomain}/agent/{orchID}/{taskID}/{instanceID}`. The broker code (`internal/identity/id_svc.go`) validates that `orch_id` and `task_id` are non-empty strings and that they produce valid SPIFFE path segments, but provides no guidance on what values developers should use. The Go code comments say only: "OrchID identifies the orchestrator that launched this agent" and "TaskID identifies the specific task this agent was created for."

The upstream [Ephemeral Agent Credentialing pattern v1.3](https://github.com/devonartis/AI-Security-Blueprints/blob/main/patterns/ephemeral-agent-credentialing/versions/v1.3.md) uses `orchestration_id` and `task_id` in examples but does not prescribe how developers should derive them.

Neither the broker documentation (`api.md`, `concepts.md`, `getting-started-developer.md`) nor the Go codebase documents where these values come from, what makes a good choice, or what the consequences of a bad choice are. This was identified during SDK design review.

The broker owns `trustDomain` (operator-configured via `AA_TRUST_DOMAIN`, default `"agentauth.local"`) and `instanceID` (broker-generated, 16 random hex chars). The developer only supplies `orch_id` and `task_id`.

### Decision

**Developer guidance for choosing `orch_id` and `task_id` is an SDK-level documentation concern.** The SDK PRD includes a dedicated section explaining what these values represent, how to derive them, format constraints, framework-specific examples, and revocation implications. The broker docs will be backfilled from this guidance (tracked as TECHDEBT).

Key guidance points:

- **`orch_id`** — identifies the orchestration system or application that launches agents. The app name is a natural choice, especially in multi-app environments (e.g., `"data-pipeline"`, `"customer-analyzer"`, `"crewai-crew-1"`). It groups all agents from the same source in SPIFFE IDs and audit trails.
- **`task_id`** — identifies the specific unit of work. Can be a random UUID, an incrementing counter, a job ID from your system, or any string that uniquely identifies the task. The critical consideration is **revocation granularity**: `POST /v1/revoke` with `level: "task"` invalidates all tokens sharing a `task_id`. Meaningful task IDs enable surgical revocation; reused task IDs cause collateral revocation.
- **Format constraints** — both must be non-empty and valid SPIFFE path segments (URL-safe, no `/` or `..`). The broker enforces non-empty; the `go-spiffe/v2` library validates path segment rules.
- **Trust domain and instance ID** are not developer concerns — the broker handles them.

### Consequences

- The SDK's `create_agent()` docstring and the PRD section [Choosing `orch_id` and `task_id`] provide the canonical guidance.
- Broker-side docs (`api.md`, `concepts.md`, `getting-started-developer.md`) are marked as TECHDEBT to be updated with this guidance.
- Developers have concrete examples for common frameworks and scenarios.
- The revocation implication of `task_id` choice is explicitly documented, preventing the "why did revoking one task kill all my agents?" surprise.

---

## Relationship to Broker Decisions

The SDK decisions above are constrained by the broker's design decisions (documented in [Design Decisions](../design-decisions.md)):

| Broker Decision | SDK Constraint |
|----------------|----------------|
| Decision 1 (Tokens) | SDK issues and manages tokens, never API keys |
| Decision 2 (JWTs) | SDK models mirror JWT claims structure |
| Decision 3 (Ed25519) | SDK uses `cryptography` for Ed25519 key generation and nonce signing |
| Decision 4 (Short-lived + renewal) | SDK provides `agent.renew()` with in-place mutation |
| Decision 5 (Launch tokens) | SDK hides launch tokens inside `create_agent()` |
| Decision 6 (action:resource:identifier scopes) | SDK provides `scope_is_subset()` mirroring `authz.ScopeIsSubset` |
| Decision 7 (Three roles) | SDK serves only the App and Agent roles; Admin is excluded |
| Decision 8 (No sidecar) | SDK talks directly to the broker; no sidecar dependency |
| Decision 9 (Not OAuth) | SDK implements AgentAuth's own token protocol, not OAuth flows |
| Decision 11 (Four revocation levels) | SDK handles 403 from revoked tokens; revocation API itself is operator-only |
| SPIFFE ID structure (implicit) | SDK documents `orch_id`/`task_id` guidance (SDK-012); broker docs marked TECHDEBT to port this guidance |
