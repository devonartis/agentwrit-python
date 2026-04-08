# Concepts

This document explains how AgentAuth works and what you need to understand before writing application code. Read this first — it will save you hours of debugging.

---

## The Problem

AI agents need credentials to access databases, APIs, and file systems. Most teams solve this one of three ways:

**Shared API keys.** Every agent uses the same key. If one agent is compromised, every agent's access is compromised. You cannot tell which agent did what. The key never expires because rotating it breaks every running agent.

**User identity inheritance.** The agent runs as the user who launched it. The agent can do everything the user can do — read anyone's data, write to any table, delete anything.

**Service accounts with broad scope.** An ops team creates a service account for the agent framework. It has all the permissions any agent might ever need. It sits unused 99% of the time but remains fully active.

These approaches share three failures:
1. Credentials live too long
2. Credentials are too broad
3. No way to trace what each agent did

---

## The Three Roles

AgentAuth has three distinct roles. Understanding them is critical because the SDK operates as one of them.

### Operator

The human or script that manages the broker. The operator:
- Starts and configures the broker
- Registers applications and sets their scope ceilings
- Can revoke any token, kill any agent
- Has the admin secret (root of trust)

**You are NOT the operator** (unless you also run the broker). The operator gave you your `client_id` and `client_secret`.

### Application (This Is You)

Your software that uses the SDK. The application:
- Authenticates with `client_id` and `client_secret`
- Creates agents within its scope ceiling
- Cannot exceed the ceiling the operator set
- Cannot revoke other apps' agents or read the audit trail

When you create an `AgentAuthApp`, you are acting as the Application role:

```python
app = AgentAuthApp(broker_url, client_id, client_secret)
```

### Agent

An ephemeral identity created by your application for a specific task. The agent:
- Has a unique SPIFFE identity (e.g., `spiffe://agentauth.local/agent/my-service/task-001/a1b2c3d4`)
- Holds a short-lived JWT with specific scope
- Can renew its token, release it, or delegate to other agents
- Cannot create other agents — only the app can do that

When you call `create_agent()`, you get back an `Agent` object:

```python
agent = app.create_agent(
    orch_id="my-service",
    task_id="task-001",
    requested_scope=["read:data:customers"],
)
```

### The Authority Chain

```
Operator (root of trust)
  │  sets scope ceiling: ["read:data:*", "write:data:*"]
  ▼
Application (your code)
  │  creates agents within ceiling
  ▼
Agent (ephemeral worker)
  │  scope can only narrow on delegation
  ▼
Delegated Agent (sub-worker, max 5 hops)
```

At every step, authority can only narrow. The operator defines what apps can do. Apps define what agents can do. Agents define what sub-agents can do. No step can exceed the step above it.

---

## Scopes

Scopes are the most important concept in the SDK. Every agent has a scope that defines exactly what it can do. Getting scopes wrong is the #1 source of bugs.

### The 3-Segment Format

Every scope has exactly three parts separated by colons:

```
action:resource:identifier
```

| Part | What it means | Examples |
|------|---------------|----------|
| **action** | What operation | `read`, `write`, `delete` |
| **resource** | What category of thing | `data`, `logs`, `config` |
| **identifier** | Which specific thing | `customers`, `partition-7`, `report-q3` |

Real examples:
```
read:data:customers          — read customer data
write:data:order-abc-123     — write to a specific order
read:data:partition-7        — read partition 7
write:logs:cleanup-result    — write a cleanup log entry
```

### Wildcards

The wildcard `*` only works in the **identifier** position (the third segment):

```
read:data:*                  — read ANY data resource
write:data:*                 — write to ANY data resource
```

Wildcards do NOT work in action or resource positions:

```
*:data:customers             — INVALID, will not match anything
read:*:customers             — INVALID, will not match anything
*:*:*                        — INVALID, will not match anything
```

This is critical to understand. The broker enforces exact match on action and resource. Only the identifier supports wildcards.

### Scope Matching Rules

The SDK provides `scope_is_subset()` to check if a requested scope is covered by an allowed scope:

```python
from agentauth import scope_is_subset

# Exact match — works
scope_is_subset(["read:data:customers"], ["read:data:customers"])  # True

# Wildcard covers specific — works
scope_is_subset(["read:data:customers"], ["read:data:*"])  # True

# Different identifier — blocked
scope_is_subset(["read:data:orders"], ["read:data:customers"])  # False

# Different action — blocked
scope_is_subset(["write:data:customers"], ["read:data:customers"])  # False

# Different resource — blocked
scope_is_subset(["read:logs:customers"], ["read:data:customers"])  # False
```

### Common Scope Mistakes

These are mistakes we discovered while building the acceptance test suite:

**Mistake 1: Wrong resource segment**

```python
# WRONG — "analytics" is the resource, "project-x" is the identifier
scope = ["read:analytics:project-x"]

# RIGHT — "data" is the resource, "analytics-project-x" is the identifier
scope = ["read:data:analytics-project-x"]
```

The resource must match what your operator configured in the scope ceiling. If the ceiling is `["read:data:*"]`, the resource must be `data`.

**Mistake 2: Thinking action mismatch is the only check**

```python
agent_scope = ["read:data:email-user-42"]

# This is blocked, but not ONLY because write != read.
# It's blocked because BOTH action AND resource must match.
scope_is_subset(["write:email:user-42"], agent_scope)  # False
# "write" != "read" (action mismatch)
# "email" != "data" (resource mismatch)
# "user-42" != "email-user-42" (identifier mismatch)
# All three are wrong. The scope format matters.
```

**Mistake 3: Forgetting the identifier is the full third segment**

```python
# The scope "read:data:partition-7" has:
#   action = "read"
#   resource = "data"  
#   identifier = "partition-7"

# NOT:
#   action = "read"
#   resource = "data"
#   identifier = "partition"
#   sub-identifier = "7"
```

There are exactly 3 segments. Everything after the second colon is the identifier, even if it contains hyphens.

### Using scope_is_subset() as a Gatekeeper

In real applications, the app checks scope before allowing an agent to act:

```python
from agentauth import scope_is_subset

agent = app.create_agent(
    orch_id="customer-service",
    task_id="lookup",
    requested_scope=["read:data:customer-artis"],
)

# Before any action, check if the agent is authorized
action_scope = ["read:data:customer-artis"]
if scope_is_subset(action_scope, agent.scope):
    # proceed — agent is authorized
    ...
else:
    # block — agent doesn't have this scope
    ...

# Agent tries to read ALL customers — blocked
scope_is_subset(["read:data:all-customers"], agent.scope)  # False

# Agent tries to WRITE — blocked (read-only agent)
scope_is_subset(["write:data:customer-artis"], agent.scope)  # False
```

This is the app's responsibility. The broker sets the scope at creation time, but the app must enforce it before every action.

---

## Agent Lifecycle

An agent goes through a simple lifecycle:

```
Created → Active → Released (or Expired)
```

### Created

`create_agent()` registers the agent with the broker and returns an `Agent` object.

```python
agent = app.create_agent(
    orch_id="my-service",
    task_id="my-task",
    requested_scope=["read:data:customers"],
)
```

### Active

While active, the agent can:
- Use its `access_token` as a Bearer credential
- Call `renew()` to get a fresh token (same identity, old token revoked)
- Call `delegate()` to give narrower scope to another agent
- Be validated by any service via `validate(broker_url, token)`

### Released

When the task is done, the agent calls `release()`:

```python
agent.release()
```

After release:
- The broker rejects the token on all future requests
- `renew()` raises `AgentAuthError`
- `delegate()` raises `AgentAuthError`
- Calling `release()` again is safe (no-op)

### Expired

If the agent doesn't release and doesn't renew, the token expires naturally after its TTL (default 300 seconds). After expiry, `validate()` returns `valid=False`.

---

## Delegation

Delegation is how one agent gives a subset of its authority to another agent. The broker issues a new token for the delegate with narrowed scope.

### How It Works

```python
# Agent A has two scopes
agent_a = app.create_agent(
    orch_id="pipeline",
    task_id="orchestrator",
    requested_scope=["read:data:partition-7", "read:data:partition-8"],
)

# Agent B exists (created separately)
agent_b = app.create_agent(
    orch_id="pipeline",
    task_id="worker",
    requested_scope=["read:data:partition-7"],
)

# A delegates ONLY partition-7 to B
delegated = agent_a.delegate(
    delegate_to=agent_b.agent_id,
    scope=["read:data:partition-7"],
)
```

`delegated` is a `DelegatedToken` with:
- `access_token` — a new JWT for agent B with only `["read:data:partition-7"]`
- `expires_in` — TTL (default 60 seconds)
- `delegation_chain` — records of who delegated what

### Delegation Rules

1. **Scope must be subset of delegator's scope.** Agent A has `["read:data:partition-7", "read:data:partition-8"]`. It can delegate `["read:data:partition-7"]` but NOT `["read:data:partition-9"]`.

2. **The broker rejects escalation.** If agent A tries to delegate scope it doesn't have, the broker returns 403 and the SDK raises `AuthorizationError`.

3. **Delegation chain is tracked.** Each delegation records who delegated, what scope they had, and when. Auditors can trace authority back to the source.

4. **Maximum depth is 5.** A→B→C→D→E→F is the deepest chain allowed.

5. **Same-scope delegation is allowed.** The broker accepts delegation where the delegated scope equals the delegator's scope. Equal is a valid subset. (We confirmed this in acceptance testing.)

### What You Cannot Do with the SDK's delegate()

The SDK's `agent.delegate()` always uses the agent's **own registration token**. If agent B receives a delegated token from agent A and wants to re-delegate to agent C, `agent_b.delegate()` will use B's registration token — not the delegated token from A. This means the broker starts a fresh delegation chain from B, not a continuation of A's chain.

To build a real multi-hop chain (A→B→C), the second hop must use the delegated token directly as the Bearer credential via raw HTTP:

```python
import httpx

# Hop 1: A delegates to B (SDK)
delegated_ab = agent_a.delegate(
    delegate_to=agent_b.agent_id,
    scope=["read:data:partition-7"],
)

# Hop 2: B delegates to C using the delegated token (raw HTTP)
resp = httpx.post(
    f"{broker_url}/v1/delegate",
    json={
        "delegate_to": agent_c.agent_id,
        "scope": ["read:data:partition-7"],
    },
    headers={"Authorization": f"Bearer {delegated_ab.access_token}"},
)
```

This is a known SDK limitation. Single-hop delegation works through the SDK. Multi-hop chains require the second hop to use the delegated token directly.

---

## Validation

Any service can validate a token by asking the broker:

```python
from agentauth import validate

result = validate(broker_url, agent.access_token)
```

`validate()` is a module-level function. It doesn't need an `AgentAuthApp` — just the broker URL and the token. This is how downstream services verify agent tokens.

The broker returns `valid=True` with claims, or `valid=False` with an error message. The broker intentionally returns the same generic error ("token is invalid or expired") for all failure cases — expired, revoked, malformed, or unknown — to prevent information leakage.

---

## Error Model

When the broker rejects a request, it returns an RFC 7807 Problem Detail. The SDK parses this into structured exceptions.

### Exception Hierarchy

```
AgentAuthError (base — catch this to handle any SDK error)
├── ProblemResponseError (broker returned an error response)
│   ├── AuthenticationError (401 — bad credentials)
│   ├── AuthorizationError (403 — scope violation, delegation rejected)
│   └── RateLimitError (429 — too many requests)
├── TransportError (network failure — broker unreachable)
└── CryptoError (Ed25519 failure — key generation or signing)
```

### ProblemDetail Fields

When you catch a `ProblemResponseError` (or any subclass), you get structured error info:

```python
from agentauth.errors import AuthorizationError

try:
    agent_a.delegate(delegate_to=agent_b.agent_id, scope=["read:data:something-else"])
except AuthorizationError as e:
    print(e.status_code)          # 403
    print(e.problem.type)         # urn:agentauth:error:scope_violation
    print(e.problem.title)        # Forbidden
    print(e.problem.detail)       # delegated scope exceeds delegator scope
    print(e.problem.error_code)   # scope_violation
    print(e.problem.instance)     # /v1/delegate
    print(e.problem.request_id)   # bd4b257e53efe7f2 (broker trace ID)
```

Every field is available for logging, alerting, or debugging. The `request_id` matches the broker's `X-Request-ID` header for cross-referencing with broker logs.

---

## SPIFFE Identities

Every agent gets a unique SPIFFE identity:

```
spiffe://agentauth.local/agent/{orch_id}/{task_id}/{instance_id}
```

For example:
```
spiffe://agentauth.local/agent/data-pipeline/manager/8ece9e2d8a22fdb8
```

This identity is:
- **Unique per instance** — two agents with the same orch_id and task_id get different instance IDs
- **Cryptographically bound** — tied to the Ed25519 keypair generated during registration
- **Embedded in the JWT** — the `sub` claim in the token contains this SPIFFE URI
- **Preserved across renewals** — `renew()` issues a new token but the agent_id stays the same

---

## Standards Alignment

The SDK implements the [Ephemeral Agent Credentialing](https://github.com/devonartis/AI-Security-Blueprints/blob/main/patterns/ephemeral-agent-credentialing/versions/v1.2.md) pattern (v1.2), which aligns with:

| Standard | What it addresses |
|----------|-------------------|
| **NIST IR 8596** | Unique AI agent identities via SPIFFE IDs |
| **NIST SP 800-207** | Zero-trust per-request validation |
| **OWASP Top 10 for Agentic AI (2026)** | ASI03 (Identity/Privilege Abuse), ASI07 (Insecure Inter-Agent Communication) |
| **IETF WIMSE** (draft-ietf-wimse-arch-06) | Delegation chain re-binding |
| **IETF draft-klrc-aiagent-auth-00** | OAuth/WIMSE/SPIFFE framework for AI agents |

---

## Next Steps

| Guide | What You'll Learn |
|-------|-------------------|
| [Getting Started](getting-started.md) | Install, connect, create your first agent |
| [Developer Guide](developer-guide.md) | Real patterns: delegation, scope gating, error handling |
| [API Reference](api-reference.md) | Every class, method, parameter, and exception |
