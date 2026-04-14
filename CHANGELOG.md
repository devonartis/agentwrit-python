# Changelog

## v0.3.0 — Initial AgentWrit Public Release (2026-04-14)

First public release of the AgentWrit Python SDK. Complete rewrite from the internal v0.1.0/v0.2.0 codebase.

### Core API

- **AgentWritApp** — main entry point; authenticates with the broker on first use (lazy auth)
- **create_agent()** — registers an agent with Ed25519 challenge-response, returns an `Agent` object
- **Agent** — lifecycle management: `renew()`, `release()`, `delegate()`
- **validate()** — module-level online token validation against the broker
- **scope_is_subset()** — module-level scope comparison utility

### Models

- `AgentClaims`, `ValidateResult`, `RegisterResult`, `HealthStatus`, `DelegatedToken`, `ProblemDetail` — typed dataclasses for all broker responses

### Error Handling

- `AgentWritError` base exception with RFC 7807 `ProblemDetail` support
- Typed hierarchy: `AuthenticationError`, `AuthorizationError`, `RateLimitError`, `ProblemResponseError`, `TransportError`

### Transport

- `httpx`-based HTTP transport with automatic error dispatch
- User-Agent: `agentwrit-python/0.3.0`

### Testing

- 99 unit tests (no broker required)
- 15 acceptance stories against live broker
- Integration test suite with session-scoped fixtures

### Demos

- MedAssist AI (FastAPI + HTMX) — multi-agent medical encounter pipeline
- Support Tickets (Flask + HTMX + SSE) — triage/knowledge/response agent pipeline
