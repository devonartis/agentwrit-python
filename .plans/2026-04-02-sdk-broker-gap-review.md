# SDK–Broker Gap Review

> **Date:** 2026-04-02
> **Status:** Reviewed — Codex adversarial review added findings 12–15
> **Scope:** Every field the broker returns vs what the Python SDK exposes, drops, or hides.
> **Source of truth:** Broker handlers in `broker/internal/handler/`, `broker/internal/admin/`, `broker/internal/app/` (vendored). API spec: `broker/docs/api.md`.

---

## Method: How this review was done

1. Read every broker endpoint handler to extract the exact response structs and fields.
2. Read every SDK source file (`client.py`, `token.py`, `crypto.py`, `errors.py`, `retry.py`, `__init__.py`).
3. Compared field-by-field what the broker sends vs what the SDK returns, caches, or discards.
4. **Codex adversarial review** (GPT-5 Codex, 2026-04-02): cross-referenced broker source and SDK source for lifecycle bugs, concurrency issues, and cache correctness beyond field-level gaps. Added findings 12–15.

---

## Findings

### 1. `get_token()` drops `agent_id` from `/v1/register` response

**Severity: High**

The broker returns three fields from `POST /v1/register`:

```json
{
  "agent_id": "spiffe://agentauth.local/agent/orch/task/instance",
  "access_token": "eyJ...",
  "expires_in": 300
}
```

The SDK keeps `access_token` and `expires_in` (for cache) but discards `agent_id` entirely (`client.py:347-348`). `get_token()` returns a bare `str`.

**Impact:** To call `delegate()`, the caller needs the target agent's SPIFFE ID. Without it, they must make an extra `validate_token()` HTTP round-trip just to extract `claims["sub"]`. Every delegation example in the codebase does this workaround:
- `tests/integration/test_delegation.py:35-55`
- `tests/sdk-core/s7_delegation.py:50-53`
- `docs/api-reference.md:164-166`

---

### 2. `get_token()` hides `expires_in` from caller

**Severity: Medium**

`expires_in` is stored in the `TokenCache` internally but never exposed to the caller. `get_token()` returns `str`, so the caller has no way to know when their token expires without calling `validate_token()` and reading `claims["exp"]`.

**Impact:** Callers can't implement their own timeout logic, display token lifetime in UIs, or make scheduling decisions based on remaining TTL.

---

### 3. `delegate()` drops `expires_in`

**Severity: Medium**

The broker returns `expires_in` from `POST /v1/delegate`. The SDK discards it (`client.py:386-387`) and returns only the JWT string.

**Impact:** Same as #2 — caller can't reason about the delegated token's lifetime.

---

### 4. `delegate()` drops `delegation_chain`

**Severity: High**

The broker returns `delegation_chain` from `POST /v1/delegate` — an array of `DelegRecord` objects:

```json
{
  "access_token": "eyJ...",
  "expires_in": 60,
  "delegation_chain": [
    {
      "agent": "spiffe://agentauth.local/agent/orch/task/instance1",
      "scope": ["read:data:*", "write:data:*"],
      "delegated_at": "2026-02-15T12:00:00Z",
      "signature": "a1b2c3..."
    }
  ]
}
```

The SDK discards the entire chain (`client.py:386-387`). Only `access_token` is returned.

**Impact:** The delegation chain is the cryptographic provenance trail for C7 (Delegation Chain). It proves who delegated what to whom, when, with what scope, signed by the delegator. Dropping it means:
- No client-side audit capability
- No ability to inspect or log the chain of custody
- No way to verify delegation provenance without decoding the JWT

---

### 5. No `renew_token()` method — broker endpoint not exposed

**Severity: High**

The broker exposes `POST /v1/token/renew` which:
- Takes the current token as Bearer auth
- Returns a fresh JWT with new timestamps
- Preserves the original TTL
- Revokes the predecessor token
- Is a single HTTP call

The SDK has no `renew_token()` method. The cache's auto-renewal triggers `get_token()` again, which performs full re-registration:
1. `POST /v1/app/launch-tokens`
2. Ed25519 keygen
3. `GET /v1/challenge`
4. Nonce signing
5. `POST /v1/register`

That's 3 HTTP calls + crypto operations vs 1 HTTP call.

**Impact:** Higher latency for token renewal, unnecessary load on the broker, wasted crypto operations.

---

### 6. `request_id` dropped from error responses

**Severity: Medium**

Every broker error response includes `request_id` in the RFC 7807 body:

```json
{
  "type": "urn:agentauth:error:scope_violation",
  "title": "Forbidden",
  "status": 403,
  "detail": "requested scope exceeds ceiling",
  "instance": "/v1/app/launch-tokens",
  "error_code": "scope_violation",
  "request_id": "a1b2c3d4e5f6",
  "hint": "check your app's registered scope ceiling"
}
```

The SDK's `parse_error_response()` (`errors.py:105-172`) extracts only `detail` and `error_code`. The `request_id`, `hint`, `type`, and `instance` fields are all discarded.

**Impact:** `request_id` is the key for correlating SDK errors with broker-side audit logs. Without it, debugging production issues requires timestamp-based log correlation instead of exact request matching.

---

### 7. `X-Request-ID` header not sent or read

**Severity: Medium**

The broker supports client-sent `X-Request-ID` headers for distributed tracing. If present, the broker propagates it; if absent, the broker generates one and returns it in the response header.

The SDK:
- Never sends `X-Request-ID` on outgoing requests
- Never reads `X-Request-ID` from response headers
- Has no mechanism for the caller to provide or retrieve request IDs

**Impact:** No distributed tracing support. In a multi-agent pipeline, there's no way to trace a request through SDK → broker → audit log without manual correlation.

---

### 8. App `scopes` not exposed from constructor auth

**Severity: Low**

`POST /v1/app/auth` returns:

```json
{
  "access_token": "eyJ...",
  "expires_in": 1800,
  "token_type": "Bearer",
  "scopes": ["app:launch-tokens:*", "app:agents:*", "app:audit:read"]
}
```

The SDK stores `access_token` and `expires_in` but drops `scopes` and `token_type` (`client.py:174-177`).

**Impact:** Callers can't inspect what operational scopes their app was granted. Minor — these are fixed operational scopes, not the app's data scope ceiling.

---

### 9. Launch token `policy` dropped

**Severity: Low**

`POST /v1/app/launch-tokens` returns:

```json
{
  "launch_token": "a1b2c3...",
  "expires_at": "2026-02-15T12:01:00Z",
  "policy": {
    "allowed_scope": ["read:data:*"],
    "max_ttl": 600
  }
}
```

The SDK only uses `launch_token` and discards `expires_at` and `policy` (`client.py:289-290`).

**Impact:** Low — the launch token is ephemeral and consumed immediately. However, `policy` could be useful for debugging scope ceiling mismatches (the caller could see what ceiling the launch token was created with before registration fails).

---

### 10. `hint` dropped from error responses

**Severity: Low**

The broker's RFC 7807 error body includes an optional `hint` field with actionable fix guidance (e.g., "check your app's registered scope ceiling"). The SDK discards it.

**Impact:** Callers don't get the broker's troubleshooting suggestions. They only see the `detail` message.

---

### 11. `sid` (Session ID) in token claims — undocumented

**Severity: Low**

The broker's `TknClaims` struct includes a `sid` field (session ID). The SDK's `_ValidateTokenResponse` TypedDict doesn't mention it. The field does pass through in `validate_token()` since claims are typed as `dict[str, object]`, but it's invisible to SDK users reading the docs or TypedDicts.

**Impact:** Minor — the data isn't lost, just undocumented.

---

## Codex Adversarial Review Findings

*The following 4 findings were identified by Codex adversarial review (GPT-5 Codex) and were not caught in the original field-level gap analysis.*

### 12. Live API key in working tree (`.env`)

**Severity: Critical**

`.env` contains an unredacted `OPENAI_API_KEY`. The repo does not ignore `.env`, so accidental commit/push exposes the credential to anyone with repo access.

**Impact:** Immediate secret exposure risk. Not an SDK design gap — a repo hygiene blocker.

**Recommendation:** Rotate the key, remove `.env` from the working tree, add `.env` to `.gitignore`, and add secret-scanning protection.

---

### 13. Token cache aliases different task/orchestrator identities onto one credential (`token.py:40-42`)

**Severity: High**

The cache key is `(agent_name, frozenset(scope))`. But `get_token()` sends `task_id` and `orch_id` to `/v1/register`, and the broker embeds them in the JWT claims and SPIFFE subject (`spiffe://{domain}/agent/{orch}/{task}/{instance}`).

Two calls with the same agent name and scope but different `task_id` or `orch_id` hit the same cache entry. The second caller receives a token minted for the first task's identity.

**Impact:** Breaks task isolation. Corrupts audit trail and delegation provenance. A token scoped to `task_id="q4-analysis"` could be served to a caller requesting `task_id="q1-cleanup"`.

**Recommendation:** Include `task_id` and `orch_id` in the cache key: `(agent_name, frozenset(scope), task_id, orch_id)`.

---

### 14. Revoked tokens remain cached and can be returned (`client.py:389-405`)

**Severity: High**

After `revoke_token()` succeeds, the SDK never evicts the corresponding cache entry. A subsequent `get_token()` call with the same key returns the revoked token from cache (no broker call), which will then fail on use.

**Impact:** Post-revocation, stale dead tokens circulate inside the process until they expire or the 80% renewal threshold triggers re-registration. Confusing auth failures with no obvious cause.

**Recommendation:** `revoke_token()` should evict the cache entry for the revoked token. This requires either tracking a token→cache-key mapping or accepting the token string as a lookup parameter for eviction.

---

### 15. Concurrent `get_token()` calls can mint duplicate SPIFFE identities (`client.py:258-351`)

**Severity: Medium**

The cache-miss/renewal path is not serialized per key. `get_token()` does a cache lookup, a separate renewal check, and then the full registration flow with no per-key lock. Two threads hitting a cold cache (or both seeing needs_renewal=True) will both complete the full launch-token → challenge → register flow, each receiving a different SPIFFE ID from the broker.

The second thread's `put()` overwrites the first thread's cache entry. The first thread's token is now valid at the broker but orphaned — no reference to it exists in the SDK, so it can never be revoked or renewed.

**Impact:** Duplicate valid identities under load. Orphaned tokens that can't be revoked. Last-writer-wins cache corruption. Audit trail shows phantom registrations.

**Recommendation:** Add per-key locking (singleflight pattern) around the miss/renew path so only one registration runs per logical cache key at a time.

---

## Summary

| # | Gap | Location | Severity | Impact |
|---|-----|----------|----------|--------|
| 1 | `agent_id` dropped | `get_token()` | **High** | SPIFFE ID — forces extra HTTP call |
| 2 | `expires_in` hidden | `get_token()` | **Medium** | Token lifetime not exposed to caller |
| 3 | `expires_in` dropped | `delegate()` | **Medium** | Delegated token lifetime |
| 4 | `delegation_chain` dropped | `delegate()` | **High** | Entire cryptographic provenance trail |
| 5 | No `renew_token()` | Missing method | **High** | Lightweight renewal not available |
| 6 | `request_id` dropped | `parse_error_response()` | **Medium** | Audit log correlation key |
| 7 | `X-Request-ID` not used | All requests | **Medium** | Distributed tracing |
| 8 | App `scopes` not exposed | Constructor | **Low** | App operational scopes |
| 9 | Launch token `policy` dropped | `get_token()` internal | **Low** | Scope ceiling debugging info |
| 10 | `hint` dropped from errors | `parse_error_response()` | **Low** | Broker troubleshooting guidance |
| 11 | `sid` undocumented | TypedDicts/docs | **Low** | Session ID field invisible |
| 12 | Live API key in `.env` | Working tree | **Critical** | Secret exposure if committed |
| 13 | Cache key missing `task_id`/`orch_id` | `token.py:40-42` | **High** | Breaks task isolation, corrupts audit |
| 14 | Revoked tokens stay cached | `client.py:389-405` | **High** | Dead tokens returned post-revoke |
| 15 | Concurrent `get_token()` mints duplicates | `client.py:258-351` | **Medium** | Orphaned identities, cache corruption |

### Critical (1 item)
- #12: Live secret in working tree

### High severity (5 items)
- #1, #4: SDK discards broker response fields that callers need
- #5: Broker capability not exposed at all
- #13: Cache key doesn't include task/orchestrator identity
- #14: Revoked tokens not evicted from cache

### Medium severity (5 items)
- #2, #3: Lifetime info hidden or dropped
- #6, #7: No request tracing or audit correlation
- #15: Concurrent registration race condition

### Low severity (4 items)
- #8, #9, #10, #11: Debugging convenience and documentation gaps
