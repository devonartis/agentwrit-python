# MEMORY.md — agentauth-python

## Mission

Python SDK for the AgentAuth credential broker. Wraps the broker's Ed25519 challenge-response flow into simple function calls. Open-source core — no HITL, no OIDC, no enterprise code.

## Origin

Extracted from `devonartis/agentauth-clients` (monorepo) on 2026-04-01 using `git filter-repo`.

**Key documents in parent project (`agentauth-core`):**
- Design doc: `.plans/designs/2026-04-01-python-sdk-repo-design.md` — full design with extraction, HITL removal, API audit, testing strategy
- Release strategy: `.plans/release-strategy.md` — 4-phase plan (repo cleanup, SDK setup, SDK update, enterprise extensions)
- FLOW.md — decision log including SDK repo model choice (Stripe/Twilio per-language pattern)
- MEMORY.md — migration lessons, especially B6 session on role model and code comments

## Standing Rules

- **Strict type safety** — every variable, parameter, return annotated. `mypy --strict`. No `Any` without justification.
- **`uv` only** — no pip, no poetry, no conda.
- **No enterprise code** — zero HITL/OIDC/cloud/federation. Contamination check: `grep -ri "hitl\|approval\|oidc\|federation\|sidecar" src/ tests/` must return nothing after cleanup.
- **API source of truth** is `agentauth-core/docs/api.md` — not the SDK code, not the old broker.
- **Live broker testing mandatory** — don't trust docs or code inspection alone. Stand up the core broker and verify.

## Current State

**Status:** v0.3.0 SDK closure in flight on branch `feature/v0.3.0-sdk-closure`. Phase 1 done, Phases 2–7 specs drafted, ready for plans + execution.

**Active line of work:** v0.3.0 SDK closure — 25 findings from two audits (field-level gap review + Codex adversarial pass + developer-docs re-audit). Recovers dropped broker response fields, fixes cache correctness bugs, adds missing endpoints, observability, and docs.

**Demo app ARCHIVED** (commit `958541f`, 2026-04-04). The v2 "5-agent LLM pipeline" design exposed that the SDK couldn't support it cleanly (no `delegation_chain` client-side, no SPIFFE ID in `get_token()`, no `request_id` correlation). Fix the SDK first, rebuild the demo after v0.3.0 ships. Demo design docs preserved for future rebuild: `.plans/designs/2026-04-01-demo-app-design-v2.md`, `.plans/designs/2026-04-01-demo-app-design-v3.md`.

**What's done:**
- v0.2.0 shipped — HITL removed, API aligned, 119 unit + 13 integration tests green
- Two SDK audits complete: `.plans/2026-04-02-sdk-broker-gap-review.md` (G1–G15 + Codex review), `.plans/designs/2026-04-04-v0.3.0-sdk-design.md` (G0, G16–G25)
- v0.3.0 design doc locked in (`.plans/designs/2026-04-04-v0.3.0-sdk-design.md` — 526 lines, 25 findings, 7 phases, all decisions resolved)
- **Phase 1 (G0) shipped** — `AgentAuthClient` → `AgentAuthApp` rename, commit `33fb2f4`
- **Phase 2–7 specs drafted** (2026-04-05, `.plans/specs/2026-04-05-v0.3.0-phase{2..7}-*-spec.md`, 6 files, 2173 lines total)

**What's next (in dependency order):**
1. Phase 2 (Cache Correctness — G13/G14/G15/G16) — smallest, most contained, unblocks everything
2. Phase 3 (Result Types — G1–G4, G8, G11, G17, G18) — biggest phase; `TokenResult`, `DelegationResult`, `TokenClaims` dataclasses
3. Phase 4 (Missing Endpoints — G5 `renew_token`, G24 `decode_claims`)
4. Phase 5 (Ergonomics — G19 rename, G20 idempotent release, G21 nonce freshness, G23 pre-flight scope)
5. Phase 6 (Observability — G6/G7/G10/G22 + logging; can run parallel to 4/5)
6. Phase 7 (Docs + Release — G25 CHANGELOG scrub + full doc refresh + 0.3.0 version bump)

**Immediate next step:** Draft Phase 2 acceptance stories + impl plan via `superpowers:writing-plans`, then execute via `superpowers:executing-plans`.

**What's NOT done (see FLOW.md roadmap):**
- v0.3.0 Phases 2–7 (coding)
- Demo application rebuild (blocked on v0.3.0)
- No CI (GitHub Actions)
- Not on PyPI yet
- Not pushed to GitHub as `divineartis/agentauth-python` yet

## Tech Debt

**All 25 items enumerated in v0.3.0 design doc (`.plans/designs/2026-04-04-v0.3.0-sdk-design.md`).** v0.3.0 closes them; this section stays sparse until post-v0.3.0.

- **Tracker drift:** `.plans/tracker.jsonl` still holds archived demo-app stories (DEMO-PC1..DEMO-S9). Needs archival + v0.3.0 phase story registration during devflow Step 5.

## Recent Lessons (last 3 sessions)

### v0.3.0 Planning + Archive Cleanup Session (2026-04-05)

**What happened:**
- Confirmed coverage of prior audits (SDK-broker field-level gap review + Codex adversarial pass + v0.3.0 design doc re-audit) — 12 dropped-field findings + 4 correctness bugs + 9 others = 25 total
- Drafted one umbrella spec covering all 24 remaining findings, then broke it up into **6 phase-scoped specs** per user feedback ("no big specs"): `.plans/specs/2026-04-05-v0.3.0-phase{2..7}-*-spec.md`
- Drafted Phase 2 (Cache Correctness) impl plan via `superpowers:writing-plans`: `.plans/2026-04-05-v0.3.0-phase2-cache-correctness-plan.md`
- Extracted Phase 2 acceptance stories (SDK-P2-S1..S4) into `tests/sdk-core/user-stories.md`
- Started brainstorming in-repo broker setup (replace `~/proj/agentauth-core` coupling) — design-in-progress, NOT yet saved
- **Archive cleanup:** 12 stale planning docs (demo app v1/v2/v3, HITL removal, PRD) moved to `.plans/ARCHIVE/` with:
  1. Unicode strikethrough (U+0336) applied to filenames → visible crossed-out in ls/Finder/VS Code sidebar
  2. `~~Title~~` markdown strikethrough + `> **Status:** ~~DONE/ARCHIVED/REJECTED/SUPERSEDED~~` banners inside each file
- All moves via `git mv` — history preserved

**Key decisions captured in specs:**
- `TokenExpiredError` deleted outright (not wired up) — `TokenResult.expires_at` makes expiry checkable by caller
- `decode_claims()` implements inline base64url decoder — no new `pyjwt` dep
- Pre-flight scope check is conservative — only obvious wildcard root mismatches rejected; ceiling wildcard `*` always defers to broker
- `X-Request-ID` auto-generated per-request, overridable via `app.request_context(...)` thread-local context manager
- Cache reverse-index is linear scan on `remove_by_token()` — O(n) fine for in-memory sizes

**Immediate next step:** Finish in-repo broker design doc (include docs-copy per user addition) → get user approval → writing-plans for broker implementation → then Phase 2 code execution against that in-repo broker.

### Dev Flow Session 2 (2026-04-01)

**What happened:**
- Wrote spec and implementation plan for HITL removal + API alignment
- Created `/broker` slash command for managing test broker (up/down/status)
- Discovered `examples/hitl-demo/` — missed in design doc, added to spec and plan
- Verified gates pass: mypy clean, 122 tests pass, ruff has pre-existing issues in examples/sdk-core scripts
- Context gate hit at 62% — saving state for fresh session

**Key findings:**
- HITL contamination is in 6 source files, 5 test files, 2 doc files, and 1 example app
- API field names appear aligned from code inspection (the known mismatches from parent project may have been fixed during monorepo phase) — needs live broker verification
- `_ChallengeResponse` TypedDict missing `expires_in` field (minor, Task 10 in plan)

### Extraction Session (2026-04-01)

**What happened:**
- Extracted from monorepo using `git filter-repo --subdirectory-filter agentauth-python/`
- Only 1 commit preserved — the monorepo conversion was a single commit. All prior history was in the monorepo root, not the subdirectory.
- Set up CLAUDE.md, MEMORY.md, FLOW.md, devflow-client skill

**What we know from parent project:**
- HITL contamination mirrors B0 sidecar removal from the broker — same pattern, different layer
- Known API mismatches: `token` vs `access_token`, `allowed_scopes` vs `allowed_scope`, `agent_name` required, nonce encoding (base64 vs hex)
- The existing `pyproject.toml` already has `mypy --strict` and `uv.lock` — aligns with our rules
