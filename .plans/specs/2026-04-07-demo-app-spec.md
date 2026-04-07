# Demo App Spec — AgentAuth SDK v0.3.0

**Date:** 2026-04-07
**Branch:** create `feature/demo-app-v0.3.0` from `feature/v0.3.0-sdk-spec-rewrite`
**Reference:** `/Users/divineartis/proj/showcase-authagent/apps/dashboard/` (old v0.2.0 demo)
**Status:** Ready for implementation

---

## What This Is

A FastAPI web dashboard that demonstrates the AgentAuth Python SDK in a realistic customer support scenario. An LLM-powered pipeline processes support tickets using multiple agents, each with scoped credentials. The UI shows the full lifecycle in real-time: agent creation, scope enforcement, delegation, tool execution, and token revocation.

This is a showcase app — not a production application. It uses mock customer data and simulated tool execution. The only real systems are the AgentAuth broker and the LLM providers (OpenAI, Gemini).

---

## What Changed from v0.2.0

| v0.2.0 (old demo) | v0.3.0 (this spec) |
|---|---|
| `AgentAuthClient` | `AgentAuthApp` |
| `client.get_token(name, scope)` → string | `app.create_agent(orch_id, task_id, scope)` → `Agent` object |
| `client.revoke_token(token)` | `agent.release()` |
| `client.validate_token(token)` → dict | `validate(broker_url, token)` → `ValidateResult` |
| `client.delegate(token, to, scope)` → string | `agent.delegate(delegate_to, scope)` → `DelegatedToken` |
| `HITLApprovalRequired` exception | **Removed** — no HITL in v0.3.0 SDK |
| `ScopeCeilingError` | `AuthorizationError` |
| `requests` library | `httpx` |
| Token caching, auto-renewal | **Removed** — agents are objects, not cached strings |

---

## Architecture

```
demo/
├── app.py                          # FastAPI app, static mount, router include
├── routes.py                       # All HTTP routes (pages + HTMX + pipeline SSE)
├── pipeline/
│   ├── runner.py                   # Pipeline orchestrator — triage → knowledge → response
│   ├── agent.py                    # LLM wrapper (OpenAI + Gemini)
│   ├── tools/
│   │   ├── definitions.py          # 22 tools with scope mapping (minus HITL-gated ones)
│   │   └── executor.py             # Mock tool execution
│   └── data/
│       ├── customers.py            # Customer data loader
│       ├── customers.csv           # Mock customer records
│       ├── billing.csv             # Mock billing history
│       ├── tickets.csv             # Mock support tickets
│       └── knowledge_base.py       # KB search
├── templates/
│   ├── base.html                   # Layout with 3 tabs
│   ├── operator.html               # Broker health, launch tokens
│   ├── developer.html              # Pipeline UI with scenario presets
│   ├── security.html               # Audit trail, revocation
│   └── partials/                   # HTMX partial templates
└── static/
    └── style.css                   # Dashboard styling
```

---

## Three Tabs

### Tab 1: Operator

What it does:
- Shows broker health (`app.health()` → `HealthStatus`)
- Creates launch tokens via admin API (raw `httpx` to `/v1/admin/launch-tokens`)

SDK calls used:
- `app.health()` → displays status, version, uptime, db_connected, audit_events_count

### Tab 2: Developer

What it does:
- Text input for a support ticket (or select a scenario preset)
- Runs a 3-agent pipeline: triage → knowledge → response
- Streams events via SSE to a 3-panel UI (agents, event stream, enforcement)
- Shows agent creation, scope grants, tool calls, scope denials, and token revocation in real-time

SDK calls used:
- `app.create_agent()` — creates triage, knowledge, and response agents
- `agent.scope` — displayed in agent cards
- `agent.access_token` — used for tool execution context
- `agent.release()` — shown as token revocation event
- `validate(broker_url, token)` — post-revocation verification
- `scope_is_subset()` — client-side scope gating before tool execution
- `agent.delegate()` — when response agent delegates to a sub-agent for a specific tool

### Tab 3: Security

What it does:
- Queries audit trail via admin API (`GET /v1/audit/events`)
- Displays events in a table with agent identity, task, event type, outcome
- Provides token/agent revocation form via admin API (`POST /v1/revoke`)

SDK calls used:
- None directly — uses raw `httpx` with admin token to hit admin endpoints

---

## Pipeline Design (Developer Tab)

### Agents

| Agent | LLM Provider | Scope | Purpose |
|---|---|---|---|
| triage-agent | OpenAI (gpt-4o-mini) | `["read:data:tickets"]` | Classify ticket: priority (P1-P4), category (billing/technical/account/general) |
| knowledge-agent | Gemini (gemini-2.0-flash) | `["read:data:knowledge-base"]` | Search KB for relevant articles |
| response-agent | OpenAI (gpt-4o-mini) | Per-tool scopes | Execute tools and draft response |

### Pipeline Flow

```
1. Identity Resolution — match customer name from ticket text
2. Triage — create triage-agent, classify ticket, release agent
3. Route Selection — pick route based on priority + category
4. Knowledge Search — create knowledge-agent, search KB, release agent (conditional)
5. Response — create response-agent with tool access
6. Tool Loop — for each tool call:
   a. Look up tool's required scope
   b. Check scope_is_subset() — client-side gate
   c. If scope violation → deny and log
   d. If cross-customer access → deny and log
   e. If authorized → execute tool, return result to LLM
7. Cleanup — release all agents, verify revocation
```

### Scope Enforcement (No HITL)

The old demo used HITL for sensitive actions (delete, refund, SSN, etc.). In v0.3.0, those actions are handled differently:

- **Actions within the app's scope ceiling** → auto-approved, tool executes
- **Actions outside the ceiling** → `AuthorizationError`, pipeline logs denial
- **Cross-customer access** → client-side `scope_is_subset()` check, pipeline blocks it

There is no pause-for-human-approval flow. The scope ceiling is the hard limit.

### Delegation Demo

The old demo did not demonstrate delegation. This demo should:

When the response-agent needs to call a tool that requires a specific customer scope, it creates a sub-agent via delegation:

```python
# Response agent has broad scope
response_agent = app.create_agent(
    orch_id="pipeline",
    task_id=f"response-{task_id}",
    requested_scope=["read:data:billing", "read:data:contact", "read:data:account"],
)

# For a specific tool call, delegate narrow scope
tool_agent_token = response_agent.delegate(
    delegate_to=sub_agent.agent_id,
    scope=["read:data:billing"],  # only what the tool needs
)
```

This shows delegation in action — the response agent narrows its authority for each tool call.

### Scenario Presets

Keep from old demo (minus HITL-specific ones):

| Preset | Ticket Text | What It Demonstrates |
|---|---|---|
| Happy Path | "Check my balance and confirm last payment" | Full pipeline: triage → KB → tools → response |
| Fast Path | "What are your support hours?" | Route skips tools, direct LLM response |
| Cross-Customer Read | "Check my balance and also look up John's" | Scope gating blocks cross-customer access |
| Cross-Customer Delete | "Delete John's account" | Scope gating blocks cross-customer destructive action |
| Scope Escalation | "Disable my account and revoke their access" | `AuthorizationError` for scope outside ceiling |
| P1 Escalation | "COMPLETE OUTAGE — escalate to CTO" | High-priority routing, escalation tool |

Remove presets: hitl_delete, hitl_refund, hitl_password, hitl_ssn, hitl_gdpr, hitl_denied (all HITL-dependent).

---

## Tools

Keep all 22 tools from old demo. Remove the HITL-gating concept — all tools either execute (within ceiling) or fail (outside ceiling). The tool definitions, executor, and data files (customers.csv, billing.csv, tickets.csv, knowledge_base.py) are copied directly from the old demo — they have no SDK dependency.

---

## Data Files

Copy directly from old demo — no changes needed:
- `pipeline/data/customers.csv` — 3-5 mock customers with name, email, phone, balance, SSN, etc.
- `pipeline/data/billing.csv` — billing history per customer
- `pipeline/data/tickets.csv` — open/closed support tickets
- `pipeline/data/knowledge_base.py` — KB article search

---

## Frontend

Keep the same structure from old demo:
- `base.html` — layout with 3 tabs (Operator, Developer, Security)
- `developer.html` — 3-panel pipeline UI (agents, event stream, enforcement)
- HTMX for partial updates on Operator and Security tabs
- SSE for real-time pipeline streaming on Developer tab
- `style.css` — dashboard styling

Remove:
- `partials/hitl_approval.html` — no HITL
- All HITL-related JavaScript (showHitlCard, hitlRespond)
- HITL preset buttons

---

## Dependencies

```
fastapi
uvicorn
jinja2
python-multipart
python-dotenv
httpx
openai
google-genai
agentauth  (this SDK, installed as editable: uv pip install -e .)
```

---

## Environment Variables

```bash
AGENTAUTH_BROKER_URL=http://localhost:8080
AGENTAUTH_CLIENT_ID=<from broker registration>
AGENTAUTH_CLIENT_SECRET=<from broker registration>
AGENTAUTH_ADMIN_SECRET=<broker admin secret>
OPENAI_API_KEY=<for gpt-4o-mini>
GEMINI_API_KEY=<for gemini-2.0-flash>
```

---

## How to Run

```bash
# 1. Start broker
./broker/scripts/stack_up.sh

# 2. Install demo deps
uv pip install -e ".[demo]"

# 3. Set env vars (or use .env file)
export AGENTAUTH_BROKER_URL=http://localhost:8080
# ... etc

# 4. Run
uv run uvicorn demo.app:app --reload --port 5000
```

---

## Implementation Order

1. **Scaffold** — create `demo/` directory structure, `app.py`, `routes.py`
2. **Data layer** — copy CSV files and data loaders from old demo (no changes)
3. **Tools** — copy tool definitions and executor from old demo (remove HITL scope references)
4. **LLM agent** — copy `agent.py` from old demo (no changes — pure LLM, no SDK coupling)
5. **Pipeline runner** — rewrite using v0.3.0 SDK:
   - `app.create_agent()` instead of `client.get_token()`
   - `agent.release()` instead of `client.revoke_token()`
   - Remove all HITL code paths
   - Add delegation for per-tool scope narrowing
   - `scope_is_subset()` for client-side gating
6. **Routes** — rewrite using v0.3.0 SDK:
   - `AgentAuthApp` instead of `AgentAuthClient`
   - `app.health()` for operator tab
   - Remove HITL approval/denial routes
   - Keep admin token caching for operator/security tabs
7. **Templates** — copy from old demo, remove HITL elements
8. **Static** — copy CSS from old demo
9. **Test** — run against live broker with all scenario presets
