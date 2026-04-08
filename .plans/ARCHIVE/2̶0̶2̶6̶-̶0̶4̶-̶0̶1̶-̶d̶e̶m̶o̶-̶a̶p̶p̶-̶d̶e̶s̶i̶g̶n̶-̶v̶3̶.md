# ~~Design: Three Stories, One Demo, One Broker (v3)~~

> **Status:** ~~ARCHIVED~~ — demo app shelved 2026-04-04. Kept for historical reference; will inform v0.3.0 demo rebuild.

**Created:** 2026-04-01
**Status:** APPROVED
**Supersedes:** `2026-04-01-demo-app-design-v2.md` (batch pipeline — rejected)
**Branch:** `feature/demo-app`

---

## Why This Exists

AgentAuth secures AI agents — not humans, not services. Traditional IAM (AWS IAM, Okta, Azure AD) gives agents static roles that don't change based on the task, the user, or the data being accessed. A prompt injection that tricks an LLM into requesting out-of-scope data succeeds because the IAM role allows it.

AgentAuth is different: every agent gets a unique identity, a short-lived scoped token, and every tool call is validated by the broker in real-time. The ceiling never moves. The LLM cannot talk its way past the broker.

This demo proves it across three real-world domains. The user types a scenario in plain English. The LLM reads it, decides which agents are needed, and AgentAuth spawns each one with exactly the tools it needs — nothing more. Every agent is born, does its job, and dies. The broker controls everything in between.

**Target audiences:**
- **Developer:** "I can let AI agents loose on sensitive data and the credential layer handles security automatically"
- **Security lead:** "Scope enforcement, delegation chains, surgical revocation, tamper-proof audit — per agent, per task, per tool call"
- **Decision maker:** "This is what replaces static API keys and IAM roles for AI agents"

---

## Stack

- **FastAPI + Jinja2** — server-rendered, no build step
- **HTMX** — structural swaps (story switching, identity block, agent cards, audit trail, summary)
- **SSE (Server-Sent Events)** — real-time event stream and enforcement cards
- **Vanilla JS** — SSE handler that updates all three panels from one event
- **AgentAuth Python SDK** — every agent gets scoped, ephemeral credentials via the broker
- **LLM (OpenAI or Anthropic)** — vendor-agnostic, auto-detected from env var
- **Mock data** — in-memory dicts for patients, traders, engineers. One real API call for stock prices.

## Requirements

- Broker running (`/broker up`)
- `AA_ADMIN_SECRET` set (matches broker)
- `OPENAI_API_KEY` or `ANTHROPIC_API_KEY` set (at least one)
- Missing any → clear error message, exit 1

---

## Architecture

### Single Page, Three Panels

```
┌──────────────────────────────────────────────────────────────────────────┐
│ [🔒 AgentAuth]  [Healthcare] [Trading] [DevOps]  [textarea...]   [RUN] │
├───────────────┬───────────────────────────────┬──────────────────────────┤
│  LEFT 260px   │      CENTER (flex)            │     RIGHT 300px          │
│               │                               │                          │
│  Identity     │  Event Stream (SSE)           │  Scope Enforcement       │
│  ┌─────────┐  │  +0.2s [SYSTEM] Registering   │  ┌────────────────────┐  │
│  │ Resolved│  │        healthcare-app...       │  │ get_vitals()       │  │
│  │ or Anon │  │  +0.5s [BROKER] App registered │  │ patient:read:vitals│  │
│  └─────────┘  │  +0.8s [BROKER] Triage Agent  │  │ sig ✓ exp ✓        │  │
│               │        registered              │  │ rev ✓ scope ✓      │  │
│  Triage       │  +1.2s [TRIAGE] Classifying... │  │ ALLOWED            │  │
│  ┌─────────┐  │  +2.1s [BROKER] Diagnosis     │  └────────────────────┘  │
│  │ ● active│  │        registered (delegated)  │  ┌────────────────────┐  │
│  │ scopes  │  │  +2.8s [DIAGNOSIS] Reading     │  │ get_billing()      │  │
│  └─────────┘  │        vitals...               │  │ patient:read:billing│ │
│               │  +3.1s [BROKER] validate →     │  │ sig ✓ exp ✓        │  │
│  Diagnosis    │        get_vitals ALLOWED       │  │ rev ✓ scope ✗      │  │
│  ┌─────────┐  │  +3.5s [BROKER] validate →     │  │ DENIED             │  │
│  │ ● active│  │        get_billing DENIED       │  └────────────────────┘  │
│  │ scopes  │  │  +4.0s [POLICY] Billing not    │                          │
│  └─────────┘  │        in ceiling               │  Audit Trail             │
│               │                               │  ┌────────────────────┐  │
│  Prescription │  [LLM output blocks]          │  │ evt1 hash:a3f8...  │  │
│  ┌─────────┐  │                               │  │ evt2 ← prev:a3f8  │  │
│  │ ○ wait  │  │                               │  │ evt3 ← prev:91b4  │  │
│  │ or 🔴rev│  │                               │  └────────────────────┘  │
│  └─────────┘  │                               │                          │
│               │                               │  Summary                 │
│  Specialist   │                               │  ┌────────────────────┐  │
│  ┌─────────┐  │                               │  │  3 passed  1 denied│  │
│  │ ✗ unreg │  │                               │  │  4 tool calls total│  │
│  └─────────┘  │                               │  └────────────────────┘  │
└───────────────┴───────────────────────────────┴──────────────────────────┘
```

### Top Bar

- **Brand:** Lock icon + "AgentAuth"
- **Story selector buttons:** Healthcare, Trading, DevOps. Clicking one:
  - Registers the story's app with the broker (visible in event stream as first event)
  - Swaps the left panel agent roster via HTMX
  - Loads that story's preset prompt buttons
- **Textarea:** Free text. User can type anything. Preset buttons populate it.
- **RUN button:** Starts the pipeline via `POST /api/run`

### Left Panel — Agents & Identity

- **Identity block:** Green (resolved user, name + ID) or amber (anonymous). Appears when identity resolution runs.
- **Agent cards:** One per agent in the active story. Each card shows:
  - Agent name
  - Status dot: gray (waiting), blue pulse (working), green (done), red (revoked)
  - SPIFFE ID (appears on registration, monospace, cyan)
  - Scope pills (blue badges, new delegated scopes flash green)
  - Status text: "Waiting", "Registered (TTL: 300s)", "Done", "REVOKED"
- **Unregistered agent card:** Shows with ✗ marker when C6 (mutual auth) is triggered

### Center Panel — Event Stream

- **SSE-driven.** Events appear in real-time, auto-scroll.
- **Format:** `+Ns [TAG] message` — monospace, color-coded by tag
- **Tags and colors:**
  - `[SYSTEM]` — gray (pipeline start/end, identity resolution)
  - `[BROKER]` — gold (app registration, agent registration, token validation)
  - `[TRIAGE]` — purple (classification, routing)
  - `[DIAGNOSIS]` / `[STRATEGY]` / `[LOG-ANALYZER]` — cyan (specialist agents working)
  - `[RESPONSE]` / `[ORDER]` / `[REMEDIATION]` — amber (action agents)
  - `[POLICY]` — orange (scope denials, revocations, policy violations)
- **LLM output blocks:** Indented, bordered, max-height with scroll. Show actual LLM response text.
- **Counters:** "N events · M broker validations" in the header

### Right Panel — Scope Enforcement

- **Enforcement cards:** One per tool call. Slide in as SSE events arrive.
  - Tool name (bold)
  - Required scope (monospace, dim)
  - Broker validation: `sig ✓ · exp ✓ · rev ✓ · scope ✓/✗`
  - Status: ALLOWED (green), DENIED (red), CHECKING... (cyan)
  - Tool result preview (if allowed, truncated)
  - For denials: enforcement type (HARD DENY, ESCALATION, DATA BOUNDARY)
- **Audit trail section:** Appears after pipeline completes. Hash-chained events from broker.
- **Summary card:** Appears at end. Large numbers: passed (green) / denied (red). Total tool calls, broker validations.

---

## The Three Stories

### Story 1: Healthcare — Patient Triage

**App ceiling** (registered with broker when user clicks "Healthcare"):
```
patient:read:intake  patient:read:vitals  patient:read:history
patient:write:prescription  patient:read:referral
```

Note: `patient:read:billing` is NOT in the ceiling. It can never be obtained regardless of what the LLM decides.

**Agents:**

| Agent | Scopes | Token | Role |
|-------|--------|-------|------|
| Triage Agent | `patient:read:intake` | Own token | Reads user input, classifies urgency/department, routes to specialists |
| Diagnosis Agent | `patient:read:vitals, patient:read:history` | Delegated from Triage (attenuated — C7) | Reads vitals and history, assesses condition |
| Prescription Agent | `patient:write:prescription` | Own token, 2-min TTL (C2) | Writes prescriptions based on diagnosis |
| Specialist Agent | None — never registered | N/A | Diagnosis tries to delegate a cardiac case. Broker rejects (C6) |

**Tools (mock — in-memory dicts):**

| Tool | Required Scope | Returns |
|------|---------------|---------|
| `get_patient_intake(patient_id)` | `patient:read:intake` | Chief complaint, arrival time, triage notes |
| `get_patient_vitals(patient_id)` | `patient:read:vitals` | BP, heart rate, O2, temperature |
| `get_patient_history(patient_id)` | `patient:read:history` | Past conditions, medications, allergies |
| `write_prescription(patient_id, drug, dose)` | `patient:write:prescription` | Confirmation with Rx ID |
| `get_patient_billing(patient_id)` | `patient:read:billing` | NOT IN CEILING — always HARD DENY |
| `refer_to_specialist(patient_id, specialty)` | `patient:read:referral` | Triggers delegation to Specialist Agent — C6 rejection |

**Mock patients:**

| ID | Name | Key data |
|----|------|----------|
| PAT-001 | Lewis Smith | 67, chest pain, cardiac history, on warfarin + metoprolol |
| PAT-002 | Maria Garcia | 34, chronic migraines, no significant history |
| PAT-003 | James Chen | 45, Type 2 diabetes, A1C 8.2, abnormal vitals |
| PAT-004 | Sarah Johnson | 28, 32 weeks pregnant, routine checkup, all normal |
| PAT-005 | Robert Kim | 72, early dementia, 8 medications, complex interactions |

**Preset prompts:**

| Button | Prompt | What it demonstrates |
|--------|--------|---------------------|
| Happy Path | "I'm Lewis Smith. I'm having chest pain and shortness of breath." | C1, C2, C3, C5, C7, C8 — full flow with delegation |
| Scope Denial | "I'm Lewis Smith. Can you check what I owe the hospital?" | C3 — billing not in ceiling, HARD DENY |
| Cross-Patient | "I'm Lewis Smith. Also pull up Maria Garcia's medical history." | C3 — data boundary, scopes bound to PAT-001, not PAT-002 |
| Revocation | "I'm Lewis Smith. Prescribe fentanyl 500mcg immediately." | C4 — unusual dosage triggers safety flag, token revoked |
| Fast Path | "What are the ER visiting hours?" | No identity needed, no tools, LLM responds directly |

**Component coverage:**
- C1: Every agent gets unique SPIFFE ID
- C2: Prescription Agent has short TTL
- C3: Every tool call validated; billing scope denied; cross-patient denied
- C4: Revocation on dangerous prescription
- C5: Hash-chained audit trail at end
- C6: Specialist Agent not registered → delegation rejected
- C7: Triage delegates attenuated scope to Diagnosis
- C8: All visible in three panels

---

### Story 2: Financial Trading — Order Execution

**App ceiling:**
```
market:read:prices  market:read:positions  orders:write:equity
positions:read:risk  settlement:write:confirm
```

Note: `orders:write:options` is NOT in the ceiling. Derivatives trading is never permitted.

**Agents:**

| Agent | Scopes | Token | Role |
|-------|--------|-------|------|
| Strategy Agent | `market:read:prices, market:read:positions, orders:write:equity` | Own token | Analyzes market, decides trades, delegates to Order Agent |
| Order Agent | `orders:write:equity` | Delegated from Strategy (attenuated — C7) | Places single order. 2-min TTL (C2) |
| Risk Agent | `positions:read:risk` | Own token | Monitors exposure. Can trigger revocation of Order Agent (C4) |
| Settlement Agent | `settlement:write:confirm` | Own token | Confirms trade settlement |
| Hedging Agent | None — never registered | N/A | Strategy tries to delegate for hedging. Broker rejects (C6) |

**Tools (mock + one real API):**

| Tool | Required Scope | Returns |
|------|---------------|---------|
| `get_market_price(symbol)` | `market:read:prices` | **Real API call** — live stock price (free endpoint) |
| `get_positions(trader_id)` | `market:read:positions` | Current holdings, P&L, exposure |
| `place_order(symbol, qty, side)` | `orders:write:equity` | Order confirmation with order ID |
| `place_options_order(symbol, type, strike, expiry)` | `orders:write:options` | NOT IN CEILING — always HARD DENY |
| `check_risk(trader_id)` | `positions:read:risk` | VaR, daily exposure %, limit remaining |
| `confirm_settlement(order_id)` | `settlement:write:confirm` | T+1 settlement confirmation |

**Mock traders:**

| ID | Name | Key data |
|----|------|----------|
| TRD-001 | Alex Rivera | Equity trader, $500K limit, 60% utilized, long AAPL/MSFT |
| TRD-002 | Priya Patel | Senior trader, $2M limit, diversified, conservative |
| TRD-003 | Marcus Webb | Junior trader, $100K limit, 92% utilized — almost at cap |
| TRD-004 | Sofia Tanaka | Options specialist — but ceiling only covers equity |
| TRD-005 | David Okafor | Risk manager, read-only access, no trading authority |

**Preset prompts:**

| Button | Prompt | What it demonstrates |
|--------|--------|---------------------|
| Happy Path | "I'm Alex Rivera. Buy 500 shares of AAPL at market." | C1, C2, C3, C5, C7, C8 — full flow with real price, delegation |
| Scope Denial | "I'm Sofia Tanaka. Buy 10 TSLA call options expiring next month." | C3 — options not in ceiling, HARD DENY |
| Cross-Trader | "I'm Marcus Webb. Show me Alex Rivera's positions." | C3 — data boundary, scopes bound to TRD-003, not TRD-001 |
| Revocation | "I'm Marcus Webb. Buy $95,000 of NVDA." | C4 — pushes over $100K limit, Risk Agent revokes Order Agent |
| Fast Path | "What's the current price of AAPL?" | No identity needed, price tool still works (read-only, not user-bound) |

**Component coverage:**
- C1: Every agent gets unique SPIFFE ID
- C2: Order Agent has 2-min TTL
- C3: Every tool call validated; options denied; cross-trader denied
- C4: Risk Agent triggers revocation when limit breached
- C5: Hash-chained audit trail — SEC-ready
- C6: Hedging Agent not registered → delegation rejected
- C7: Strategy delegates attenuated scope to Order Agent
- C8: Trading floor dashboard — all live

---

### Story 3: DevOps — Incident Response

**App ceiling:**
```
logs:read:payment-api  infra:read:status  infra:write:restart
notifications:write:slack  audit:read:events
```

Note: `infra:write:scale` is NOT in the ceiling. Restarting is permitted; scaling is not.

**Agents:**

| Agent | Scopes | Token | Role |
|-------|--------|-------|------|
| Triage Agent | `logs:read:payment-api, infra:read:status` | Own token | Reads alert, classifies severity, routes to specialists |
| Log Analyzer Agent | `logs:read:payment-api` | Delegated from Triage (attenuated — C7, no infra status) | Searches logs for root cause |
| Remediation Agent | `infra:write:restart` | Own token, 5-min TTL (C2) | Restarts the failing service |
| Notification Agent | `notifications:write:slack` | Own token | Sends incident updates |
| Compliance Agent | None — never registered | N/A | Triage tries to delegate for data exposure check. Rejected (C6) |

**Tools (mock):**

| Tool | Required Scope | Returns |
|------|---------------|---------|
| `query_logs(service, timerange)` | `logs:read:payment-api` | Recent log entries with errors, stack traces |
| `get_service_status(service)` | `infra:read:status` | Health, uptime, error rate, replica count |
| `restart_service(service, cluster)` | `infra:write:restart` | Restart confirmation with new PID |
| `scale_service(service, replicas)` | `infra:write:scale` | NOT IN CEILING — always HARD DENY |
| `send_slack(channel, message)` | `notifications:write:slack` | Message delivery confirmation |
| `query_audit(timerange)` | `audit:read:events` | Broker audit events (hash-chained) |

**Mock team members:**

| ID | Name | Key data |
|----|------|----------|
| ENG-001 | Jordan Lee | On-call SRE, full incident response access |
| ENG-002 | Casey Miller | Backend dev, read-only log access |
| ENG-003 | Taylor Nguyen | Platform lead, can authorize escalations |
| ENG-004 | Sam Brooks | Intern, no production access at all |
| ENG-005 | Morgan Chen | Security analyst, audit access only |

**Preset prompts:**

| Button | Prompt | What it demonstrates |
|--------|--------|---------------------|
| Happy Path | "I'm Jordan Lee. Payment-api is returning 500s in prod-east. Investigate and fix." | C1, C2, C3, C5, C7, C8 — full incident response |
| Scope Denial | "I'm Jordan Lee. Also scale payment-api to 10 replicas." | C3 — scale not in ceiling, HARD DENY |
| Wrong Service | "I'm Casey Miller. Pull logs from auth-service." | C3 — only `logs:read:payment-api` in ceiling |
| Revocation | "I'm Jordan Lee. Restart all services in all clusters." | C4 — overly broad restart triggers safety flag → revoke |
| No Access | "I'm Sam Brooks. What's happening with the outage?" | Intern not authorized → LLM says no access |

**Component coverage:**
- C1: Every agent gets unique SPIFFE ID
- C2: Remediation Agent has 5-min TTL
- C3: Every tool call validated; scale denied; wrong-service denied
- C4: Revocation on overly broad restart
- C5: Hash-chained audit trail — postmortem ready
- C6: Compliance Agent not registered → delegation rejected
- C7: Triage delegates attenuated scope to Log Analyzer
- C8: Incident command dashboard — all live

---

## Identity Resolution & Data Boundary Enforcement

Identity resolution uses the same pattern as the old `agentauth-app`: the LLM never decides access. The broker does.

### How it works

1. User types a prompt mentioning a name (e.g., "I'm Lewis Smith")
2. App looks up the name in the active story's mock user table (deterministic, before LLM runs)
3. **Found →** Identity resolved (green block in left panel). Agent scopes narrowed to that user's ID at registration time:
   - Base scope: `patient:read:vitals`
   - Narrowed scope: `patient:read:vitals:PAT-001`
   - The agent's token only works for PAT-001's data
4. **Not found →** Identity block shows amber (anonymous). The LLM still runs. Agents still get tools. But:
   - Tools that are `user_bound` require a user ID in the scope (e.g., `patient:read:vitals:PAT-???`)
   - The agent has no user-narrowed scope → broker denies the tool call
   - Enforcement card shows: DENIED — scope `patient:read:vitals:PAT-???` not in token
   - The LLM sees the denial in the tool response and tells the user it can't access their data
   - **The broker said no, not the LLM.** The LLM just reports what happened.
5. **General requests (no user data needed)** → Tools that aren't user-bound still work. "What are visiting hours?" / "What's the price of AAPL?" → LLM responds directly or uses non-bound tools.
6. **Cross-user access →** User is authenticated as Lewis Smith (PAT-001). LLM tries to call `get_patient_history(patient_id="PAT-002")` for Maria Garcia. The broker validates: does the token have `patient:read:history:PAT-002`? No — it has `patient:read:history:PAT-001`. **DENIED.** Enforcement card shows DATA BOUNDARY DENIED. The LLM sees the denial and reports it.

### Key principle

The LLM always tries. The tools are available. The agent calls whatever tool it decides to call. **The broker is the enforcement layer, not the prompt.** A prompt injection that tricks the LLM into calling the wrong tool still fails because the token doesn't have the scope.

This is the same pattern as the old app's `_enforce_tool_call()` — runtime scope narrowing with customer-bound tools:

```python
# Tool requires patient:read:vitals
# Agent token has patient:read:vitals:PAT-001
# Tool call has patient_id="PAT-002"
# Broker checks: does token have patient:read:vitals:PAT-002? No. DENIED.
```

### Tool definition pattern

Each tool has a `user_bound` flag:

| user_bound | Behavior |
|------------|----------|
| `False` | Scope checked as-is (e.g., `market:read:prices` — anyone can read prices) |
| `True` | Scope narrowed with user ID at validation time (e.g., `patient:read:vitals` → `patient:read:vitals:PAT-001`) |

Non-bound tools work for anonymous users. Bound tools only work when identity is resolved and the scope matches the authenticated user's ID.

---

## App Registration Flow

Each story has its own app registration with the broker. Registration happens visibly when the user clicks a story selector button:

1. User clicks "Healthcare"
2. `POST /register/healthcare` → app registers `healthcare-app` with the healthcare ceiling
3. Event stream shows: `[BROKER] App registered: healthcare-app → ceiling: patient:read:intake, patient:read:vitals, ...`
4. Left panel swaps (HTMX) to show healthcare agent cards
5. Preset prompt buttons update to healthcare presets
6. Textarea cleared, ready for input

This makes app registration part of the demo. The user sees that the ceiling is set BEFORE any agent runs. The ceiling is the law — set by the operator, enforced by the broker, invisible to the LLM.

Switching stories re-registers with a different ceiling. The broker replaces the app's ceiling.

---

## SSE Event Flow

One SSE endpoint: `GET /api/stream/{run_id}`. The pipeline yields events as dicts. The JS handler routes each event type to the correct panel updates.

**Event types and panel mapping:**

| Event Type | Center (Stream) | Left (Agents) | Right (Enforcement) |
|------------|----------------|---------------|---------------------|
| `status` | System message | — | — |
| `app_registered` | Broker message: ceiling shown | — | — |
| `identity_resolved` | System message | Identity block → green | — |
| `identity_anonymous` | System message | Identity block → amber | — |
| `identity_not_found` | System message | Identity block → red "not in system" | — |
| `agent_registered` | Broker message | Card → blue (working), SPIFFE + scopes shown | — |
| `agent_working` | Agent-tagged message | Card status text updates | — |
| `agent_result` | LLM output block | Card → green (done) | — |
| `tool_call` | Response-tagged message | — | New enforcement card (CHECKING...) |
| `broker_validation` | Broker message | — | Card updates with sig/exp/rev/scope checks |
| `tool_allowed` | Broker message | — | Card → green (ALLOWED) + result preview |
| `tool_scope_denied` | Policy message | — | Card → red (DENIED) + reason |
| `tool_data_denied` | Policy message | — | Card → red (DATA BOUNDARY DENIED) |
| `delegation` | Broker message | Target card gets new scope pills (flash green) | — |
| `delegation_rejected` | Policy message | Unregistered agent card shows ✗ | Card → red (TARGET NOT REGISTERED) |
| `revocation` | Broker message | Card → red (REVOKED) | — |
| `post_revocation_check` | Broker message | — | Card → red (REVOCATION CONFIRMED) |
| `audit_trail` | — | — | Audit section appears with hash-chained events |
| `done` | System message | — | Summary card appears |

---

## Pipeline Execution

When the user hits RUN:

```
Phase 1: Identity Resolution (deterministic, before LLM)
  → Look up name in mock user table
  → Emit identity_resolved / identity_anonymous / identity_not_found

Phase 2: Triage (LLM call)
  → Triage Agent registered with broker (visible)
  → LLM classifies: urgency, department, which specialists needed
  → Emit agent_registered, agent_working, agent_result

Phase 3: Route Selection (deterministic)
  → Based on triage output, determine which agents to invoke
  → Determine if tools are needed (fast path = no tools)

Phase 4: Specialist Agents (LLM calls with tool loops)
  → Register each specialist (visible — scope, SPIFFE ID, TTL)
  → Delegation if applicable (visible — scope attenuation)
  → Tool-calling loop:
     → LLM decides which tool to call
     → Before execution: broker validates token (visible — enforcement card)
     → ALLOWED → tool executes, result fed back to LLM
     → DENIED → enforcement card shows reason, agent blocked
  → Unregistered agent delegation attempt → C6 rejection (visible)

Phase 5: Safety Checks (deterministic)
  → If dangerous action detected (unusual dosage, over-limit trade, broad restart):
     → Revoke agent token (visible — card turns red)
     → Post-revocation verification: validate dead token (visible — confirmed dead)

Phase 6: Cleanup
  → Fetch broker audit trail (visible — hash-chained events)
  → Summary card: passed / denied counts
  → Emit done
```

---

## File Structure

```
examples/demo-app/
├── pyproject.toml              # Demo app deps (fastapi, jinja2, httpx, openai/anthropic)
├── app.py                      # FastAPI entry point, startup, story registration
├── pipeline.py                 # Pipeline runner — identity → triage → route → specialists
├── agents.py                   # LLM agent wrapper — register, tool loop, delegation
├── stories/
│   ├── __init__.py
│   ├── healthcare.py           # Healthcare ceiling, agents, tools, mock patients
│   ├── trading.py              # Trading ceiling, agents, tools, mock traders
│   └── devops.py               # DevOps ceiling, agents, tools, mock engineers
├── tools/
│   ├── __init__.py
│   ├── definitions.py          # Tool registry — name, required scope, user-bound flag
│   ├── executor.py             # Mock tool execution (dict lookups, file writes)
│   └── stock_api.py            # Real stock price API call (trading story)
├── enforcement.py              # Broker-centric tool-call validation
├── identity.py                 # Identity resolution against mock user tables
├── static/
│   └── style.css               # Dark theme (inherited from agentauth-app)
└── templates/
    ├── app.html                # Single-page layout: top bar + three panels
    └── partials/
        ├── agent_cards/
        │   ├── healthcare.html # Agent card roster for healthcare story
        │   ├── trading.html    # Agent card roster for trading story
        │   └── devops.html     # Agent card roster for devops story
        ├── identity.html       # Identity resolution block
        ├── presets.html        # Preset prompt buttons (per story)
        └── audit.html          # Audit trail section
```

---

## Design Language

Inherited from `agentauth-app` `app/web/`:

```css
--bg: #0c0e14;           /* Deep black-blue */
--panel: #111318;         /* Panel background */
--card: #181b24;          /* Card background */
--border: #232735;        /* Subtle borders */
--text: #e2e8f0;          /* Primary text */
--text-dim: #7a8194;      /* Secondary text */
--accent: #3b82f6;        /* Blue accent (active agents) */
--green: #10b981;         /* Allowed, resolved, done */
--red: #ef4444;           /* Denied, revoked */
--orange: #f59e0b;        /* Policy, warnings */
--purple: #a78bfa;        /* Triage events */
--cyan: #06b6d4;          /* Specialist events, SPIFFE IDs */
--gold: #eab308;          /* Broker events */
--mono: 'SF Mono', 'Fira Code', monospace;
```

- Dark theme throughout
- Monospace for all technical content (SPIFFE IDs, scopes, hashes)
- Sans-serif for labels and messages
- Agent status dots with pulse animation when working
- Scope pills flash green when newly delegated
- Enforcement cards animate in (slide/fade)
- 8px border radius, 1px borders, clean and dense

---

## What This Does NOT Include

- No user authentication on the demo app itself — localhost only
- No persistent storage — in-memory, resets on restart
- No HITL/OIDC/enterprise features
- No provider abstraction beyond OpenAI/Anthropic auto-detection
- No WebSocket — SSE is sufficient for server→client streaming
- No React/Vue/Svelte — vanilla JS + HTMX
- No real databases — mock data in Python dicts
- No CI integration — this is an example app, not a production service

---

## Startup Flow

```bash
# 1. Start the broker
/broker up

# 2. Run the demo
cd examples/demo-app
OPENAI_API_KEY="sk-..." AA_ADMIN_SECRET="live-test-secret-32bytes-long-ok" uv run uvicorn app:app --reload

# 3. Open http://localhost:8000
# 4. Click a story button → app registers with broker (visible in stream)
# 5. Type a prompt or click a preset → hit RUN
# 6. Watch the credential lifecycle unfold across all three panels
```

---

## Supporting Documents

- **8x8 component scenarios:** `.plans/designs/2026-04-01-eight-by-eight-scenarios.md`
- **Why traditional IAM fails:** `.plans/designs/2026-04-01-why-traditional-iam-fails.md`
- **Original design (SIMPLE-DESIGN.md):** `.plans/designs/SIMPLE-DESIGN.md`
- **Old app reference:** `~/proj/agentauth-app/app/web/` (three-panel layout, SSE, enforcement cards)
- **API source of truth:** `~/proj/agentauth-core/docs/api.md`
