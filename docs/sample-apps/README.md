# Sample Apps

Self-contained tutorials that teach the AgentWrit SDK by building real-world systems. Each app is a complete, runnable program — not a code snippet — with its own business scenario, architecture walkthrough, and learning outcomes.

---

## App Catalog

Apps are ordered by complexity. Each one introduces new SDK concepts while building on what the previous apps taught.

| # | App | SDK Concepts | Domain |
|---|-----|-------------|--------|
| 1 | [E-Commerce Order Worker](01-order-worker.md) | Agent lifecycle: create → validate → use → release | Retail order processing |
| 2 | [Multi-Tenant Data Pipeline](02-data-pipeline.md) | Multiple isolated agents, `scope_is_subset()` gatekeeping | ETL data processing |
| 3 | [Patient Record Guard](03-patient-guard.md) | Cross-scope denial, dynamic scope from request context | Healthcare HIPAA enforcement |
| 4 | [Content Moderation Queue](04-moderation-delegation.md) | Single-hop delegation, authority narrowing | Trust & safety platform |
| 5 | [CI/CD Deployment Runner](05-deploy-chain.md) | Multi-hop delegation (A→B→C), raw HTTP delegation hop | DevOps deployment |
| 6 | [Financial Trading Agent](06-trading-agent.md) | Token renewal for long tasks, custom short TTL, renewal loops | Fintech trading |
| 7 | [Incident Response System](07-incident-response.md) | Emergency revocation at 4 levels, post-revoke validation | Security operations |
| 8 | [Compliance Audit Scanner](08-audit-scanner.md) | Token validation as a service, full error model, `ProblemDetail` inspection | Regulatory compliance |

---

## Understanding the Scope Ceiling

Before running any sample app, you need to understand one critical concept that trips up almost every new developer.

### The App Ceiling Is Broad — The Agent Scope Is Narrow

AgentWrit has two layers of authority:

1. **App scope ceiling** — set by the operator when they register your app. This is the **maximum** authority your app can ever grant to any agent. Think of it as the outer fence.

2. **Agent requested scope** — set by your code when you call `create_agent()`. This is the **actual** authority the agent gets. It must be a subset of the ceiling. Think of it as the inner fence.

```
Operator sets broad ceiling:
  read:data:*, write:data:*, read:records:*, write:billing:*

Your code requests narrow scope per task:
  read:data:customer-7291, write:data:order-4823

The broker enforces: requested ⊆ ceiling
```

**Why the ceiling uses wildcards:** The app needs to be able to create agents for *any* customer, *any* order, *any* tenant. It doesn't know at registration time which specific identifiers it will need at runtime. The wildcards in the identifier position (`*`) let the app create agents scoped to any specific customer, order, or tenant — but the app can never exceed the action and resource boundaries the operator defined.

**Why this is safe:** A broad ceiling does NOT mean broad access. Every agent still gets a narrow, task-specific scope. The app ceiling is a *limit*, not a *grant*. If the operator sets the ceiling to `read:data:*`, the app can create agents with `read:data:customer-7291` but can NEVER create an agent with `write:data:anything` or `read:logs:anything` — those are different action:resource pairs.

**Wildcards only work in the identifier position (3rd segment):**

| Scope | Valid? | Why |
|-------|--------|-----|
| `read:data:*` | ✅ | Wildcard in identifier — covers any specific identifier |
| `*:data:customers` | ❌ | Wildcard in action — broker rejects this |
| `read:*:customers` | ❌ | Wildcard in resource — broker rejects this |

This means your ceiling specifies which **actions** on which **resources** your app can ever use, with flexibility on the **specific identifier**.

---

## One-Time Setup for All Sample Apps

Register a single app with a broad ceiling that covers every sample app. You only do this once.

### Step 1: Start the Broker

```bash
docker compose up -d
```

### Step 2: Register the Universal Sample App

```bash
export AA_ADMIN_SECRET="dev-secret"  # change if your broker uses a different secret

ADMIN_TOKEN=$(curl -s -X POST http://127.0.0.1:8080/v1/admin/auth \
  -H "Content-Type: application/json" \
  -d "{\"secret\": \"$AA_ADMIN_SECRET\"}" \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['access_token'])")

curl -s -X POST http://127.0.0.1:8080/v1/admin/apps \
  -H "Authorization: Bearer $ADMIN_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "sample-apps",
    "scopes": [
      "read:data:*",
      "write:data:*",
      "read:analytics:*",
      "write:reports:*",
      "read:records:*",
      "write:records:*",
      "read:billing:*",
      "write:billing:*",
      "read:labs:*",
      "read:prescriptions:*",
      "write:prescriptions:*",
      "read:deploy:*",
      "write:deploy:*",
      "read:config:*",
      "read:trades:*",
      "write:trades:*"
    ]
  }' | python3 -m json.tool
```

Copy the `client_id` and `client_secret` from the response.

### Step 3: Set Environment Variables

```bash
export AGENTWRIT_BROKER_URL="http://127.0.0.1:8080"
export AGENTWRIT_CLIENT_ID="<client_id from step 2>"
export AGENTWRIT_CLIENT_SECRET="<client_secret from step 2>"
```

These same environment variables work for **every** sample app. Each app will request its own narrow scope within this ceiling.

### What If the Ceiling Is Wrong?

The broker returns an `AuthorizationError` (HTTP 403) with `error_code: scope_violation`. The error message will say the requested scope exceeds the app's scope ceiling. The fix is always the same: have the operator update your app's ceiling to include the missing action:resource pair.

---

## Learning Path

**Start here if you're new to AgentWrit:**

```
App 1 (lifecycle basics)
  → App 2 (multiple agents + scope checks)
    → App 3 (scope denial patterns)
      → App 4 (delegation fundamentals)
        → App 5 (multi-hop chains)
          → App 6 (long-running tasks + renewal)
            → App 7 (incident response)
              → App 8 (validation service + errors)
```

You can skip around if you're comfortable with a concept, but Apps 1–3 are foundational. Apps 4–5 build on each other for delegation. Apps 6–8 are independent advanced topics.

---

## How Each App Doc Is Structured

Each app document follows the same format:

1. **The Scenario** — what business problem this app solves
2. **What You'll Learn** — specific SDK concepts and why they matter
3. **Architecture** — how the app is designed and why
4. **The Code** — complete, runnable, annotated
5. **Setup Requirements** — which ceiling scopes this app uses and why
6. **Running It** — how to execute and what output to expect
7. **Key Takeaways** — distillation of the patterns worth remembering

---

## Not What You're Looking For?

| Need | Go To |
|------|-------|
| 5-minute quickstart | [Getting Started](../getting-started.md) |
| Concept explanations (scopes, roles, delegation) | [Concepts](../concepts.md) |
| Real patterns for production code | [Developer Guide](../developer-guide.md) |
| Every method and parameter | [API Reference](../api-reference.md) |
| Full-stack healthcare demo with LLM + UI | `demo/` directory |
