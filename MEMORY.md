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

**What's next:** Write implementation plan against the new spec, then execute.

**What's NOT done (see FLOW.md roadmap):**
- v0.3.0 SDK rewrite (coding)
- Demo application rebuild (blocked on v0.3.0)
- No CI (GitHub Actions)
- Not on PyPI yet
- Not pushed to GitHub as `divineartis/agentauth-python` yet

## Tech Debt

**Old 25-item phase list is superseded.** The new spec covers all material issues. Remaining tech debt will be tracked post-v0.3.0.

## Recent Lessons (last 3 sessions)

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
