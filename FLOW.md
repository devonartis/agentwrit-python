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

**What the next session should do:**
1. Run `/devflow-client` — it will see Step 2 (Write Spec)
2. Write spec from design doc using SPEC-TEMPLATE
3. Continue through devflow: plan → acceptance tests → code → review → live test → merge

---

**Roadmap (after demo app):**
1. Push to GitHub as `divineartis/agentauth-python`
2. CI setup — GitHub Actions for lint, type check, unit tests on every PR
3. PyPI publishing — `agentauth` package on PyPI
4. TypeScript SDK — same process → `divineartis/agentauth-ts`
5. Archive `devonartis/agentauth-clients` monorepo
6. Repo rename: `agentauth-core` → `divineartis/agentauth`
