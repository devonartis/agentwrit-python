# v0.3.0 SDK Acceptance Stories

These stories define the expected behavior of the AgentAuth Python SDK. They are intended to be implemented as high-level integration tests in `tests/sdk-core/` using a running broker.

---

## 1. App Authentication & Health

### STORY-P3-S1: App Lazy Authentication
**Who:** A developer using `AgentAuthApp`.
**What:** The app should automatically authenticate with the broker on the first request that requires it (e.g., `create_agent` or `health`).
**Why:** To reduce boilerplate and simplify the developer experience.
**How:**
1. Initialize `AgentAuthApp` with `client_id` and `client_secret`.
2. Call `app.health()`.
3. **Expected:** The SDK performs a `POST /v1/app/auth` internally, retrieves a JWT, and then successfully executes the `GET /v1/health` call. No manual auth call is required by the user.

### STORY-P3-S2: App Session Renewal
**Who:** A developer using `AgentAuthApp`.
**What:** The app should automatically re-authenticate when its internal session JWT expires.
**Why:** To ensure long-running applications don't fail due to expired app credentials.
**How:**
1. Initialize `AgentAuthApp`.
2. Simulate/wait for app JWT expiry (or use a very short-lived client if the broker allows).
3. Call `app.create_agent(...)`.
4. **Expected:** The SDK detects the expired JWT, calls `POST /v1/app/auth`, and successfully completes the agent creation flow.

---

## 2. Agent Lifecycle

### STORY-P3-S3: Successful Agent Creation (Happy Path)
**Who:** A developer using `AgentAuthApp`.
**What:** A single call to `app.create_agent()` should orchestrate the entire challenge-response registration.
**Why:** This is the primary value proposition of the SDK.
**How:**
1. Call `app.create_agent(orch_id="test-orch", task_id="test-task", requested_scope=["read:data:*"])`.
2. **Expected:** 
   - Returns an `Agent` object.
   - `agent.agent_id` follows the SPIFFE format: `spiffe://agentauth.local/agent/test-orch/test-task/{instance_id}`.
   - `agent.scope` contains `["read:data:*"]`.
   - `agent.access_token` is a valid JWT.

### STORY-P3-S4: Agent Scope Ceiling Enforcement
**Who:** A developer using `AgentAuthApp`.
**What:** An attempt to create an agent with a scope exceeding the app's ceiling must fail.
**Why:** To enforce the security boundary set by the operator.
**How:**
1. (Precondition) App is registered with ceiling `["read:data:*"]`.
2. Call `app.create_agent(..., requested_scope=["write:data:customers"])`.
3. **Expected:** Raises `agentauth.errors.AuthorizationError` (mapping to a 403 Forbidden from the broker).

### STORY-P3-S5: Agent Token Renewal
**Who:** An active `Agent`.
**What:** Calling `agent.renew()` should refresh the token in-place without changing the agent's identity.
**Why:** To support long-running agent tasks.
**How:**
1. Create an `Agent` via `app.create_agent(...)`.
2. Store the current `access_token`.
3. Call `agent.renew()`.
4. **Expected:** 
   - `agent.access_token` is now different from the old one.
   - `agent.agent_id` remains exactly the same.
   - The new token is valid when used in a header.

### STORY-P3-S6: Agent Release (Self-Revocation)
**Who:** An active `Agent`.
**What:** Calling `agent.release()` should inform the broker to revoke the token immediately.
**Why:** To minimize the window of opportunity for a compromised agent.
**How:**
1. Create an `Agent`.
2. Call `agent.release()`.
3. Attempt to use the `agent.access_token` in a `validate()` call or a mock request.
4. **Expected:** `app.validate(agent.access_token)` returns `valid=False`.

---

## 3. Delegation

### STORY-P3-S7: Successful Scope-Attenuated Delegation
**Who:** A primary `Agent`.
**What:** An agent can delegate a narrower scope to another (pre-registered) agent.
**Why:** To support complex multi-agent workflows with least-privilege.
**How:**
1. Create `Agent A` with scope `["read:data:*"]`.
2. Create `Agent B` (or use an existing one).
3. Call `token = agent_a.delegate(delegate_to=agent_b.agent_id, scope=["read:data:customers"])`.
4. **Expected:** 
   - Returns a `DelegatedToken` object.
   - The new token's claims show the delegation chain including `Agent A`.
   - The new token is valid for the narrower scope.

### STORY-P3-S8: Delegation Depth Limit
**Who:** A chain of agents.
**What:** The broker must reject delegation if it exceeds a depth of 5.
**Why:** To prevent infinite delegation loops and unbounded complexity.
**How:**
1. Create a chain of 5 agents.
2. Each agent delegates to the next.
3. The 5th agent attempts to delegate to a 6th agent.
4. **Expected:** Raises `agentauth.errors.AuthorizationError`.

---

## 4. Security & Error Handling

### STORY-P3-S9: Tool-Gating with `scope_is_subset`
**Who:** A developer implementing a tool-gate.
**What:** The `scope_is_subset` utility correctly identifies if an agent's scope covers a required tool scope, including wildcard matching.
**Why:** To allow fast, local, non-networked pre-flight checks.
**How:**
1. Test `scope_is_subset(["read:data:customers"], ["read:data:*"])` -> `True`.
2. Test `scope_is_subset(["write:data:customers"], ["read:data:*"])` -> `False`.
3. Test `scope_is_subset(["read:data:customers"], ["read:data:customers"])` -> `True`.

### STORY-P3-S10: RFC 7807 Problem Detail Parsing
**Who:** An SDK user encountering an error.
**What:** When the broker returns an error, the SDK must parse the `application/problem+json` body into a structured `ProblemDetail` object.
**Why:** To provide actionable error messages to developers.
**How:**
1. Mock a broker response with a 400 status and a `ProblemDetail` JSON body.
2. Trigger the corresponding SDK action (e.g., `create_agent`).
3. **Expected:** Raises `ProblemResponseError` where `error.problem.title` and `error.problem.detail` match the mock JSON.
