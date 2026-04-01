# Demo App: Acceptance Test Stories

Spec: `.plans/specs/2026-04-01-demo-app-spec.md`
Design: `.plans/designs/2026-04-01-demo-app-design-v2.md`
Broker API: `agentauth-core/docs/api.md` (v2.0.0)
SDK: `AgentAuthClient` — `get_token`, `delegate`, `revoke_token`, `validate_token`
LLM: Claude via Anthropic SDK (direct, no abstraction)

## What These Stories Test

The SDK already has 119 unit tests and 13 integration tests. These stories test whether
the **demo app works as a real multi-agent financial pipeline** — AI agents doing real
work with AgentAuth managing every credential. The stories verify: agents get scoped
credentials, process real data with Claude, hand off through delegation chains, and
shut down cleanly. When adversarial input triggers prompt injection, the credential
layer contains the blast radius.

## Infrastructure Prerequisites

| Prerequisite | Purpose | Smoke Test Story | Status |
|-------------|---------|-----------------|--------|
| AgentAuth broker (Docker) | Credential management | DEMO-PC1 | NOT VERIFIED |
| `AA_ADMIN_SECRET` env var | Admin auth at startup | DEMO-PC1 | NOT VERIFIED |
| `ANTHROPIC_API_KEY` env var | Claude API for agents | DEMO-PC2 | NOT VERIFIED |
| Python 3.11+ with `uv` | Runtime | DEMO-PC3 | NOT VERIFIED |

---

## Precondition Stories

---

### DEMO-PC1: Broker Is Running and Accessible [PRECONDITION]

Who: The operator.

What: The operator verifies that the AgentAuth broker is running in Docker and
responding to health checks. This is the foundation — every other test depends on
a live broker.

Why: If the broker isn't running, no agent can get credentials. The demo app's
startup sequence calls `GET /v1/health`, then `POST /v1/admin/auth`, then
`POST /v1/admin/apps`. All three must succeed or the app exits with an error.

Setup:
```bash
cd ~/proj/agentauth-core
export AA_ADMIN_SECRET="live-test-secret-32bytes-long-ok"
./scripts/stack_up.sh
```

How to run:
```bash
curl -s http://127.0.0.1:8080/v1/health | python -m json.tool
```

Expected: `{"status": "ok", "version": "2.0.0", ...}` — broker is healthy.

---

### DEMO-PC2: Anthropic API Key Is Valid [PRECONDITION]

Who: The developer.

What: The developer verifies that the `ANTHROPIC_API_KEY` env var is set and the
Anthropic API is reachable. A quick Claude call confirms the key works.

Why: Every agent in the pipeline calls Claude. If the API key is invalid or the API
is unreachable, every agent will fail. Better to catch this before the pipeline runs.

Setup: `ANTHROPIC_API_KEY` set.

How to run:
```bash
python -c "
import anthropic, os
c = anthropic.Anthropic()
r = c.messages.create(model='claude-haiku-4-5-20251001', max_tokens=10, messages=[{'role':'user','content':'Say ok'}])
print(r.content[0].text)
"
```

Expected: Claude responds (any text). No auth error.

---

### DEMO-PC3: Demo App Starts Successfully [PRECONDITION]

Who: The developer.

What: The developer runs `uv run uvicorn app:app` in `examples/demo-app/` and the
app starts without error. The startup log confirms: broker health check passed, admin
auth succeeded, app registered (client_id visible, client_secret masked), Anthropic
client initialized.

Why: If startup fails, nothing else works. The startup sequence exercises the SDK's
`AgentAuthClient` constructor (which calls `POST /v1/app/auth`) and the admin API.
Both must work.

Setup: Broker running (DEMO-PC1). `AA_ADMIN_SECRET` and `ANTHROPIC_API_KEY` set.

How to run:
```bash
cd examples/demo-app
AA_ADMIN_SECRET="live-test-secret-32bytes-long-ok" uv run uvicorn app:app --port 8000 &
sleep 3
curl -s http://localhost:8000/ | head -20
kill %1
```

Expected:
1. App starts without error
2. Startup log shows: broker healthy, admin auth OK, app registered, Anthropic client ready
3. `GET /` returns HTML (the main page)

---

## Acceptance Stories

---

### DEMO-S1: Pipeline Processes All 12 Transactions [ACCEPTANCE]

Who: The developer.

What: The developer clicks "Run Pipeline" and watches 5 Claude-powered agents
process 12 financial transactions. The orchestrator dispatches work to the parser,
risk analyst, compliance checker, and report writer. Each agent's output appears
in the activity feed as it completes. The final report is a summary of risk scores
and compliance findings.

This is a real application doing real work. The parser extracts structured fields
from transaction descriptions. The risk analyst scores each transaction with reasoning.
The compliance checker flags AML and sanctions violations. The report writer produces
an executive summary. All powered by Claude, all secured by AgentAuth.

Why: This is the demo's primary function. If the pipeline doesn't process all 12
transactions and produce meaningful output, the demo has failed. The developer needs
to see that real AI agents can do real work with scoped credentials — not a simulation,
not a mock, not a staged walkthrough.

Setup: App running (DEMO-PC3).

How to run:
1. Open `http://localhost:8000`
2. Click "Run Pipeline"
3. Watch the activity feed

Expected:
1. Parser output: 12 transactions parsed with structured fields (amount, currency, counterparty, category)
2. Risk Analyst output: 12 risk scores — mix of low, medium, high, critical
3. Compliance Checker output: 12 compliance findings — mix of pass, flag, fail
4. Transaction #2 (Cayman Islands, $49.5K): high risk, AML flagged
5. Transaction #4 ($9,900 multi-ATM): compliance flagged for structuring
6. Transaction #7 (Damascus, $25K): critical risk, sanctions flagged
7. Transaction #11 ($120K intercompany): AML-reportable (>$10K)
8. Report Writer: executive summary referencing the risk scores and compliance findings
9. All output appears in the activity feed as agents complete

---

### DEMO-S2: Each Agent Gets a Correctly Scoped Credential [ACCEPTANCE]

Who: The security lead.

What: The security lead watches the security dashboard as the pipeline runs and
verifies that each agent received a credential with exactly the scope it needs —
nothing more.

The security lead is checking the principle of least privilege in practice:
- Parser: `read:data:transactions` — can only read, can't write
- Risk Analyst: `read:data:transactions, write:data:risk-scores` — can read and write scores, but not compliance rules
- Compliance Checker: `read:data:transactions, read:rules:compliance` — can read rules and data, can't write
- Report Writer: `read:data:risk-scores, read:data:compliance-results, write:data:reports` — reads intermediate results, writes report, never sees raw transactions
- Orchestrator: `read:data:*, write:data:reports` — coordinates, writes final report

Why: If agents got broader scopes than needed, the security model is broken. A
compromised risk analyst with `read:rules:compliance` could learn how to game the
system. A report writer with `read:data:transactions` would violate data minimization.
The credential scopes aren't decorative — they're the enforcement mechanism.

Setup: App running. Pipeline triggered.

How to run:
1. Click "Run Pipeline"
2. Watch the security dashboard's Active Tokens panel

Expected:
1. 5 tokens appear in the dashboard as agents are created
2. Each token shows scope badges matching the table above
3. Parser and Report Writer show delegation depth > 0 (delegated from orchestrator)
4. Risk Analyst and Compliance Checker show delegation depth 0 (own tokens)
5. No agent has a scope broader than specified

---

### DEMO-S3: Prompt Injection Is Contained by Credential Layer [ACCEPTANCE]

Who: The security lead.

What: Two transactions in the sample data contain prompt injection payloads.
Transaction #6 tells the Risk Analyst to read compliance rules and modify
transaction records. Transaction #12 tells the Parser to write to reports.
The agents process these transactions like any other — Claude may or may not
follow the injection. But it doesn't matter: the credential layer blocks any
out-of-scope access regardless of what Claude tries to do.

This is the core security story. The demo doesn't harden prompts against injection.
It doesn't need to. The credential layer is the safety net. Even if Claude is
fully compromised, the scoped token limits the blast radius to what the agent was
authorized to do.

Why: Prompt injection is the #1 attack vector for LLM agents (CVE-2025-68664
LangGrinch). Most frameworks "solve" this by hardening prompts — which is inherently
fragile because you're fighting the model's instruction-following capability. AgentAuth
solves it at the infrastructure layer: the agent's token can't do more than its scope
allows, period. This story proves that claim.

The security lead needs to see three things:
1. The adversarial transactions were processed (not skipped or filtered)
2. If Claude attempted out-of-scope access, the broker blocked it
3. The denied attempt was logged in the audit trail

Setup: App running. Pipeline triggered.

How to run:
1. Click "Run Pipeline"
2. Watch the activity feed for transactions #6 and #12
3. Watch the security dashboard for scope violation events

Expected (if Claude follows the injection):
1. Scope violation appears in activity feed: "⚠ Risk Analyst attempted read:rules:compliance — DENIED"
2. Dashboard audit trail shows `scope_violation` event with `outcome: denied`
3. The agent's SPIFFE ID in the audit event matches the Risk Analyst's token
4. Pipeline continues — the adversarial transaction still gets a risk score
5. The second adversarial transaction (#12) triggers a similar denial on the Parser

Expected (if Claude ignores the injection):
1. Transactions #6 and #12 are scored/parsed normally
2. No scope violations in audit trail
3. This is also a valid outcome — the credential layer was ready, the attack just didn't land

Both outcomes demonstrate the security model. The credential layer doesn't depend on
the attack succeeding — it's always enforcing.

---

### DEMO-S4: Report Writer Never Sees Raw Transactions [ACCEPTANCE]

Who: The security lead.

What: The security lead verifies that the Report Writer agent only received risk
scores and compliance findings — never raw transaction data. This is data minimization
enforced by credentials: the Report Writer's scope is
`read:data:risk-scores, read:data:compliance-results, write:data:reports`. There is
no `read:data:transactions` in that scope.

The security lead verifies this by:
1. Checking the Report Writer's token scope in the dashboard
2. Reading the Report Writer's output — it should reference risk levels and compliance
   findings, not transaction amounts, counterparties, or raw descriptions
3. Checking the audit trail — no `read:data:transactions` access from the Report Writer

Why: Data minimization is a regulatory requirement in financial systems. An agent that
produces risk reports doesn't need to see the underlying transaction details — it just
needs the scores and findings. Enforcing this through credentials (not through prompt
engineering or code logic) means it can't be bypassed by a prompt injection or code bug.

Setup: App running. Pipeline completed.

How to run:
1. Run the pipeline
2. Inspect the Report Writer's token scope in the dashboard
3. Read the Report Writer's output
4. Check audit trail for Report Writer's access patterns

Expected:
1. Report Writer token scope: `["read:data:risk-scores", "read:data:compliance-results", "write:data:reports"]` — no `read:data:transactions`
2. Report Writer output references risk levels (low/medium/high/critical) and compliance findings (pass/flag/fail) but does NOT quote raw transaction descriptions, amounts, or counterparty names
3. Audit trail shows Report Writer accessed risk-scores and compliance-results — no transaction data access

---

### DEMO-S5: Delegation Chain Shows Scope Attenuation [ACCEPTANCE]

Who: The security lead.

What: The security lead inspects the delegation relationships visible in the
dashboard's credentials panel. Two agents received delegated credentials from
the orchestrator:

- **Parser:** Orchestrator holds `read:data:*, write:data:reports`. Delegated
  to Parser with only `read:data:transactions`. The scope was attenuated — the
  Parser can't read everything, just transactions. And it can't write at all.

- **Report Writer:** Orchestrator delegated `read:data:risk-scores, read:data:compliance-results, write:data:reports` — attenuated from its own broader scope.

The delegation chain is cryptographically signed and recorded in the token's claims.
The security lead can verify: who delegated what, when, with what scope.

Why: Delegation is how multi-agent systems share permissions without over-provisioning.
Without scope attenuation, the orchestrator would have to give the Parser its full
`read:data:*` scope — meaning the Parser could read compliance rules, risk scores,
and any other data type. With attenuation, the Parser gets exactly
`read:data:transactions` and nothing else.

The delegation chain is the authorization paper trail. When an auditor asks "why did
the Parser have access to transaction data?", the chain shows: the orchestrator
authorized it, at this time, with this specific scope, signed with the orchestrator's
Ed25519 key.

Setup: App running. Pipeline completed.

How to run:
1. Run the pipeline
2. Inspect the credentials panel in the dashboard
3. Verify delegation relationships and scope attenuation

Expected:
1. Dashboard shows: Orchestrator → Parser (scope attenuated from `read:data:*` to `read:data:transactions`)
2. Dashboard shows: Orchestrator → Report Writer (scope: `read:data:risk-scores, read:data:compliance-results, write:data:reports`)
3. Parser's token claims include `delegation_chain` with orchestrator's SPIFFE ID
4. Report Writer's token claims include `delegation_chain`
5. Risk Analyst and Compliance Checker are NOT delegated — they have their own tokens

---

### DEMO-S6: Audit Trail Has Verifiable Hash Chain [ACCEPTANCE]

Who: The security lead.

What: The security lead inspects the audit trail in the dashboard and verifies hash
chain integrity. Each event has a `hash` and `prev_hash`. The genesis event has
`prev_hash` = all zeros. Each subsequent event's `prev_hash` matches the previous
event's `hash`. A break in the chain would indicate tampering.

This is C5 (Immutable Audit Logging) from the v1.3 pattern. The demo doesn't just
claim tamper-evident logging — the security lead can verify it by inspection.

Why: Financial data processing is subject to SOX, PCI-DSS, and regulatory audit.
"Who accessed what transaction data, when, with what authorization?" must be
answerable. And the answer must be tamper-proof. The hash chain means modifying any
past event would break the chain — the next event's `prev_hash` wouldn't match.

Setup: App running. Pipeline completed (generates multiple audit events).

How to run:
1. Run the pipeline
2. Inspect the audit trail panel in the dashboard
3. Verify hash chain: event N's prev_hash matches event N-1's hash

Expected:
1. Multiple audit events visible: `app_authenticated`, `agent_registered`,
   `token_issued`, `delegation_created`, `token_released`, potentially `scope_violation`
2. Each event shows: timestamp, event_type, agent_id, outcome, hash (truncated), prev_hash (truncated)
3. Full hashes visible on hover
4. Genesis event's prev_hash is all zeros
5. Each subsequent event's prev_hash matches the previous event's hash
6. Events are chronologically ordered
7. Scope violation events (if any) have `outcome: denied` and red highlighting

---

### DEMO-S7: All Tokens Revoked After Pipeline Completes [ACCEPTANCE]

Who: The operator.

What: The operator watches the security dashboard after the pipeline completes and
verifies that all 5 agent tokens have been revoked. No dangling credentials. The
dashboard shows all tokens struck-through or removed. The audit trail shows
`token_released` events for each agent.

Why: When a batch job completes, all credentials should die. In a traditional system,
API keys stay active until someone remembers to rotate them (which might be never).
With AgentAuth, the orchestrator explicitly revokes every token as the last pipeline
step. Even if revocation failed, the 5-minute TTL would expire them automatically.
Two safety nets.

An auditor checking the system after the pipeline completes should see: zero active
credentials. This is C4 (Automatic Expiration & Revocation) in practice.

Setup: App running. Pipeline completed.

How to run:
1. Run the pipeline
2. Wait for completion
3. Check the Active Tokens panel in the dashboard

Expected:
1. All 5 tokens (orchestrator, parser, risk-analyst, compliance-checker, report-writer) are revoked
2. Dashboard shows tokens struck-through or removed
3. Audit trail shows `token_released` events for all 5 agents
4. Zero active tokens remaining

---

### DEMO-S8: Startup Fails Clearly When Dependencies Missing [ACCEPTANCE]

Who: The developer who forgot something.

What: The developer tries to start the app with missing dependencies and gets clear,
actionable error messages instead of Python tracebacks.

Three scenarios:
1. Broker not running → "Cannot reach broker at http://127.0.0.1:8080. Start with: /broker up"
2. Wrong admin secret → "Admin auth failed. Check that AA_ADMIN_SECRET matches your broker."
3. Missing Anthropic key → "ANTHROPIC_API_KEY not set. Get one at console.anthropic.com"

Why: Error messages are the app's first impression when something goes wrong. A
developer who sees `httpx.ConnectError: [Errno 61]` files a bug report. A developer
who sees "Cannot reach broker. Start with: /broker up" fixes it in 10 seconds. The
error must tell them what's wrong AND what to do.

The wrong admin secret message must NOT include the secret value (security).

Setup: Broker intentionally not running, or wrong secret, or missing key.

How to run:
```bash
# Test 1: No broker
AA_ADMIN_SECRET="anything" ANTHROPIC_API_KEY="sk-ant-test" uv run uvicorn app:app 2>&1 | head -5

# Test 2: Wrong secret (broker running)
AA_ADMIN_SECRET="wrong" ANTHROPIC_API_KEY="sk-ant-test" uv run uvicorn app:app 2>&1 | head -5

# Test 3: Missing Anthropic key
AA_ADMIN_SECRET="live-test-secret-32bytes-long-ok" uv run uvicorn app:app 2>&1 | head -5
```

Expected:
1. Each scenario exits with code 1 within 5 seconds
2. Each error message is human-readable, includes the specific failure, and includes how to fix it
3. No Python tracebacks visible to the user
4. The wrong admin secret is NOT included in the error message

---

### DEMO-S9: Dashboard Shows Real-Time Token Lifecycle [ACCEPTANCE]

Who: The operator monitoring the pipeline.

What: The operator watches the security dashboard during pipeline execution and sees
the full token lifecycle play out in real-time:

1. Pipeline starts → orchestrator token appears (scope badges, TTL counting down)
2. Parser dispatched → parser token appears (delegated, lower depth)
3. Risk Analyst dispatched → analyst token appears (own token, depth 0)
4. Compliance Checker dispatched → checker token appears
5. Report Writer dispatched → writer token appears (delegated)
6. Pipeline cleanup → all tokens struck-through, one by one

The operator sees credentials being born, used, and dying. This is what production
monitoring of an agent pipeline looks like.

Why: Tokens are ephemeral — they exist for minutes, not months. The dashboard makes
this lifecycle tangible. An operator used to static API keys has never watched a
credential expire in real-time. Seeing tokens appear, count down, and get revoked is
the visceral version of "short-lived task-scoped tokens." This is C8 (Observability).

Setup: App running.

How to run:
1. Open the app
2. Watch the security dashboard while clicking "Run Pipeline"

Expected:
1. Tokens appear as agents are created (within seconds of pipeline start)
2. Each token shows: agent name, scope badges, TTL countdown (ticking), delegation depth
3. Delegated tokens (parser, report-writer) visually distinct from direct tokens
4. TTL counters update in real-time
5. After cleanup, all tokens are struck-through or removed
6. The lifecycle is visible — tokens don't just appear and disappear, the transition is observable

---

## Story-to-Component Mapping

| Story | Pattern Components Demonstrated |
|-------|-------------------------------|
| DEMO-S1 | C1 (each agent gets unique identity), C2 (short-lived tokens for batch) |
| DEMO-S2 | C2 (task-scoped tokens), C3 (scope enforcement per request) |
| DEMO-S3 | C3 (zero-trust — broker validates every request), C5 (violation logged) |
| DEMO-S4 | C2 (scope determines access), C7 (delegation with attenuation) |
| DEMO-S5 | C6 (both parties registered), C7 (delegation chain, scope attenuation) |
| DEMO-S6 | C5 (immutable audit, hash chain integrity) |
| DEMO-S7 | C4 (expiration & revocation — all tokens die at pipeline end) |
| DEMO-S8 | C8 (observability — clear error reporting) |
| DEMO-S9 | C8 (observability — real-time monitoring) |

**All 8 pattern components covered across 9 acceptance stories.**

## SDK Method Coverage

| Method | Where Exercised |
|--------|----------------|
| `AgentAuthClient()` | DEMO-PC3 (startup), DEMO-S1 (pipeline) |
| `get_token()` | DEMO-S1 (5 agents), DEMO-S2 (scope verification) |
| `delegate()` | DEMO-S5 (parser + report writer delegation) |
| `revoke_token()` | DEMO-S7 (all tokens revoked at cleanup) |
| `validate_token()` | DEMO-S5 (delegation chain inspection), DEMO-S4 (report writer scope check) |
