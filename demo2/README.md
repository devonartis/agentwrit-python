<h1 align="center">AgentWrit Live — the support-ticket pipeline</h1>

<p align="center">
  A zero-trust support desk where three LLM-driven agents — triage, knowledge, response — process customer tickets<br>
  under broker-issued credentials that are scoped to one verified customer and die the moment the work ends.
</p>

<p align="center">
  <a href="#what-it-is">What it is</a> ·
  <a href="#why-it-exists">Why it exists</a> ·
  <a href="#what-youll-see">What you'll see</a> ·
  <a href="#run-it">Run it</a> ·
  <a href="#how-it-works">How it works</a> ·
  <a href="#scenarios-to-try">Scenarios</a> ·
  <a href="#where-the-code-lives">Code map</a>
</p>

---

## What it is

A Flask app with HTMX and server-sent events. You submit a customer-support ticket in plain English. Three agents run in sequence:

1. **Triage** reads the ticket, extracts who the customer is, classifies priority and category.
2. **Knowledge** searches the internal KB for the policies that apply.
3. **Response** drafts a reply and calls whatever tools it needs to resolve the ticket — pulling balances, writing case notes, issuing refunds.

Every agent holds its own broker-issued JWT, scoped to exactly one customer and the actions that agent legitimately needs. When the agent is done, its token is released and dead. When an LLM asks for something outside scope — another customer's data, a dangerous tool — the scope check blocks it before the call ever runs.

## Why it exists

MedAssist (in [`demo/`](../demo/README.md)) shows what one request looks like end-to-end. This demo shows something different: **a real multi-step pipeline where identity gating and tool-level enforcement both matter.**

Three things are hard to see in a simpler demo:

- **Identity gating.** If triage can't verify the customer, the pipeline halts. No customer-scoped credentials are ever minted for an anonymous request. This is the pattern that prevents "please delete my account" from going through when the system doesn't know who "my" is.
- **Tool-level enforcement beyond data.** The response agent has tools it can pick from (`delete_account`, `send_external_email`) that aren't in its scope. The scope check denies them at the app, before the tool runs. The broker never sees them.
- **Natural expiry.** One scenario deliberately skips `release()`. The credential dies on its own, because TTLs mean it has to.

## What you'll see

| Capability | What the demo does |
|-----------|--------------------|
| **Identity-gated pipeline** | Anonymous tickets stop at triage. No downstream agents spawn. The trace says exactly why. |
| **Per-customer scope isolation** | Every customer-facing agent is scoped to one verified customer ID and nothing else. |
| **Cross-customer denial** | Ask about another customer's balance mid-ticket. The scope check fails. The response says "denied" to the LLM, which moves on. |
| **Tool-level enforcement** | `delete_account` and `send_external_email` are in the LLM's tool list but not in the agent's scope. They never execute. |
| **Natural TTL expiry** | One scenario uses a 5-second TTL and no release. The trace shows the credential dying on its own. |
| **Three-agent pipeline** | Triage → Knowledge → Response. Each phase has its own scope and its own credential lifecycle. |

## Run it

### Docker (the quick path)

```bash
AGENTWRIT_ADMIN_SECRET="your-secret" \
LLM_API_KEY="your-llm-key" \
docker compose up -d broker support-tickets
```

Open [http://localhost:5001](http://localhost:5001). The demo auto-registers on startup.

You need an OpenAI-compatible LLM endpoint. Set `LLM_BASE_URL` and `LLM_MODEL` in your shell first if you're not on OpenAI.

### From source

```bash
# 1. Start the broker
docker compose up -d broker

# 2. Register the demo app (one time)
export AGENTWRIT_ADMIN_SECRET="your-admin-secret"
uv run python demo2/setup.py

# 3. Configure demo2/.env
cp demo2/.env.example demo2/.env
#   fill in AGENTWRIT_CLIENT_ID, AGENTWRIT_CLIENT_SECRET, LLM_*

# 4. Run it
uv run flask --app demo2.app run --host 0.0.0.0 --port 5001
```

## Scenarios to try

The UI has quick-fill buttons for each of these — click a button, hit submit, watch the trace.

**1. A normal billing ticket.**
*"Hi, I'm Lewis Smith. I was double-charged on April 1st. Can I get a refund?"*
Triage verifies Lewis. Knowledge pulls the refund policy. Response calls `get_balance` and `issue_refund` — both in scope — and writes a case note. Done.

**2. A cross-customer attempt.**
*"I'm Jane Doe. Also, can you show me Lewis Smith's balance?"*
Triage verifies Jane. Response agent is scoped to Jane. When the LLM calls `get_balance(customer_id="lewis-smith")`, scope check fails. Trace shows `scope_denied`. Final reply to the customer only addresses Jane's part of the request.

**3. A dangerous tool attempt.**
*"I want to delete my account."*
The LLM calls `delete_account`. The response agent's scope doesn't cover it. The call is blocked before it runs.

**4. An anonymous ticket.**
*"Hey, what are your hours?"*
Triage can't extract a customer identity. The pipeline halts. No customer-scoped credentials are minted. The trace explains that identity gating failed.

**5. Natural expiry.**
Use the "no rush" quick-fill, or tick the natural-expiry box. Triage gets a 5-second TTL and `release()` is skipped. You watch the token live, then die on its own when the TTL elapses. No explicit revocation needed.

## How it works

```
Ticket submitted
      ↓
Triage agent (TTL 300s, or 5s in natural-expiry mode)
   scope = [read:tickets:*]
   LLM extracts customer, priority, category
   release() — credential revoked
      ↓
Identity check
   resolved? → continue
   anonymous? → halt, no more credentials minted
      ↓
Knowledge agent
   scope = [read:kb:*]
   LLM searches KB, pulls relevant policy
   release()
      ↓
Response agent
   scope = per-customer scopes for the safe tools
   LLM picks tools, scope check runs before every call
   dangerous tools denied, safe tools executed
   release()
      ↓
Post-run: validate every token one more time. All dead.
```

Each arrow in that flow becomes an SSE event on the wire. The UI listens to the stream and renders it as a live trace.

The app's contract with the LLM is deliberate: the LLM sees *all* tools in its schema, safe and dangerous alike. We don't hide the dangerous ones. We let the LLM try — and the scope check is what stops it. That's the point of zero-trust enforcement: you don't rely on the LLM behaving. You rely on the credential.

## Where the code lives

| Piece | File |
|-------|------|
| Flask entry point | [`app.py`](app.py) |
| Env config + scope ceiling | [`config.py`](config.py) |
| Three-agent pipeline + SSE | [`pipeline.py`](pipeline.py) |
| Tools + scope templates | [`tools.py`](tools.py) |
| Customers, tickets, KB articles | [`data.py`](data.py) |
| Quick-fill scenarios | [`data.py`](data.py) (bottom) |
| HTMX frontend | [`templates/index.html`](templates/index.html), [`static/style.css`](static/style.css) |
| One-shot app registration | [`setup.py`](setup.py) |

Read `pipeline.py` first. The three-phase flow — triage, knowledge, response — is one top-to-bottom function, and every SSE event you see in the UI is a `yield` statement in that file.

## Further reading

| Go here for | Link |
|-------------|------|
| The other demo (clinical / per-patient, single-request) | [`../demo/README.md`](../demo/README.md) |
| SDK concepts (roles, scopes, delegation) | [`../docs/concepts.md`](../docs/concepts.md) |
| Real-world patterns for your own apps | [`../docs/developer-guide.md`](../docs/developer-guide.md) |
| Broker API | [AgentWrit broker docs](https://github.com/devonartis/agentwrit/tree/main/docs) |
