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

**Status:** v0.2.0 merged. Demo app design approved — ready for spec (devflow Step 2).

**What's done:**
- HITL contamination fully removed (src/, tests/, docs/, README, examples)
- API contract verified against live broker — all fields aligned
- 119 unit tests, 13 integration tests passing
- mypy --strict clean, contamination guard tests in CI
- Version bumped to 0.2.0
- `/broker` slash command for managing test broker
- Demo app design approved: `.plans/designs/2026-04-01-demo-app-design.md`

**What's next:**
- Demo app: devflow Step 2 (Write Spec). Run `/devflow-client` to continue.
- Design: financial data pipeline webapp (FastAPI + Jinja2 + HTMX) with 4 sections: contrast view, pipeline runner, SDK explorer, live dashboard. All 8 v1.3 pattern components. All SDK methods.
- Key insight: demo must show "Before/After" — static API keys (Okta/AWS) vs AgentAuth. The contrast is the adoption pitch.
- Design language reference: `~/proj/agentauth-app/app/dashboard/` (dark theme, being archived)

**What's NOT done (see FLOW.md roadmap):**
- Demo application (design approved, code not started)
- No CI (GitHub Actions)
- Not on PyPI yet
- Not pushed to GitHub yet
- Not pushed to GitHub yet

## Tech Debt

None yet — this is a fresh extraction. Tech debt will be tracked here as it's discovered.

## Recent Lessons (last 3 sessions)

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
