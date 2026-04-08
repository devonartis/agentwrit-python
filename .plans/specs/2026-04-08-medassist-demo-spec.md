# MedAssist AI — AgentAuth Healthcare Demo

**Date:** 2026-04-08
**Branch:** `feature/demo-app-v0.3.0`
**Status:** Ready for implementation

---

## PRD: Product Requirements Document

### Problem Statement

Healthcare AI systems deploy multiple agents to process a patient encounter: reviewing medical history, ordering prescriptions, filing insurance claims. Each agent touches different categories of protected health information (PHI). Regulatory frameworks (HIPAA) mandate that each system component accesses only the minimum data necessary for its function — a billing system has no business reading clinical notes, and a prescription writer has no reason to see insurance claims.

Today, most multi-agent systems give every agent the same long-lived API key with broad access. A compromised billing agent can read every patient's medical records. A leaked prescription token can write prescriptions for any patient indefinitely. There is no audit trail showing which agent accessed which data, and no way to revoke one agent's access without rotating credentials for all of them.

AgentAuth solves this by giving each agent a short-lived, task-scoped credential tied to a specific patient and a specific action. This demo makes that value proposition viscerally obvious.

### Target Audience

- **Developers evaluating AgentAuth** — need to see real SDK code, not slides
- **Security/compliance leads** — need to see scope isolation, audit trails, revocation
- **Technical decision makers** — need the "why not just use API keys" answer in 60 seconds

### Success Criteria

The demo is successful when a viewer can:
1. Watch 3 agents process a patient encounter with different permissions
2. See a billing agent get blocked from reading medical records (scope isolation)
3. See a clinical agent delegate narrow prescription authority to a sub-agent
4. See an emergency revocation kill all agents instantly
5. Inspect the audit trail showing every access, denial, and delegation
6. Understand why this is better than shared API keys — without being told

---

### User Stories

**US-1: Run a Patient Encounter**
As a demo viewer, I select a patient and click "Process Encounter" so I can watch the multi-agent pipeline process the visit in real-time.

**US-2: See Scope Isolation**
As a demo viewer, I watch the billing agent get blocked from reading medical records, so I understand that each agent can only access the data it was authorized for.

**US-3: See Delegation**
As a demo viewer, I watch the clinical agent delegate narrow prescription-writing authority to a prescription agent for exactly one patient, so I understand how authority flows and narrows.

**US-4: See Cross-Patient Isolation**
As a demo viewer, I watch an agent that has access to Patient A get blocked from accessing Patient B's data, so I understand per-patient scoping.

**US-5: See Emergency Revocation**
As a demo viewer, I click "Simulate Breach" and watch all agents for a patient get revoked instantly, with subsequent requests returning 403.

**US-6: Inspect Audit Trail**
As a demo viewer, I browse the audit trail and see every agent creation, scope check, delegation, denial, and revocation — with hash-chained integrity.

**US-7: See Token Lifecycle**
As a demo viewer, I watch agent tokens being created with TTL countdowns, see a long-running agent renew its token, and see agents release tokens when done.

---

## Technical Specification

### Architecture

```
demo/
├── app.py                      # FastAPI app, static mount, router include
├── config.py                   # Environment config (broker, LLM keys)
├── routes/
│   ├── pages.py                # Page routes (encounter, audit, operator)
│   └── api.py                  # HTMX + SSE endpoints (pipeline, revocation)
├── pipeline/
│   ├── runner.py               # Encounter orchestrator (creates agents, runs pipeline)
│   ├── agents/
│   │   ├── clinical.py         # Clinical review agent (LLM-powered)
│   │   ├── prescription.py     # Prescription agent (LLM-powered, delegated)
│   │   └── billing.py          # Billing agent (LLM-powered, isolated)
│   └── tools.py                # Mock healthcare tools (read records, write Rx, etc.)
├── data/
│   ├── patients.py             # Patient data loader
│   ├── patients.json           # 4-5 mock patients with records, billing, prescriptions
│   └── formulary.json          # Drug formulary for prescription checks
├── templates/
│   ├── base.html               # Layout with navigation
│   ├── encounter.html          # Main encounter view (agent cards + event stream)
│   ├── audit.html              # Audit trail browser
│   └── partials/               # HTMX fragments (agent card, event row, etc.)
└── static/
    ├── style.css               # Dark theme, medical dashboard aesthetic
    └── app.js                  # SSE handler, TTL countdown timers
```

### Scope Model

Scopes follow AgentAuth's `action:resource:identifier` format. The identifier encodes the patient ID, enforcing per-patient isolation.

**Clinical scopes:**
- `read:records:{patient_id}` — read medical records (history, notes, vitals)
- `write:records:{patient_id}` — write clinical notes, update records
- `read:labs:{patient_id}` — read lab results

**Prescription scopes:**
- `write:prescriptions:{patient_id}` — write prescriptions for one patient
- `read:formulary:*` — read drug formulary (reference data, any identifier)

**Billing scopes:**
- `read:billing:{patient_id}` — read billing history, charges
- `write:billing:{patient_id}` — generate billing codes, file claims
- `read:insurance:{patient_id}` — read insurance coverage

**App scope ceiling** (registered with broker):
```
["read:records:*", "write:records:*", "read:labs:*", "write:prescriptions:*", "read:formulary:*", "read:billing:*", "write:billing:*", "read:insurance:*"]
```

Each agent gets a strict subset of the ceiling, scoped to exactly one patient.

### Agents and Their Permissions

| Agent | LLM | Scopes | Purpose |
|-------|-----|--------|---------|
| **Clinical Review** | gemma-4-26B-A4B-it (vLLM) | `read:records:{pid}`, `write:records:{pid}`, `read:labs:{pid}` | Review patient history, write clinical notes, order labs |
| **Prescription** | gemma-4-26B-A4B-it (vLLM) | `write:prescriptions:{pid}`, `read:formulary:*` | Check drug interactions, write prescriptions. Created via delegation from Clinical Agent |
| **Billing** | gemma-4-26B-A4B-it (vLLM) | `read:billing:{pid}`, `write:billing:{pid}`, `read:insurance:{pid}` | Generate billing codes (ICD-10/CPT), file insurance claims. No medical record access. |

### Pipeline Flow (Patient Encounter)

1. User selects patient and scenario preset
2. **Phase 1 — Clinical Review:** App creates clinical agent with `read:records:{pid}`, `write:records:{pid}`, `read:labs:{pid}`. LLM reviews history, writes notes.
3. **Phase 2 — Prescription (Delegated):** App creates prescription agent with `read:formulary:*`. Clinical agent delegates `write:prescriptions:{pid}` to prescription agent. LLM checks interactions, writes Rx.
4. **Phase 3 — Billing (Isolated):** App creates billing agent with `read:billing:{pid}`, `write:billing:{pid}`, `read:insurance:{pid}`. LLM attempts to access medical records — blocked by scope_is_subset. LLM generates billing codes, files claim using its authorized scopes.
5. **Phase 4 — Cleanup:** All agents call release(). App validates all tokens are dead.

### Demo Scenarios (Presets)

| Preset | Patient | What It Shows |
|--------|---------|---------------|
| Happy Path | Maria Santos (P-1042) | Full encounter: clinical review, prescription, billing. All scopes respected. |
| Billing Blocked | James Chen (P-2187) | Billing agent attempts to read medical records. scope_is_subset blocks it. |
| Cross-Patient | Maria Santos (P-1042) | Clinical agent for Patient A tries to read Patient B's records. Blocked. |
| Delegation Chain | Aisha Patel (P-3301) | Clinical delegates to prescription, prescription delegates to drug-interaction checker. Two-hop chain. |
| Emergency Revoke | Any patient | "Breach Detected" revokes all agents for the patient via admin API. |
| Token Expiry | James Chen (P-2187) | Agent created with 10s TTL. Dashboard shows countdown. After expiry, validate() confirms dead. |

### SDK Methods Exercised

Every public SDK symbol gets used:

| SDK Symbol | Where Used |
|------------|------------|
| `AgentAuthApp(broker_url, client_id, client_secret)` | App startup |
| `app.create_agent(orch_id, task_id, requested_scope)` | Create clinical, billing agents |
| `app.health()` | Operator panel, pre-flight check |
| `app.validate(token)` | Post-revocation verification |
| `agent.access_token` | Displayed in agent cards |
| `agent.agent_id` | SPIFFE identity display |
| `agent.scope` | Scope badge display + gating |
| `agent.expires_in` | TTL countdown timer |
| `agent.renew()` | Long-running clinical review |
| `agent.release()` | Cleanup after each phase |
| `agent.delegate(delegate_to, scope)` | Clinical -> Prescription delegation |
| `validate(broker_url, token)` | Token validation after release/revoke |
| `scope_is_subset(required, held)` | Client-side gating before every tool call |
| `AuthorizationError` | Caught when delegation exceeds scope |
| `ProblemResponseError.problem` | RFC 7807 error display |
| `AgentClaims` | Claims display in agent detail panel |
| `DelegatedToken` | Delegation result display |
| `ValidateResult` | Validation result display |
| `HealthStatus` | Operator panel |

### Tech Stack

- **Backend:** FastAPI + Jinja2
- **Frontend:** HTMX for partial updates, vanilla JS for dynamic UI
- **LLM:** `google/gemma-4-26B-A4B-it` via local vLLM (OpenAI-compatible API at `http://spark-3171/vllm/v1`, key `EMPTY`)
- **Styling:** Custom CSS, high-contrast dark theme
- **SDK:** agentauth (this repo, installed as editable)

### Dependencies

```
fastapi
uvicorn[standard]
jinja2
python-multipart
httpx
openai
agentauth
```

### Environment Variables

```
AGENTAUTH_BROKER_URL=http://localhost:8080
AGENTAUTH_CLIENT_ID=<from broker app registration>
AGENTAUTH_CLIENT_SECRET=<from broker app registration>
AGENTAUTH_ADMIN_SECRET=<broker admin secret, for audit/revocation panel>

# LLM — local vLLM instance (OpenAI-compatible API)
LLM_BASE_URL=http://spark-3171/vllm/v1
LLM_API_KEY=EMPTY
LLM_MODEL=google/gemma-4-26B-A4B-it
```

### How to Run

```bash
# 1. Start the broker
./broker/scripts/stack_up.sh

# 2. Register the demo app with the broker (one-time setup script)
uv run python demo/setup.py

# 3. Set environment variables
cp demo/.env.example demo/.env
# Edit demo/.env with your keys

# 4. Run the demo
uv run uvicorn demo.app:app --reload --port 5000
```
