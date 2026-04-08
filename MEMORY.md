# MEMORY.md — agentauth-python

## Mission

Python SDK for the AgentAuth credential broker. Wraps the broker's Ed25519 challenge-response flow into simple function calls. Open-source core — no HITL, no OIDC, no enterprise code.

## Standing Rules

- **Strict type safety** — every variable, parameter, return annotated. `mypy --strict`. No `Any` without justification.
- **`uv` only** — no pip, no poetry, no conda.
- **No enterprise code** — zero HITL/OIDC/cloud/federation. Contamination check: `grep -ri "hitl\|approval\|oidc\|federation\|sidecar" src/ tests/` must return nothing after cleanup.
- **API source of truth** is `broker/docs/api.md` (vendored, frozen — see `broker/VENDOR.md`) — not the SDK code, not the old broker.
- **Live broker testing mandatory** — don't trust docs or code inspection alone. Stand up the core broker and verify.

## Current State

**Status:** v0.3.0 SDK rewrite on branch `feature/v0.3.0-sdk-spec-rewrite`. Clean rewrite of `src/agentauth/` driven by a comprehensive PRD + ADRs that model the broker's actual trust hierarchy.

**Active line of work:** Rewrite the SDK from a flat token-vending design (`get_token()` → string) to a proper object model (`create_agent()` → `Agent` with lifecycle methods). The new spec was written from the broker's Go source and aligns 1:1 with the broker's app-as-container trust model.

**Spec (source of truth for v0.3.0):**
- `.plans/specs/NEW_SPECS_TO_USED.md` — full PRD (16 sections, ~970 lines)
- `.plans/specs/SPEC_ADR.md` — 12 architecture decision records (SDK-001 through SDK-012)

**What's done:**
- v0.2.0 shipped — HITL removed, API aligned, 119 unit + 13 integration tests green
- `AgentAuthClient` → `AgentAuthApp` rename (Phase 1 of old plan, commit `33fb2f4`)
- **In-repo broker vendored** (2026-04-05) — `broker/` pinned at upstream `9b89f06` (v2.0.0-259, frozen). Self-contained testing: `./broker/scripts/stack_up.sh`. See `broker/VENDOR.md`.
- **New PRD + ADRs written** (2026-04-06) — replaces the old 7-phase incremental approach

**What the rewrite changes (current → spec):**
- `requests` → `httpx` (ADR SDK-011)
- `get_token()` returning string → `create_agent()` returning `Agent` object (ADR SDK-002, SDK-004)
- No `Agent` class → `Agent` with `renew()`, `release()`, `delegate()` (ADR SDK-006, SDK-008)
- Ad-hoc error parsing → `ProblemDetail` + typed exception hierarchy (`ProblemResponseError`, `AuthorizationError`)
- No scope checking → `scope_is_subset()` module-level function (ADR SDK-007)
- `validate_token()` on app only → module-level `validate()` + `app.validate()` shortcut (ADR SDK-007)
- No typed response models → `AgentClaims`, `ValidateResult`, `DelegatedToken`, `RegisterResult`, `HealthStatus`
- `token.py` (TokenCache) → removed; agents are objects, not cached strings
- `retry.py` → removed; SDK does not retry by default (spec Section 9.2)

**What's done (2026-04-07):**
- v0.3.0 SDK rewrite complete — 99 unit tests passing
- **15 acceptance tests passing** (`tests/integration/test_acceptance_1_8.py`) against live broker
- **All SDK docs rewritten** for v0.3.0 (README, getting-started, concepts, developer-guide, api-reference, testing-guide)
- Demo app spec written (`.plans/specs/2026-04-07-demo-app-spec.md`)

**Acceptance test suite (15 stories, all green):**
- Stories 1-4: core lifecycle (create, renew, release, validate)
- Stories 5-8: delegation (narrow, rejected, multi-hop chain A→B→C, full-scope no-narrowing)
- Story 9: scope gating via scope_is_subset()
- Story 10: natural token expiry (5s TTL, no release)
- Story 11: RFC 7807 ProblemDetail error structure
- Story 12: multiple agents with isolated scopes
- Stories 13-15: released agent guard, garbage token handling, health check

**Key findings from acceptance testing:**
- Story 7: SDK `agent.delegate()` uses agent's registration token, not a received delegated token. Multi-hop chains (A→B→C) require raw HTTP for hop 2.
- Story 8: Broker ACCEPTS same-scope delegation (equal is a valid subset — `broker_accepts_full_delegation = True`)
- Old test suite (22 stories) was deleted — delegation tests never validated the DelegatedToken, scope formats were wrong, tests passed for wrong reasons

**What's NOT done (see FLOW.md roadmap):**
- Demo application rebuild (spec ready at `.plans/specs/2026-04-07-demo-app-spec.md`, build on branch `feature/demo-app-v0.3.0`)
- No CI (GitHub Actions)
- Not on PyPI yet
- Not pushed to GitHub as `divineartis/agentauth-python` yet

## Tech Debt

**Old 25-item phase list is superseded.** The new spec covers all material issues. Remaining tech debt will be tracked post-v0.3.0.

## Recent Lessons (last 3 sessions)

### Acceptance Test Rewrite (2026-04-07)

**What happened:**
- Reviewed old 22-story test suite with 5 independent sub-agents. Cross-referenced findings.
- 7 stories were broken: delegation tests (S7, S19, S22) never validated the DelegatedToken, S18 had scope format mismatch causing silent skips, S21 had ambiguous assertions, S17 passed for wrong reason (resource mismatch, not action mismatch).
- Rewrote from scratch: 15 stories, each testing ONE distinct SDK behavior, no redundancy.
- All 15 pass against live broker. Every SDK response captured in evidence files.
- Rewrote all 5 SDK docs — old docs referenced v0.2.0 API (`get_token()`, `ScopeCeilingError`, `requests`, token caching) that no longer exists.
- Added `docs/testing-guide.md` with instructions for running tests and adding new stories.
- Demo app spec written for next session.

**Lessons:**
1. Delegation tests MUST validate the `DelegatedToken.access_token` via `validate()`, not check `worker.scope` (registration scope ≠ delegation scope)
2. Scope format is `action:resource:identifier` — all three must match. `read:analytics:project-x` ≠ `read:data:analytics-project-x`
3. Every `if` check needs an `else: passed = False` — no silent skips
4. No wildcard `*` scopes on agents unless testing wildcard behavior specifically
5. `agent.delegate()` uses the agent's own registration token — multi-hop chains require raw HTTP for hop 2
6. Broker accepts same-scope delegation (equal is a valid subset)
7. Banner prints before test runs (4-second pause) so output is readable in real-time

### FIX_NOW.md Rejected (2026-04-07)

**Finding:** `FIX_NOW.md` claimed a critical design flaw where SDK uses `requested_scope` instead of Broker-granted scope, causing silent failures.

**Investigation:** Reviewed Broker's `id_svc.go:111` — implements ALL-OR-NOTHING scope enforcement:
- Request exceeds ceiling → `403 scope_violation` (registration FAILS)
- Request within ceiling → `200 OK` (scope equals request exactly)

**Verdict:** Finding INVALID. When registration succeeds, `requested_scope` IS the truth. No divergence possible. Broker is frozen, so attenuation behavior won't change.

**Action:**
- Renamed `FIX_NOW.md` → `REJECT-FIX_NOW.md` (preserved for history)
- Added `broker/BACKLOG.md` with deferred enhancement (explicit token validation methods for defense-in-depth)
- No code changes required — `orchestrator.py` remains correct

**Commit:** `5107205` — "docs: Reject FIX_NOW.md finding and add SDK validation backlog"


### Spec-Driven Rewrite Decision (2026-04-06)

**What happened:**
- New comprehensive PRD + ADRs written (`.plans/specs/NEW_SPECS_TO_USED.md`, `.plans/specs/SPEC_ADR.md`) — 12 ADRs, ~970-line spec grounded in broker Go source
- **Decision:** Abandon the incremental 7-phase approach (25 findings, 6 phase specs). The old approach patched a structurally wrong design. The new spec designs the SDK from first principles based on the broker's trust model.
- Created branch `feature/v0.3.0-sdk-spec-rewrite` from `feature/v0.3.0-sdk-closure` (to preserve spec files)

**Why the old approach was wrong:**
- `get_token()` returning a string erased agents as principals — the broker gives them SPIFFE identities, JWT claims, lifecycle methods
- No `Agent` class meant `delegate()`, `revoke_token()`, `validate_token()` all lived on `AgentAuthApp` with raw token strings passed around
- `requests` library had no async migration path; `httpx` does (ADR SDK-011)
- TokenCache was solving a problem that doesn't exist when agents are objects
- Error handling was ad-hoc instead of modeling RFC 7807 `ProblemDetail`

### In-Repo Broker Vendored (2026-04-05)

- Vendored into `broker/` — pinned at upstream `9b89f06` (v2.0.0-259, frozen)
- Self-contained testing: `./broker/scripts/stack_up.sh`
- Do not re-vendor unless upstream unfreezes

### Extraction + v0.2.0 (2026-04-01)

- Extracted from monorepo, HITL removed, API aligned, 119 unit + 13 integration tests green
- `pyproject.toml` has `mypy --strict` and `uv.lock`
