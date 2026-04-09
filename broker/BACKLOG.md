# SDK Backlog

## Post-v0.3.0 Enhancement: Scope Creation Tool

**Status:** Deferred | **Priority:** Medium | **Depends On:** v0.3.0 release

### Problem Discovered During Acceptance Testing
During acceptance test development, we discovered significant confusion around scope format and validation:

1. **Scope Format Confusion**: Developers may use inconsistent scope patterns like:
   - `read:email:user-42` vs `read:data:email-user-42`
   - `read:documents:doc-xyz` vs `read:data:document-doc-xyz`
   
2. **Ceiling Matching Complexity**: The Broker validates that requested scopes are covered by the app's ceiling using `action:resource:identifier` parsing with wildcard support. However, developers may not understand:
   - `read:data:*` covers `read:data:user-123` (same resource, wildcard identifier)
   - `read:data:*` does NOT cover `read:email:user-42` (different resource)

3. **Debugging Difficulty**: When scope validation fails, the error message shows the ceiling but doesn't explain WHY a specific scope was rejected.

### Proposed Solution: Scope Creation Tool
A developer tool that helps design and validate scopes before runtime:

```python
from agentauth.tools import ScopeDesigner

# Check if scope matches ceiling
designer = ScopeDesigner(app_ceiling=["read:data:*", "write:data:*"])

# Validate proposed agent scope
result = designer.validate([
    "read:data:user-123",
    "write:data:order-456"
])
print(result.is_valid)  # True
print(result.explanation)  # "All scopes covered by ceiling"

# Get suggestions for invalid scopes
result = designer.validate(["read:email:user-42"])
print(result.is_valid)  # False
print(result.explanation)  # "Resource 'email' not in ceiling. Did you mean 'read:data:email-user-42'?"
```

### Why This Matters
- **Security**: Prevents developers from accidentally requesting overly broad scopes
- **Developer Experience**: Clear error messages BEFORE runtime
- **Documentation**: Living examples of scope best practices

### References
- Acceptance tests: `tests/integration/test_acceptance.py` (22 stories demonstrating scope patterns)
- Broker validation: `broker/internal/authz/scope.go` (ScopeIsSubset logic)

---

## Post-v0.3.0 Enhancement: Agent Token Validation

**Status:** Deferred | **Priority:** Low | **Depends On:** None

### Description
Add explicit token validation methods to the SDK Agent class for defense-in-depth. Currently, the SDK trusts that `requested_scope` equals granted scope (which is guaranteed by the Broker's all-or-nothing enforcement). Future enhancement could add explicit verification.

### Proposed API
```python
class Agent:
    def validate_token(self) -> TokenValidationResult:
        """
        Verify token validity with Broker via POST /v1/token/validate.
        Useful for:
        - Checking revocation status
        - Getting current expiry
        - Explicit scope verification (defense in depth)
        """
        pass
    
    def has_scope(self, required: str) -> bool:
        """
        Check if agent has required scope against live Broker state.
        Calls validate_token() internally.
        """
        pass
```

### Rationale
- Current SDK correctly uses `requested_scope` (Broker guarantees match)
- This enhancement adds explicit verification without claiming existing code is broken
- No Broker changes required (endpoint already exists)

### References
- Original finding: See `../REJECT-FIX_NOW.md` (false alarm, documented for history)
- Broker endpoint: `POST /v1/token/validate` (see `broker/docs/api.md`)

---

## Feature Request: Scope Update on Existing Agent

**Status:** Proposed | **Priority:** Medium | **Depends On:** Broker support (new endpoint)

### Problem
Once an agent is created, its scope is fixed for its lifetime. If a running agent needs additional scopes (still within the app's ceiling), the only option is to release the agent and create a new one. This breaks the agent's SPIFFE identity, invalidates any delegated tokens, and forces the app to re-wire everything downstream.

### Observation
The broker already has `POST /v1/token/renew` which issues a new JWT for the same agent identity (same SPIFFE ID, new JTI, fresh timestamps). The same mechanism could issue a new JWT with an updated scope, as long as the new scope remains within the app's scope ceiling. The trust chain stays intact — the ceiling still caps authority.

### Proposed Broker Endpoint
```
POST /v1/token/update-scope
Authorization: Bearer <agent-token>

{
  "requested_scope": ["read:data:customer-7291", "write:notes:customer-7291"]
}
```

**Behavior:**
1. Validate Bearer token (same as renew)
2. Validate `requested_scope` is within the app's scope ceiling
3. Revoke old token
4. Issue new JWT with same agent identity + updated scope
5. Return new `access_token` + `expires_in`

### Proposed SDK Method
```python
agent = app.create_agent(
    orch_id="support",
    task_id="ticket-42",
    requested_scope=[f"read:data:{customer_id}"],
)

# Later, the task needs write access too
agent.update_scope([
    f"read:data:{customer_id}",
    f"write:notes:{customer_id}",
])
# agent.access_token is now updated, same SPIFFE identity
```

### Why This Is Useful
- **Long-running agents** that discover they need additional authority mid-task (e.g., an LLM agent that starts read-only and determines it needs to write)
- **Avoids identity churn** — the agent keeps its SPIFFE ID, delegation chains remain valid
- **Still safe** — the app's ceiling is the hard limit, scope can only be updated within it

### Notes
- This is a **broker-side feature request** — the SDK cannot implement this without a new broker endpoint
- This file lives in the SDK repo, not the broker repo, so it survives broker re-vendoring
- The broker is currently frozen; this is for a future upstream release
