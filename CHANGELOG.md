# Changelog

## v0.1.0 (2026-03-07)

Initial release of the AgentAuth Python SDK.

### Features

- **AgentAuthApp** -- main entry point with app authentication on init
- **get_token()** -- full 8-step credential flow (app auth, launch token, Ed25519 challenge-response, caching)
- **HITL support** -- `HITLApprovalRequired` exception with `approval_id` and `expires_at`, retry with `approval_token`
- **delegate()** -- scope-attenuated delegation to another registered agent (C7 Delegation Chain)
- **revoke_token()** -- self-revocation for credential cleanup (C4 Expiration & Revocation)
- **validate_token()** -- online token validation against the broker (C3 Zero-Trust)
- **Token caching** -- by (agent_name, scope) key, proactive renewal at 80% TTL, thread-safe
- **Retry with backoff** -- exponential backoff on 5xx/connection errors, Retry-After on 429
- **Error hierarchy** -- AgentAuthError, AuthenticationError, ScopeCeilingError, HITLApprovalRequired, RateLimitError, BrokerUnavailableError, TokenExpiredError
- **Type safety** -- mypy strict mode, no Any in source, TypedDict for all broker responses
- **Security** -- ephemeral Ed25519 keys (never on disk), client_secret never in output, TLS verified by default, thread-safe app token state

### Testing

- 122 unit tests (no broker required)
- 16 integration tests (live broker)
- 7 live acceptance test scripts (SDK-S1 through SDK-S8)
- Security review: all HIGH/MEDIUM findings resolved

### Demo

- Interactive HITL demo app (FastAPI + HTMX) with pattern/NIST annotations
- 6 scenarios: Read Data, Write (HITL), Scope Violation, Delegation, Full Lifecycle, Blast Radius

### Documentation

- README with full API, security properties, and pattern component mapping
- API reference (docs/api-reference.md)
- Getting started guide (docs/getting-started.md)
- Pattern component annotations in all module docstrings
