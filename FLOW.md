# FLOW.md — agentauth-python

Running decision log. Append after each meaningful action.

---

## 2026-04-01 — Repo Creation

### Decision: Extract from monorepo, not fresh start

Used `git filter-repo --subdirectory-filter agentauth-python/` from `devonartis/agentauth-clients`. Preserves commit history for the Python subdirectory. Design rationale in `agentauth-core/.plans/designs/2026-04-01-python-sdk-repo-design.md`.

### Decision: Stripe/Twilio per-language repo model

Each SDK gets its own repo with independent release cycle. Python first (`divineartis/agentauth-python`), TypeScript follows (`divineartis/agentauth-ts`). Decision made in `agentauth-core/FLOW.md` (2026-03-31 + 2026-04-01).

### Decision: `uv` + strict types as hard rules

`uv` is the only package manager. Every variable gets a type annotation. `mypy --strict` enforced. These are non-negotiable.

### Decision: Version starts at v0.2.0

Continues from monorepo's `v0.1.0`. Not a fresh start — the prior work counts.

### Status: Repo extracted, scaffolding set up (2026-04-01)

### 2026-04-01 — HITL Removal & API Alignment (v0.2.0) MERGED

**Spec:** `.plans/specs/2026-04-01-hitl-removal-api-alignment-spec.md`
**Plan:** `.plans/2026-04-01-hitl-removal-api-alignment-plan.md`
**Branch:** `feature/hitl-removal` → merged to `main`

Completed all 9 devflow steps. 14 commits, 2416 lines removed, 164 added.
Code review caught docs/ contamination — fixed before merge.
13 integration tests passed against live broker v2.0.0.

### 2026-04-01 — Demo App Design (brainstorm complete)

**Design doc:** `.plans/designs/2026-04-01-demo-app-design.md`
**Status:** Design APPROVED. Next: devflow Step 2 (Write Spec).

**Decisions made during brainstorm:**

1. **Progressive demo (not just happy-path)** — starts simple, reveals full 8-component story. Targets both indie developers and security leads.

2. **Financial data pipeline scenario** — combines data pipeline relatability (every LLM developer has one) with financial security stakes (DBS Bank scenario from v1.3 pattern doc). Orchestrator reads transactions, delegates to analyst with attenuated scope, writes risk assessments.

3. **Webapp, not CLI** — more impact for showing off the product. FastAPI + Jinja2 + HTMX (same stack as prior `agentauth-app`). Dark theme with accent purple inherited from existing design language.

4. **Dual view with pipeline + live dashboard** — pipeline runs on top, security machinery visible underneath in real-time. 8-component tracker lights up as each component is demonstrated.

5. **"Before/After" contrast is the landing view** — split-screen showing static API key (Okta/AWS/.env pattern) vs AgentAuth. The demo's purpose is adoption — it must show WHY, not just HOW. This is the answer to "why not just use Okta tokens for my agents?"

6. **Breach simulation with timeline** — "Simulate Compromise" button tries to use a read-only token for writes. Broker blocks it. Timeline shows: AgentAuth = 1 scope, 5 minutes, audited vs Traditional = everything, forever, no trail.

7. **SDK Explorer for complete coverage** — interactive panels for every SDK method: validate_token, caching demo, auto-renewal at 80% TTL, scope ceiling error, auth error. The pipeline alone only covers the happy path — the explorer covers everything.

8. **All 8 v1.3 pattern components demonstrated** — mapped in design doc table. C8 (Observability) served by the dashboard itself.

**Reference for design language:** `~/proj/agentauth-app/app/dashboard/` has the dark theme CSS, tabbed layout, HTMX partials. That app is stale and being deleted, but its visual design is the starting point.

### 2026-04-01 — Demo App Redesign (v2) + Full Planning

**Design v1 rejected** — showcase booth (staged buttons, SDK Explorer, contrast view) isn't a real-world app. Rethought from scratch.

**Design v2 approved** — real multi-agent LLM pipeline. 5 Claude-powered agents process 12 financial transactions. AgentAuth manages every credential. 2 adversarial transactions with prompt injection payloads. Security story emerges from watching real operations.

Key decisions:
1. LLM agents are mandatory, not optional — without them the app solves a problem that doesn't exist (deterministic code doesn't need AgentAuth)
2. Claude via Anthropic SDK directly — no provider abstraction (YAGNI)
3. Killed contrast view — the running pipeline IS the contrast
4. Killed SDK Explorer — the pipeline exercises every method naturally
5. Sample data baked in, not user-provided

**Artifacts produced (commit `92193de`):**
- Design v2: `.plans/designs/2026-04-01-demo-app-design-v2.md`
- Spec: `.plans/specs/2026-04-01-demo-app-spec.md`
- Stories: `tests/demo-app/user-stories.md` (3 preconditions + 9 acceptance)
- Plan: `.plans/2026-04-01-demo-app-plan.md` (10 tasks)
- Tracker: `.plans/tracker.jsonl`

**Devflow Steps 1-5 complete.** Next: Step 6 (Code) via `superpowers:executing-plans` in a fresh session.

### 2026-04-04 — Demo app archived, v0.3.0 SDK closure takes priority

**Decision:** Archive the demo app (commit `958541f`). SDK can't support the v2 multi-agent design — no `delegation_chain` exposed, no SPIFFE ID from `get_token()`, no `request_id` correlation. Fix the SDK first.

**Decision:** v0.3.0 design locked in (`.plans/designs/2026-04-04-v0.3.0-sdk-design.md`). 25 findings from 3 audits. 7 phases. Hard breaks only (pre-release, no aliases).

**Status:** Phase 1 (G0 rename `AgentAuthClient` → `AgentAuthApp`) shipped in commit `33fb2f4`.

**Next:** Phases 2–7 specs + impl plans.

### 2026-04-05 — v0.3.0 specs broken into per-phase files

**Decision:** 6 phase-scoped specs instead of one umbrella. Each spec is independently reviewable/mergeable with own goals, stories, and TDD order. Files: `.plans/specs/2026-04-05-v0.3.0-phase{2..7}-*-spec.md`.

**Next:** Draft Phase 2 acceptance stories + impl plan (`superpowers:writing-plans`), then execute (`superpowers:executing-plans`). Phase 2 first because it's contained and unblocks Phase 3's cache integration.

### 2026-04-05 — Phase 2 plan drafted + archive cleanup

**Decision:** Phase 2 impl plan saved to `.plans/2026-04-05-v0.3.0-phase2-cache-correctness-plan.md` (TDD tasks for G13/G14/G15/G16). Phase 2 acceptance stories (SDK-P2-S1..S4) extracted to `tests/sdk-core/user-stories.md`.

**Decision:** 12 stale planning docs archived into `.plans/ARCHIVE/` with Unicode strikethrough (U+0336) on filenames + `~~Status~~` banners inside. Active vs. archived is now visible at a glance in Finder/ls/VS Code. All moves via `git mv` (history preserved).

**Decision:** In-repo broker (replacing `~/proj/agentauth-core` coupling) confirmed as Option A — vendor Go source + aactl + docs into `broker/`. Design doc NOT yet saved (interrupted).

### 2026-04-05 — In-repo broker vendored + tracker reset

**Decision:** Skipped the in-repo broker design doc. Upstream (`agentauth-core`) is at code freeze, so there's nothing to discover — plain one-time `cp` vendor, no git subtree, no resync plan. Do-not-modify policy enforced via `broker/VENDOR.md`.

**Decision:** Vendor pinned at upstream commit `9b89f063deb3d885235ca02dfea42cf24bb52d56` (v2.0.0-259-g9b89f06). 107 files, 1.4M. Includes `cmd/`, `internal/`, `docs/`, Dockerfile, `docker-compose*.yml`, `go.mod/go.sum`, `scripts/stack_{up,down}.sh`. Scripts resolve paths relative to their own location — work correctly from `broker/` with no edits.

**Decision:** All active config/rules/skills/specs stripped of `~/proj/agentauth-core` path references. Repo is now self-contained: integration tests run via `./broker/scripts/stack_up.sh`, API contract is `broker/docs/api.md`. Historical references preserved in FLOW.md decision log, `broker/VENDOR.md` provenance, and ARCHIVE only.

**Decision:** Tracker reset. 17 stale entries (12 DEMO-* stories + 5 demo STEPs) moved to `.plans/ARCHIVE/tracker-demo-app.jsonl`. New tracker reflects v0.3.0 reality: Phase 1 DONE, Phase 2 Steps 1–5 DONE, Step 6 (Code) NOT_STARTED, SDK-P2-S1..S4 registered as ACCEPTANCE stories.

**Next:** ~~Execute Phase 2 code~~ — superseded by spec-driven rewrite (2026-04-06).

### 2026-04-06 — Spec-driven SDK rewrite replaces 7-phase incremental approach

**Decision:** Abandon the 7-phase v0.3.0 closure (25 findings, 6 phase specs, incremental patches). Replace with a clean rewrite driven by a comprehensive PRD (`NEW_SPECS_TO_USED.md`) + 12 ADRs (`SPEC_ADR.md`) written from the broker's Go source.

**Why:** The old approach patched a structurally wrong design. The v0.2.0 SDK modeled agents as opaque JWT strings (`get_token()` → `str`). The broker models agents as SPIFFE principals with identity, scope, lifecycle, and delegation chains. Incremental patches couldn't fix that mismatch — the SDK needed to be redesigned around the broker's actual trust hierarchy: app as container, agents as ephemeral per-task principals created by the app.

**Branch:** `feature/v0.3.0-sdk-spec-rewrite` (branched from `feature/v0.3.0-sdk-closure` to preserve spec files).

**What changes:**
- `requests` → `httpx` (ADR SDK-011)
- `get_token()` → `create_agent()` returning `Agent` with `renew()`, `release()`, `delegate()` (ADR SDK-002, SDK-004)
- Module-level `validate()` + `scope_is_subset()` (ADR SDK-007)
- `ProblemDetail` + typed exception hierarchy (spec Section 9)
- `AgentClaims`, `ValidateResult`, `DelegatedToken`, `RegisterResult`, `HealthStatus` models (spec Section 7)
- TokenCache + retry module removed
- Strict type safety (`mypy --strict`), module-level docstrings explaining broker alignment

**Old phase specs:** `.plans/specs/2026-04-05-v0.3.0-phase{2..7}-*-spec.md` — superseded, not deleted (git history).

### 2026-04-07 — Acceptance tests failed

**What happened:** Ran 8 acceptance stories against live broker. 3 passed (S1, S2, S3). 5 failed.

**Bug 1 (fixed): `validate()` parser KeyError on missing `aud`.** The spec model (`AgentClaims`) defines `aud: list[str]` but the broker's `/v1/token/validate` response doesn't return `aud`. The parser used `data["aud"]` instead of `data.get("aud", [])`. Root cause: wrote the parser without checking `broker/docs/api.md` for the actual response shape — trusted the model blindly. Fixed in commit `1f29008`. Added spec Section 8.1 (Response-to-Model Parsing Contract) defining required vs optional fields for all response parsers.

**Bug 2 (not fixed): rate limit from acceptance runner design.** Each acceptance script creates its own `AgentAuthApp` instance = separate `POST /v1/app/auth` call. 8 scripts = 8 auth calls in rapid succession = 429 from broker (10 req/min limit). The old v0.2.0 tests avoided this with a session-scoped pytest fixture in `conftest.py` that authenticated once. The new standalone scripts don't use pytest fixtures. Fix: rewrite acceptance scripts as pytest integration tests using the existing session-scoped `client` fixture from `conftest.py`, while keeping the banner + evidence output format.

**Lesson:** Don't write acceptance scripts as standalone processes when the broker has rate limits on auth. Use pytest session-scoped fixtures to share one authenticated app across all stories — same pattern as v0.2.0.

**Next:** Rewrite acceptance scripts as pytest tests using `conftest.py` session-scoped `client` fixture. Re-run all 8 stories. Capture evidence.

### 2026-04-07 — FIX_NOW.md rejected after investigation

**Decision:** `FIX_NOW.md` "critical design flaw" finding is INVALID after code review.

**Investigation:**
- Broker's `id_svc.go:111` implements ALL-OR-NOTHING scope enforcement
- If `requested_scope` exceeds launch token ceiling → registration fails with `403 scope_violation`
- If registration succeeds → `requested_scope` equals JWT scope exactly
- Current SDK code `scope=requested_scope` is CORRECT

**Why the finding was wrong:**
- Assumed Broker "attenuates" scope (grants subset on success)
- Reality: Broker "rejects" scope violations entirely
- Silent divergence between SDK state and JWT claims is IMPOSSIBLE

**Artifacts:**
- `REJECT-FIX_NOW.md` — original finding preserved for history
- `broker/BACKLOG.md` — deferred enhancement for explicit token validation (defense-in-depth, not bug fix)
- Commit `5107205` — full analysis in commit message

**What's next (immediate):**
- ~~Fix acceptance test runner~~ — DONE (2026-04-07)
- ~~Re-run all acceptance stories~~ — DONE (15 stories, all green)
- Demo app rebuild — spec ready, build on branch `feature/demo-app-v0.3.0`

### 2026-04-07 — Acceptance tests rewritten + SDK docs rewritten

**Decision:** Delete old 22-story test suite. It had broken delegation tests (never validated DelegatedToken), wrong scope formats (S18), and redundant stories. Replace with 15 clean stories, each testing one SDK behavior.

**How:** Used 5 independent sub-agents to review the old suite. Cross-referenced findings — only flagged issues that 3+ agents agreed on. Then brainstormed new stories with the user, debated what each should test and why, and built them one at a time against the live broker.

**Key discoveries from testing:**
- `agent.delegate()` uses the agent's registration token, not a delegated token. Multi-hop chains require raw HTTP for hop 2. (Story 7)
- Broker accepts same-scope delegation — equal is a valid subset. `broker_accepts_full_delegation = True`. (Story 8)
- Broker returns 400 (not 200) for empty-string token in validate(). SDK raises HTTPStatusError instead of returning ValidateResult. (Story 14 — removed empty string case)

**Artifacts (3 commits):**
- `b450f7f` — 15 new acceptance tests + all 5 docs rewritten
- `469fded` — Old tests deleted, run script updated, testing guide added
- `afcf5a4` — Demo app spec

**SDK docs rewritten (all were referencing v0.2.0 API that no longer exists):**
- README.md — updated quick start, diagrams, no fake features
- docs/getting-started.md — beginner walkthrough with create_agent() → Agent
- docs/concepts.md — roles, scopes (with real mistakes from testing), delegation, error model
- docs/developer-guide.md — lifecycle, delegation (single + multi-hop), scope gating, errors
- docs/api-reference.md — every class, method, dataclass, exception
- docs/testing-guide.md — how to run tests, what each story covers, how to add new ones

**Demo app spec:** `.plans/specs/2026-04-07-demo-app-spec.md` — FastAPI dashboard with 3 tabs (operator, developer, security), LLM pipeline, 22 tools, delegation demo, 6 scenario presets. References old demo at `showcase-authagent/apps/dashboard/`. To be built on branch `feature/demo-app-v0.3.0`.

---

**Roadmap (after v0.3.0):**
1. Push to GitHub as `divineartis/agentauth-python`
2. CI setup — GitHub Actions for lint, type check, unit tests on every PR
3. PyPI publishing — `agentauth` package on PyPI
4. TypeScript SDK — same process → `divineartis/agentauth-ts`
5. Archive `devonartis/agentauth-clients` monorepo
6. Repo rename: `agentauth-core` → `divineartis/agentauth`
