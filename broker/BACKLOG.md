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
