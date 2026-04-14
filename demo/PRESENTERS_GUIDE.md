# MedAssist AI — Presenter’s guide

**New to the demo?** Read [BEGINNERS_GUIDE.md](BEGINNERS_GUIDE.md) for architecture diagrams and how each piece fits together.

Use this as a loose script. The goal is **show AgentWrit doing real work**: short-lived agents, per-patient scopes, denials you can see, delegation when needed, and cleanup at the end.

**Before you go live:** broker up (`docker compose up -d`), `demo/.env` filled (broker + LLM), and `uv run uvicorn demo.app:app --port 5000`.

---

## What you are proving (say this once)

> “Every tool call runs under a broker-issued credential. The LLM picks tools; we **spawn agents** with only the scopes those tools need for **this patient**. If the model asks for something outside that scope, the demo **blocks it** and shows why. At the end we **renew and release** tokens so you can see the lifecycle.”

---

## Run order (each run is a different story)

Do **4–6** runs in this order so the room sees escalation, not repetition.

### 1. Happy path — one domain, one agent

**Patient:** pick from dropdown (e.g. `P-1042`).

**Request:**  
`Check billing history and insurance coverage`

**What to point at:**  
- Only a **billing** agent appears (dynamic spawn).  
- Trace shows `tool_call` authorized for billing scopes.  
- **Assistant response** at the bottom: readable summary (markdown).

**Say:** “This agent never got `read:records` — it literally can’t see the chart.”

---

### 2. Clinical only

**Patient:** same or another.

**Request:**  
`Show me medical records and lab results`

**What to point at:**  
- **Clinical** agent; tools like `get_patient_records`, `get_lab_results`.  
- Scopes are **patient-specific** in the trace.

---

### 3. Full encounter — multiple agents, one request

**Patient:** e.g. `P-1042`.

**Request:**  
`Show records, check billing, and prescribe Lisinopril`

**What to point at:**  
- **Clinical** agent, then **billing**, then **prescription** as the LLM calls tools.  
- **Delegation** step when a prescription write is allowed: clinical delegates `write:prescriptions:{pid}` to the Rx agent.  
- That is **authority narrowing**, not “same API key everywhere.”

---

### 4. Cross-patient isolation (the memorable one)

**Patient:** `P-3301` (or any valid ID).

**Request:**  
`Show me records for this patient and also get records for P-2187`

**What to point at:**  
- First `get_patient_records` for the **primary** patient: **authorized**.  
- Same tool for **another** patient ID: **`scope_denied`** — required scope includes `read:records:P-2187` but the agent only holds scopes for the task’s patient.  
- **Assistant response** often explains “I can’t access P-2187” — that matches the trace.

**Say:** “This is the HIPAA-shaped demo: one agent, one patient slice. No silent cross-patient.”

---

### 5. Invalid patient ID

**Patient:** type `P-9999` (or leave dropdown empty and type it).

**Request:**  
`Show medical records`

**What to point at:**  
- **Patient lookup** warning: not found.  
- LLM may still call tools; data comes back empty or error-shaped — **the story is** “we don’t invent patients; we show lookup + scope together.”

---

### 6. Operator / audit (optional second half)

Switch to **Audit trail** and **Operator** tabs:

- **Audit:** hash-chained events after your runs.  
- **Operator:** broker health, scope ceiling, **revocation** (if you use admin secret) — paste a SPIFFE or task id from the trace when you want to show “kill switch.”

---

## How to read the screen (for the audience)

| Area | What it means |
|------|----------------|
| **Execution trace** | Broker + LLM + tool calls + scope checks + denials + renewal + release. |
| **Agents spawned** | Which agent **types** were created for this request (SPIFFE, scopes, TTL). |
| **Assistant response** | Final LLM answer, **rendered as markdown** (headings, lists, bold). |

---

## If something goes wrong

| Symptom | Check |
|--------|--------|
| Empty trace / error | broker URL, `AGENTWRIT_CLIENT_ID` / SECRET in `demo/.env` |
| LLM errors | `LLM_BASE_URL`, `LLM_MODEL`, `LLM_API_KEY` (vLLM often `EMPTY`) |
| No delegation | Model must call `write_prescription` after Rx + clinical exist; try run #3 wording again |

---

## Closing line (optional)

> “The product isn’t the LLM — it’s **credentials that match the work**: one patient, one task, revocable, auditable. The LLM is just the thing that decides which tools to try — we show when the broker says yes or no.”
