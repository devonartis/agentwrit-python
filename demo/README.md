<h1 align="center">MedAssist AI — the healthcare walkthrough</h1>

<p align="center">
  A working FastAPI app that shows every AgentWrit capability against a live broker —<br>
  dynamic agents, per-patient scope isolation, cross-patient denial, delegation, renewal, release, and a tamper-evident audit trail.
</p>

<p align="center">
  <a href="#what-it-is">What it is</a> ·
  <a href="#why-it-exists">Why it exists</a> ·
  <a href="#what-youll-see">What you'll see</a> ·
  <a href="#run-it">Run it</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#where-the-code-lives">Code map</a> ·
  <a href="#further-reading">More</a>
</p>

---

## What it is

MedAssist AI is a small clinical-assistant app. You type a patient ID and a plain-language question. An LLM decides which tools to call (records, labs, billing, prescriptions). The app spawns broker-backed agents on demand, each scoped to **one patient and one category of work**, and every step shows up in a live execution trace — scope checks, denials, delegations, renewals, release.

If you've ever wondered *"what does short-lived, task-scoped, per-user credentialing actually look like in a real app?"* — this is that app.

## Why it exists

Reading about ephemeral credentials is one thing. Watching three agents get spawned, one of them get denied mid-request because it asked about the wrong patient, and then seeing the whole chain die when the encounter ends — that's what makes the pattern stick.

We built MedAssist AI because:

- **Beginners need a story.** "Scoped JWTs" is abstract. "The clinical agent can only read Patient 1042's records, and when it tries Patient 2187 the broker says no" is concrete.
- **Reviewers need evidence.** The audit tab shows a hash-chained ledger of every broker event, which is what a security reviewer wants to see before approving production use.
- **Contributors need a reference.** Every SDK feature — `create_agent`, `validate`, `delegate`, `renew`, `release`, `scope_is_subset` — is wired in here, used the way it's meant to be used.

## What you'll see

| Capability | What the demo does |
|-----------|--------------------|
| **Dynamic agent creation** | Agents spawn as the LLM picks tools. No pre-allocated pool. |
| **Per-patient scope isolation** | Each agent's scope contains one patient ID and nothing else. |
| **Cross-patient denial** | Ask about another patient mid-encounter. The scope check fails. The trace shows `scope_denied`. |
| **Delegation with attenuation** | The clinical agent delegates `write:prescriptions:{patient}` to the prescription agent. The broker refuses to widen. |
| **Token lifecycle** | `renew()` issues a fresh token under the same SPIFFE identity. `release()` kills the token immediately. |
| **Audit trail** | A dedicated tab shows every broker event in a hash chain that can't be retroactively altered. |

The trace panel in the UI is the point. Every capability surfaces as a line in the trace so you can read the whole story of one request.

## Run it

### Option A — Docker (recommended)

One command, no Python setup:

```bash
AGENTWRIT_ADMIN_SECRET="your-secret" \
LLM_API_KEY="your-llm-key" \
docker compose up -d broker medassist
```

Open [http://localhost:5000](http://localhost:5000). The demo auto-registers itself with the broker on startup.

You need an OpenAI-compatible LLM endpoint. If you're not using OpenAI, set `LLM_BASE_URL` and `LLM_MODEL` in your shell before `docker compose up` — e.g. a local vLLM or llama.cpp server.

### Option B — From source

For when you want to edit the code:

```bash
# 1. Start the broker
docker compose up -d broker

# 2. Register the demo app (one time — writes client_id/client_secret)
export AGENTWRIT_ADMIN_SECRET="your-admin-secret"
uv run python demo/setup.py

# 3. Configure demo/.env
cp demo/.env.example demo/.env
#   then fill in AGENTWRIT_CLIENT_ID, AGENTWRIT_CLIENT_SECRET, LLM_BASE_URL, LLM_API_KEY, LLM_MODEL

# 4. Run it
uv run uvicorn demo.app:app --reload --port 5000
```

### What to try first

1. Pick a patient from the dropdown.
2. Ask something simple: *"What are this patient's recent labs?"* Watch agents spawn, watch each tool check scope, watch the final response render.
3. Ask a crossing question: *"And show me Patient 2187's records too."* Watch the scope check fail. Read the `scope_denied` line in the trace.
4. Open the Audit tab. Every event is there, hash-chained.

## How it works

The demo is built on one rule: **the app never trusts the LLM for security.** The LLM picks tools. The broker decides what credentials exist. The app enforces tool access against those credentials with `scope_is_subset()` before every call.

```
User types a request
      ↓
FastAPI receives it
      ↓
LLM chooses a tool (records / labs / billing / prescription)
      ↓
App asks: "Do I have an agent for this category yet?"
      ↓ no                           ↓ yes
Broker creates one,             Reuse it
scoped to this patient          
      ↓
App checks: scope_is_subset(tool-requires, agent-holds)?
      ↓ yes                         ↓ no
Run the tool                    Emit scope_denied, tell LLM "access denied"
      ↓
Return result to LLM. Repeat until LLM is done.
      ↓
App releases every agent. Tokens are dead.
```

Every branch of this flow appears in the execution trace. The trace is the documentation.

For the full walkthrough — sequence diagrams, how delegation flows from the clinical agent to the prescription agent, and what each UI panel shows — read the [Beginner's Guide](BEGINNERS_GUIDE.md). For a scripted live presentation, read the [Presenter's Guide](PRESENTERS_GUIDE.md).

## Where the code lives

| Piece | File |
|-------|------|
| FastAPI entry point | [`app.py`](app.py) |
| Env config (broker + LLM) | [`config.py`](config.py) |
| Main API loop (LLM, agent spawning, trace) | [`routes/api.py`](routes/api.py) |
| Page routes (encounter, audit, operator) | [`routes/pages.py`](routes/pages.py) |
| Tool definitions + scope templates | [`pipeline/tools.py`](pipeline/tools.py) |
| Mock patient and formulary data | [`data/`](data/) |
| Frontend (trace, markdown render) | [`static/app.js`](static/app.js), [`static/style.css`](static/style.css) |
| One-shot app registration helper | [`setup.py`](setup.py) |

Read `routes/api.py` first. That's where the agent-creation-and-scope-check loop lives, and everything else supports it.

## Further reading

| Go here for | Link |
|-------------|------|
| Step-by-step beginner walkthrough with diagrams | [BEGINNERS_GUIDE.md](BEGINNERS_GUIDE.md) |
| Live presentation script (timing, transitions) | [PRESENTERS_GUIDE.md](PRESENTERS_GUIDE.md) |
| SDK concepts (roles, scopes, delegation) | [../docs/concepts.md](../docs/concepts.md) |
| Building real apps with the SDK | [../docs/developer-guide.md](../docs/developer-guide.md) |
| Broker API (source of truth) | [AgentWrit broker docs](https://github.com/devonartis/agentwrit/tree/main/docs) |
