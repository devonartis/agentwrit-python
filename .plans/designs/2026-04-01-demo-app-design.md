# Design: Financial Data Pipeline Demo App

**Created:** 2026-04-01
**Status:** SUPERSEDED by `2026-04-01-demo-app-design-v2.md` — rejected as showcase booth, not real-world app
**Scope:** Runnable web app showcasing all 8 Ephemeral Agent Credentialing v1.3 components, all SDK methods, and both happy/error paths through a financial data pipeline scenario.

---

## Why This Demo Exists

Every AI agent framework today treats credentials like they're just another API key. LangChain agents get `OPENAI_API_KEY`. CrewAI pipelines get Okta tokens with full access. AutoGPT instances inherit user permissions. It's all the same pattern: long-lived, over-privileged, unauditable, and one prompt injection away from total exposure.

Agents are not users. They're autonomous software that makes decisions, calls APIs, and can be compromised through prompt injection (CVE-2025-68664 LangGrinch). They need credentials that match their reality: ephemeral, scoped to exactly what they're doing right now, automatically expired, and fully audited.

This demo makes that contrast visceral. The developer first sees the "status quo" — a static API key with full access, no expiry, no audit trail, total exposure on breach. Then they see the same pipeline through AgentAuth — scoped tokens, minute-level TTLs, delegation chains, tamper-evident audit logging, and a breach that's contained to one scope for five minutes.

**Target audiences:**
- **Indie developer:** "3 lines of code replace my insecure `.env` key management"
- **Security lead:** "Scope attenuation, delegation chains, audit trails — production ready"
- **Decision maker:** "Here's why Okta tokens aren't enough for AI agents"

---

## Pattern Alignment

Source of truth: [Ephemeral Agent Credentialing v1.3](https://github.com/devonartis/AI-Security-Blueprints/blob/main/patterns/ephemeral-agent-credentialing/versions/v1.3.md)

| Component | How the Demo Shows It |
|-----------|----------------------|
| C1: Ephemeral Identity Issuance | Every `get_token()` generates a fresh Ed25519 keypair. Visible in token claims (unique SPIFFE ID). |
| C2: Short-Lived Task-Scoped Tokens | Tokens have 5-min TTL and specific scope. TTL countdown visible in dashboard. |
| C3: Zero-Trust Enforcement | Every broker call validated independently. Breach simulation shows scope enforcement. |
| C4: Automatic Expiration & Revocation | Pipeline cleanup revokes tokens. Renewal demo shows auto-renewal at 80% TTL. |
| C5: Immutable Audit Logging | Live audit trail panel shows hash-chained events with prev_hash linkage. |
| C6: Agent-to-Agent Mutual Auth | Delegation requires both agents to be registered. Visible in delegation step. |
| C7: Delegation Chain Verification | Orchestrator delegates to analyst with attenuated scope. Chain visible in token claims. |
| C8: Operational Observability | The dashboard itself. RFC 7807 errors shown in error scenarios. |

---

## SDK Coverage

Every public method and behavior is exercised:

| SDK Surface | Where Demonstrated |
|------------|-------------------|
| `AgentAuthClient()` constructor | Pipeline Step 1 (app auth) |
| `get_token()` | Pipeline Steps 2, 4 + SDK Explorer |
| `delegate()` | Pipeline Step 3 |
| `validate_token()` | SDK Explorer (token inspector) |
| `revoke_token()` | Pipeline Step 5 |
| Token caching | SDK Explorer (cache demo) |
| Auto-renewal at 80% TTL | SDK Explorer (renewal demo) |
| `ScopeCeilingError` | SDK Explorer (scope error trigger) |
| `AuthenticationError` | SDK Explorer (error scenarios) |
| `BrokerUnavailableError` | SDK Explorer (error scenarios) |

---

## Architecture

```
examples/demo-app/
├── app.py                  # FastAPI entry point, route registration
├── pipeline.py             # Pipeline scenario logic (SDK calls)
├── explorer.py             # SDK Explorer route handlers
├── static/
│   └── style.css           # Dark theme, component tracker animations
└── templates/
    ├── index.html           # Main page — three-section layout
    └── partials/
        ├── step_result.html       # Pipeline step output
        ├── component_card.html    # Component tracker card (lights up)
        ├── token_event.html       # Dashboard token/audit event row
        ├── breach_result.html     # Compromise simulation result
        ├── timeline.html          # Before/after timeline comparison
        ├── validate_result.html   # Token validation claims display
        ├── cache_demo.html        # Caching demonstration output
        ├── renewal_demo.html      # Auto-renewal demonstration
        └── error_result.html      # Error scenario display
```

**Stack:** FastAPI + Jinja2 + HTMX. No JS build step. One command to start.

**Dependencies:** `agentauth` SDK (local), `fastapi`, `uvicorn`, `jinja2`. All managed via `uv`.

**Requires:** Running broker (`/broker up`), registered test app.

---

## Layout — Four Sections

### Section 0: The Contrast (landing view)

The first thing the user sees. A split-screen comparison that makes the problem visceral before showing the solution.

**Left panel (red accent) — "Without AgentAuth: The Status Quo"**

Simulates what developers do today. A mock agent pipeline using a static API key:
- Shows a single long-lived API key (`sk-proj-abc...xyz`) with full access
- Agent reads data — works
- Agent writes data — works (no scope restriction)
- "Breach" button: attacker steals the key → has full read/write access, no expiry, no audit
- Timer counting up: "This key has been valid for 147 days"
- No audit trail — "Who accessed what? Unknown."

This panel does NOT call the broker. It's a simulation showing the insecure pattern — the world of Okta tokens, static AWS keys, shared API secrets.

**Right panel (green accent) — "With AgentAuth"**

Same pipeline, but through AgentAuth:
- Agent gets ephemeral token: `read:data:transactions` only, 5-min TTL
- Agent reads data — works
- Agent tries to write — BLOCKED (wrong scope)
- "Breach" button: attacker steals the token → read-only, expires in 3 minutes, attempt logged
- Timer counting down: "This credential expires in 4:32"
- Full audit trail: every action, hash-chained, tamper-evident

**Call to action:** "See the full pipeline →" button scrolls to Section 1.

This is the adoption pitch. A developer sees both sides and understands *why* in 30 seconds.

### Section 1: Pipeline Runner

The financial data pipeline story. User clicks through 5 steps sequentially. Each step triggers real SDK calls and updates the dashboard below.

**Scenario:** A fintech startup's agent pipeline processes customer transactions.

| Step | User Sees | What Happens (SDK) | Components |
|------|----------|-------------------|------------|
| 1. **Connect** | "App authenticated with broker" | `AgentAuthClient()` constructor authenticates | C3 |
| 2. **Read Transactions** | Token issued with read scope, SPIFFE ID shown | `get_token("orchestrator", ["read:data:transactions"])` | C1, C2 |
| 3. **Analyze Risk** | Delegation chain formed, analyst gets narrower scope | `delegate(token, analyst_id, ["read:data:transactions"])` | C6, C7 |
| 4. **Write Assessment** | New token with write scope, assessment written | `get_token("orchestrator", ["write:data:assessments"])` | C2, C5 |
| 5. **Cleanup** | Both tokens revoked, audit trail complete | `revoke_token()` on both tokens | C4 |

**After Step 5:**

**"Simulate Compromise" button** — Takes the analyst's expired/revoked read-only token, tries to write data. Broker rejects (scope violation). Audit trail logs the attempt. Components C3 and C5 glow.

**Timeline comparison** — Side-by-side:

```
AgentAuth:                          Traditional API Key:
:00  Token issued (read only)       Jan 2024  Key issued (full access)
:02  Breach → BLOCKED               ...365 days...
:05  Token expires                  Still valid. No scope limit.
Blast radius: 1 scope, 5 min       Blast radius: everything, forever
```

### Section 2: SDK Explorer (middle)

Interactive panels for poking at every SDK capability. Each panel is independent — no need to run the pipeline first.

**Panel: Token Inspector**
- Select a token from the pipeline or paste one
- Calls `validate_token()`, displays full claims: SPIFFE ID, scope, expiry, orch_id, task_id, delegation_chain
- Shows valid/invalid/revoked status

**Panel: Cache Demo**
- Click "Get Token" with agent_name + scope
- Shows HTTP calls made (3 calls: launch token, challenge, register)
- Click again with same params → shows "Cache hit — 0 HTTP calls"
- Visual: first call shows 3 network arrows, second call shows cache icon

**Panel: Renewal Demo**
- Issue a token with short TTL (visible countdown)
- Watch the SDK auto-renew at 80% of TTL
- Shows old token → new token transition

**Panel: Error Scenarios**
- "Scope Ceiling" button → requests `admin:everything:*` → `ScopeCeilingError` displayed with RFC 7807 body
- "Bad Credentials" button → wrong client_secret → `AuthenticationError`
- Shows the error hierarchy and how each maps to broker HTTP status

### Section 3: Live Dashboard (bottom, always visible)

Three side-by-side panels that update in real-time as pipeline steps and explorer actions execute.

**Tokens Panel:**
- Active tokens listed with: agent name, scope badges, TTL countdown timer, delegation depth indicator
- Revoked tokens shown struck-through
- Visual distinction between orchestrator (primary color) and delegated (secondary) tokens

**Audit Trail Panel:**
- Hash-chained events: timestamp, event_type, agent_id, outcome
- Each event shows its hash and prev_hash (demonstrating C5 tamper evidence)
- Violation events highlighted in red

**Component Tracker:**
- 8 cards in a row, one per pattern component
- Each starts dim, glows with accent color when demonstrated
- Subtle pulse animation on activation
- Shows which pipeline step or explorer action triggered it
- C8 (Observability) lights up when the dashboard first loads — the dashboard itself is observability

---

## Design Language

Inherited from `agentauth-app`:
- Dark theme: `#0f1117` background, `#1a1d27` secondary, `#6c63ff` accent purple
- CSS variables for consistent theming
- System fonts (no web font loading)
- Clean borders, 8px radius
- HTMX for all interactivity (no JS framework)

**New elements:**
- Component cards with glow animation on activation (`box-shadow` transition with `--accent-glow`)
- TTL countdown badges (CSS animation, HTMX polling)
- Timeline comparison with visual contrast (green for AgentAuth, red for traditional)
- Hash chain visualization (monospace font, truncated hashes with hover for full)

---

## Startup Flow

```bash
# 1. Start the broker
/broker up

# 2. Run the demo
cd examples/demo-app
uv run uvicorn app:app --reload

# 3. Open http://localhost:8000
```

The app auto-registers a test application with the broker on startup (using admin auth). Zero manual setup beyond having the broker running.

---

## What This Does NOT Include

- No authentication for the demo app itself (it's a local demo, not a hosted service)
- No persistent storage (everything in-memory, resets on restart)
- No HITL/OIDC/enterprise features (this is the open-source core demo)
- No production deployment concerns (no Docker, no HTTPS, no rate limiting on the demo)
