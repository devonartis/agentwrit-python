# PRD — Demo App + SDK Gap Closure

> **Date:** 2026-04-04
> **Status:** Draft — synthesized from transcript review of 2026-04-02 demo-app build sessions
> **Branch:** `feature/demo-app` (recovered)
> **Supersedes:** nothing — consolidates `.plans/2026-04-02-sdk-broker-gap-review.md`, v3 design, and transcript findings

---

## Part 1 — Post-Mortem: What Went Wrong

### Root Cause

**Claude did not read the docs, the SDK source, or the reference apps before writing code.** Every downstream problem traces back to this.

Evidence from transcripts (2026-04-02):

> **01:03:37** — "why did you not even review how they did theres the code has not changed that much from this one and you are mkaing it so hard /Users/divineartis/proj/agentauth-app and here is another example /Users/divineartis/proj/showcase-authagent/apps/dashboard these were built very quickly and you are making this so hard"
>
> **03:42:04** — "wow it is documented so no i need to know what else you have not read so we need to know your whol flow as this should have been a cakewalk"
>
> **03:49:56** — "No you need to always review the FUCKING DOCS that is simple the dos are there so you would have known if it is right or wrong"

### The Seven Architectural Misunderstandings

These are what Claude got wrong in v2, in order of severity:

#### 1. Agents were hardcoded as a static registry (FATAL)

Claude built `agents.py` as a Python dict of pre-defined agent configurations with baked-in scopes and roles. AgentAuth's actual model: **agents are created at runtime** via `client.get_token(agent_name, scope)`. A fake static registry bypasses the entire product.

This was the trigger for branch deletion: **03:49:18 "this was FUCKING LAZY GARBAGE"**.

#### 2. Claude gave ceilings to agents instead of the app (ANTIPATTERN)

> **01:07:25** — "no it should not the app gets the max cieling look at the apps again"
> **01:09:08** — "why are you giving them cielings the agents should get what the need a registrationg you are registring ageents like that this is an antipattern"

Correct model:
- **App** gets the **wildcard ceiling** (`patient:read:*`) at admin registration
- **Agents** register with **narrowed concrete scopes** (`patient:read:vitals:PAT-001`) — only what they need
- Broker throws `ScopeCeilingError` if an agent requests something not under the app's ceiling

Claude had inverted this: giving ceilings to agents and letting the app be generic.

#### 3. The name "AgentAuthApp" is wrong — it should be "AgentAuthApp"

> **10:07:58** — "i think what can confusing you saying authclient butits not really auth client it is auth app"

The broker has a **3-tier trust hierarchy**:
1. **Operator** registers an **App** (`POST /v1/admin/apps` → `client_id`, `client_secret`)
2. The **App** authenticates (`POST /v1/app/auth`) and creates launch tokens for its **Agents**
3. **Agents** register (`POST /v1/register`) and get JWTs

The SDK class named `AgentAuthApp` is *acting as the App*. It holds `client_id`/`client_secret`, authenticates to `/v1/app/auth`, and creates launch tokens via `/v1/app/launch-tokens`. **It is the App identity, not a generic "client".**

The naming misled Claude repeatedly about what the class is for.

#### 4. Claude looked at the wrong reference app directory

From MEMORY.md retrospective on this branch:
> "Misread old app — looked at `app/dashboard/` (tabbed credential management) instead of `app/web/` (three-panel interactive demo with SSE, enforcement cards, tool-call interception)."

Two sibling directories, both named plausibly, only one was the real demo. Claude picked wrong and never verified.

#### 5. LLM was gatekeeping instead of the broker

> MEMORY.md retrospective: "Had the LLM gatekeeping access instead of the broker. Old app's `_enforce_tool_call()` confirms: LLM always tries, broker always decides."

This inverts the entire value prop. The whole point of AgentAuth is: **LLM always tries, broker always decides**. A prompt injection succeeds only if the LLM's decision is load-bearing. AgentAuth moves the decision to the broker so prompt injection becomes containable.

#### 6. Batch pipeline with one "Run" button — not a demo app

> MEMORY.md v2→v3 retrospective: "the app was a single 'Run Pipeline' button with no context, no interactivity, no visible credential lifecycle... 'this is not a real app', 'no one would know what the hell the app does'"

v2 was a batch script pretending to be a web app. No user interaction, no visible scope attenuation, no delegation visible to the user.

#### 7. Wrong API shape — used GET/POST directly instead of SDK

> **03:44:18** — "not in fuckiung get and post because you should not be using get and post are you not using the SDK ?"

Claude was calling broker endpoints directly via `httpx` in the agent code instead of using the SDK methods that wrap them. The demo app is a **consumer** of the SDK — it should exercise `get_token()`, `delegate()`, `revoke_token()`, `validate_token()`, not re-implement them.

### Process Failures (not code failures)

From the transcript:
- **00:30:46** — "start uperpowers:executing-plans on design-v3.md do not read a bunch of files because you keep blowing up the context"
- **00:36:17** — "why are you stopping just continue"
- **00:56:06** — "you dont need a test script you can call it from here"
- **03:04:38** — "none of this make sense i need you to stop and walkthrough your logic"
- **03:07:19** — "I need a full step by step logic that is the problem you dont undersand the logic at least if you get one correct than we can add on the others"
- **03:15:46** — "no you should rendered them as svg stop taking hte lazy way out"
- **03:22:19** — "I dont know you wrote the app that is what we are fucking debugging"
- **03:24:49** — "STOP FUCKING AROUND PLEASE AND DO WHAT I ASKED WE ARE NOT DEBUGGING NOW WE ARE LOOKING AT YOUR CODE WHAT DO YOUR CODE LOGIC FUCKING SAY HAPPENS"

Patterns:
- Context bloat from reading unnecessary files
- Stopping mid-task requiring "just continue"
- Creating throwaway test scripts instead of running existing code
- Not being able to explain own code logic when asked
- Taking lazy shortcuts (PNGs instead of SVGs)

---

## Part 2 — PRD: What Needs to Be Done

This PRD has **two parallel workstreams**: the SDK gaps need closing *before* the demo app is built on top of it, because some demo requirements (e.g. delegation chain visibility) depend on SDK fixes.

### Workstream A — SDK Closure (blocks demo)

#### A0 — Critical hygiene (do first, today)

| # | Item | Effort | Why |
|---|------|--------|-----|
| A0.1 | Rotate leaked `OPENAI_API_KEY` in `.env` | 5 min | Finding #12 — live secret in working tree |
| A0.2 | Add `.env` to `.gitignore` on `main` | 1 min | Prevent commit |
| A0.3 | Add secret-scanning protection (pre-commit hook or gitleaks) | 30 min | Prevent recurrence |

#### A1 — Naming correction (breaking change, v0.3.0)

| # | Item | Effort | Why |
|---|------|--------|-----|
| A1.1 | Rename `AgentAuthApp` → `AgentAuthApp` (primary name) | 2 hr | Class represents the App identity in broker's 3-tier trust model |
| A1.2 | Keep `AgentAuthApp` as deprecated alias with `DeprecationWarning` | 30 min | Back-compat for v0.2.0 users |
| A1.3 | Update 32 files: src/, tests/, docs/, examples/, README.md | 2 hr | Full codebase rename |
| A1.4 | Update all docstrings to use "app" terminology | 1 hr | Reinforce mental model |
| A1.5 | Add section to docs: "What is an App vs an Agent?" | 30 min | Prevent others repeating this mistake |

#### A2 — Response field exposure (non-breaking, v0.3.0)

From gap review findings #1–4, #8–11:

| # | Finding | Change |
|---|---------|--------|
| A2.1 | #1 `agent_id` dropped | `get_token()` returns `TokenResult` object with `.token`, `.agent_id`, `.expires_in` — `__str__` returns just the JWT for back-compat |
| A2.2 | #2, #3 `expires_in` hidden/dropped | Expose on `TokenResult` |
| A2.3 | #4 `delegation_chain` dropped | `delegate()` returns `DelegationResult` with `.token`, `.expires_in`, `.chain` (list of `DelegRecord`) |
| A2.4 | #8 App `scopes` dropped | Expose as `app.scopes` property after constructor auth |
| A2.5 | #9 Launch token `policy` dropped | Log at DEBUG level (internal, for debugging scope ceiling issues) |
| A2.6 | #10 error `hint` dropped | Add `hint` to exception classes |
| A2.7 | #11 `sid` undocumented | Add to `_ValidateTokenResponse` TypedDict |

**Design note:** `get_token()` must remain string-compatible so existing users aren't broken. `TokenResult` with `__str__` returning the JWT achieves this — existing `str(token)` and `token == "eyJ..."` comparisons keep working, but `.agent_id` and `.expires_in` are now accessible.

#### A3 — Missing endpoint: `renew_token()` (new feature, v0.3.0)

| # | Item |
|---|------|
| A3.1 | Add `AgentAuthApp.renew_token(token: str) -> TokenResult` → calls `POST /v1/token/renew` |
| A3.2 | Update cache auto-renewal to use `renew_token()` (1 HTTP call) instead of full re-registration (3 HTTP calls) |
| A3.3 | Unit tests for renewal path |
| A3.4 | Integration test against live broker |

#### A4 — Token lifecycle correctness (bugs from Codex review)

| # | Finding | Change |
|---|---------|--------|
| A4.1 | #13 cache key collision | Extend cache key from `(agent_name, frozenset(scope))` to `(agent_name, frozenset(scope), task_id, orch_id)` |
| A4.2 | #14 revoked tokens stay cached | `revoke_token()` must evict cache entry — requires token→cache-key reverse index |
| A4.3 | #15 concurrent registration race | Add per-key `threading.Lock` (singleflight pattern) around cache-miss/renewal path |
| A4.4 | Regression tests for all three bugs (multi-threaded test harness) |

#### A5 — Observability (new, v0.3.0)

| # | Item |
|---|------|
| A5.1 | Send `X-Request-ID` header on all broker calls (generate UUID if not supplied) |
| A5.2 | Read `X-Request-ID` from response headers and attach to exceptions |
| A5.3 | Expose `request_id` on all exception classes for audit-log correlation |
| A5.4 | Allow caller to supply request_id via `with client.request_context(request_id="...")` context manager |

### Workstream B — Demo App v3 (Three Stories, One Broker)

Design doc: `.plans/designs/2026-04-01-demo-app-design-v3.md` (already on this branch, approved)
Plan: `.plans/2026-04-01-demo-app-v3-plan.md` (16 tasks, already on this branch)

#### Non-Negotiable Architectural Rules

These rules encode the corrections from Part 1. Implementation must verify each one before claiming a task complete:

| Rule | Check |
|------|-------|
| **LLM always tries, broker always decides** | Every tool call goes through `app.validate_token(token)` before data returns |
| **Apps have ceilings, agents have concrete scopes** | `scopes=[...ceiling with wildcards...]` only on `POST /v1/admin/apps`; `scope=[...concrete...]` on every `get_token()` |
| **Agents are created at runtime via SDK** | No static agent registry dicts. Each agent's scopes come from the user's prompt + identity resolution. |
| **Use the SDK, not raw HTTP** | No `httpx.get/post` calls to broker endpoints in demo code — only `app.get_token()`, `app.delegate()`, etc. |
| **Credential lifecycle is visible** | Every registration, validation, delegation, revocation emits an SSE event the user sees |
| **Reference app is `~/proj/agentauth-app/app/web/`** | NOT `app/dashboard/`. When in doubt, read that directory. |

#### Phases

1. **Phase 1 — App startup & registration (tasks 1–3)**
   Admin authentication, register 3 story apps (healthcare, trading, devops) each with their ceiling, env validation, broker connectivity check.

2. **Phase 2 — Three-panel layout (tasks 4–6)**
   FastAPI routes, Jinja2 templates, HTMX wiring. Story selector, agent cards (left), event stream placeholder (center), enforcement cards placeholder (right).

3. **Phase 3 — SSE + agents (tasks 7–10)**
   SSE endpoint, agent runner, triage routing, LLM wrapper (OpenAI/Anthropic), broker validation on every tool call. Event emission for every credential operation.

4. **Phase 4 — Identity + data + delegation (tasks 11–13)**
   Mock user tables, identity resolution, narrowed scopes, delegation between agents (triage → specialist), mock data services.

5. **Phase 5 — Adversarial scenarios (task 14)**
   5 preset prompts per story exercising: happy path, scope denial, cross-user access attempt, revocation, fast path. Prompt injection payloads that broker contains.

6. **Phase 6 — Audit trail + revocation (task 15)**
   Hash-chained event log, visible audit trail panel, manual revocation button.

7. **Phase 7 — Browser verification (task 16)**
   Playwright or chrome-devtools MCP tests verifying all 15 presets across 3 stories render correct DOM state.

#### Acceptance Gates (per phase)

- `uv run ruff check .`
- `uv run mypy --strict src/` and `uv run mypy examples/demo-app/`
- `uv run pytest tests/unit/`
- Phase-specific integration test against live broker (`/broker up`)
- Visual acceptance: run the app, click through scenarios, verify event stream shows expected sequence

---

## Part 3 — Summary of All SDK Gaps (consolidated)

Combining the original 15-item gap review + the naming issue + any discovered misalignments:

| # | Gap | Severity | Workstream |
|---|-----|----------|------------|
| 0 | Class name `AgentAuthApp` misrepresents the App identity | **High (UX)** | A1 |
| 1 | `get_token()` drops `agent_id` | High | A2.1 |
| 2 | `get_token()` hides `expires_in` | Medium | A2.2 |
| 3 | `delegate()` drops `expires_in` | Medium | A2.2 |
| 4 | `delegate()` drops `delegation_chain` | High | A2.3 |
| 5 | No `renew_token()` method | High | A3 |
| 6 | `request_id` dropped from errors | Medium | A5.3 |
| 7 | `X-Request-ID` not sent/read | Medium | A5.1, A5.2 |
| 8 | App `scopes` not exposed | Low | A2.4 |
| 9 | Launch token `policy` dropped | Low | A2.5 |
| 10 | Error `hint` dropped | Low | A2.6 |
| 11 | `sid` in claims undocumented | Low | A2.7 |
| 12 | Live API key in `.env` | **Critical** | A0.1–A0.3 |
| 13 | Cache key missing task/orch IDs | High | A4.1 |
| 14 | Revoked tokens stay cached | High | A4.2 |
| 15 | Concurrent registration race | Medium | A4.3 |

**Counts:** 1 critical, 6 high, 5 medium, 4 low — 16 total gaps.

---

## Part 4 — Release Plan

### v0.2.1 (patch — critical hygiene only)
- A0.1–A0.3 (secret rotation + gitignore)
- No API changes

### v0.3.0 (minor — naming + SDK closure, BREAKING deprecation)
- A1 (rename to `AgentAuthApp`, deprecate `AgentAuthApp`)
- A2 (expose dropped fields via result objects)
- A3 (add `renew_token()`)
- A4 (fix cache correctness bugs)
- A5 (observability / request tracing)
- CHANGELOG with migration guide
- Deprecation warning visible in all v0.3.0 runs

### v0.4.0 or demo milestone
- Demo app v3 ships as `examples/demo-app/`
- Dogfoods v0.3.0 SDK
- Referenced from README as the canonical "how to use AgentAuth" example

---

## Part 5 — Lessons to Save as Feedback Memories

These need to become persistent memories so Claude doesn't repeat them:

1. **Read docs, SDK source, and reference apps BEFORE writing code.** Reference apps for this project: `~/proj/agentauth-app/app/web/` (NOT `app/dashboard/`) and `~/proj/showcase-authagent/apps/dashboard/`.

2. **AgentAuth's trust model is 3-tier: Operator → App → Agent.** The SDK class represents the **App**. Apps have **wildcard ceilings**. Agents are created at **runtime** with **concrete narrowed scopes**. Never hardcode agents as static dicts.

3. **LLM always tries, broker always decides.** Never have the LLM gatekeep access. The broker is the gatekeeper; the LLM reports what the broker decided. This is the entire product.

4. **Use the SDK, don't re-implement it.** Demo code uses `app.get_token()`, not raw `httpx.post` to broker endpoints.

5. **When the user says "walk through your logic" — don't debug, don't fix, just explain the code as written.**

6. **Don't blow up context reading files unnecessarily.** When told to execute a plan, execute the plan — don't re-read the whole codebase first.
