# SDK Backlog

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
