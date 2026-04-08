# ~~HITL Removal & API Alignment: Clean the SDK for open-source release~~

> **Status:** ~~DONE~~ — shipped in v0.2.0, merged to `main` 2026-04-01. Kept for historical reference.

**Status:** Spec
**Priority:** P0 — blocks v0.2.0 release and all downstream work
**Effort estimate:** 1-2 sessions
**Depends on:** Repo extraction (done)
**Architecture doc:** `agentauth-core/.plans/designs/2026-04-01-python-sdk-repo-design.md`
**Tech debt:** None (fresh extraction)

---

## Overview

The Python SDK was extracted from the `devonartis/agentauth-clients` monorepo via `git filter-repo`. The extraction preserved HITL (human-in-the-loop) approval code that belongs in an enterprise extension layer, not the open-source core SDK. The broker's API contract has also evolved — the SDK's HTTP calls need verification against `agentauth-core/docs/api.md` (the source of truth) and the live broker.

This spec covers two tightly coupled changes:

1. **HITL contamination removal** — delete all HITL exception classes, error parsing branches, client parameters, tests, and docs. The `get_token()` flow simplifies to: cache check -> app auth -> launch token -> keypair -> challenge -> sign -> register -> cache.

2. **API contract audit** — verify every SDK HTTP call against the broker API doc and live broker. Fix any field name, encoding, or response shape mismatches. The MEMORY.md from the parent project flagged potential mismatches (`token` vs `access_token`, `allowed_scopes` vs `allowed_scope`, nonce encoding), though code inspection suggests some may already be aligned.

**What changes:** Remove `HITLApprovalRequired` exception and all code paths that reference it. Remove `approval_token` parameter from `get_token()`. Delete HITL test files and docs. Verify API field names against live broker. Update README and version to v0.2.0.

**What stays the same:** The core auth flow (app auth -> launch token -> challenge-response -> register). The error hierarchy structure (just minus one class). Token caching, retry logic, crypto module, delegation, revocation, and validation. Thread safety model. The `requests` HTTP library dependency.

---

## Goals & Success Criteria

1. `grep -ri "hitl\|approval\|oidc\|federation\|sidecar" src/ tests/` returns zero matches
2. `uv run mypy --strict src/` passes with zero errors
3. `uv run ruff check .` passes with zero errors
4. `uv run pytest tests/unit/` — all tests pass (existing tests updated, no HITL tests remain)
5. Every SDK HTTP call matches the field names and types in `agentauth-core/docs/api.md`
6. `get_token()` has no `approval_token` parameter and no HITL retry/polling logic
7. `__version__` is `"0.2.0"`
8. README contains zero HITL references and no `HITLGroup` in architecture diagrams
9. `docs/hitl-implementation-guide.md` does not exist
10. Live broker integration test: full flow (app auth -> get_token -> validate -> delegate -> revoke) succeeds against running broker

---

## Non-Goals

1. **Enterprise extension points** — no plugin hooks, no subclass registration, no HITL callback interface. YAGNI. Deferred to Phase 4.
2. **Token renewal via SDK** — `POST /v1/token/renew` exists in the broker but the SDK doesn't wrap it yet. Out of scope for this spec.
3. **Admin endpoints** — `POST /v1/admin/auth`, `POST /v1/admin/launch-tokens`, `POST /v1/revoke`, `GET /v1/audit/events`. The SDK is app-path only.
4. **CI/CD setup** — GitHub Actions configuration is a separate task.
5. **PyPI publishing** — separate task after v0.2.0 is verified.

---

## User Stories

### Developer Stories

1. **As a developer**, I want `get_token()` to return an agent JWT without any approval flow so that my agent can authenticate without human intervention.

2. **As a developer**, I want clear error messages when scope exceeds the app ceiling so that I can fix my scope configuration without debugging HTTP bodies.

3. **As a developer**, I want the SDK's field names to match the broker's API exactly so that I don't encounter silent failures from misnamed fields.

### Security Stories

4. **As a security reviewer**, I want zero HITL/OIDC/enterprise code in the open-source SDK so that the attack surface is minimal and the codebase is auditable.

5. **As a security reviewer**, I want `client_secret` to never appear in error messages, repr, or logs so that credential leakage is impossible through SDK error paths.

---

## Contract Changes

**Schema:** None — no schema changes.

**API:** None — no new endpoints. The SDK already calls the correct endpoints. This spec fixes field-level alignment within existing calls.

---

## Codebase Context & Changes

### 1. `src/agentauth/__init__.py:1-51` — Package exports and docstring

```python
"""AgentAuth Python SDK — ephemeral, task-scoped credentials for AI agents.

This package provides a Python client for the AgentAuth credential broker.
It wraps the broker's 8-step Ed25519 challenge-response flow into simple
function calls, handling key generation, token caching, renewal, retry,
and HITL (human-in-the-loop) approval flow control.
...
    HITLApprovalRequired    — 403: human approval needed (flow control, not failure)
...
"""

__version__ = "0.1.0"

from agentauth.errors import (
    ...
    HITLApprovalRequired,
    ...
)

__all__ = [
    ...
    "HITLApprovalRequired",
    ...
]
```

**Change:**
- Remove "and HITL (human-in-the-loop) approval flow control" from module docstring
- Remove `HITLApprovalRequired` from imports, `__all__`, and docstring exports list
- Change `__version__` from `"0.1.0"` to `"0.2.0"`

### 2. `src/agentauth/errors.py:77-97` — HITLApprovalRequired class

```python
class HITLApprovalRequired(AgentAuthError):  # noqa: N818
    """Scope requires human-in-the-loop approval (HTTP 403, hitl_approval_required)."""

    def __init__(
        self,
        *,
        approval_id: str,
        expires_at: str,
    ) -> None:
        self.approval_id = approval_id
        self.expires_at = expires_at
        super().__init__(
            f"HITL approval required (approval_id={approval_id})",
            status_code=403,
            error_code="hitl_approval_required",
        )
```

**Change:** Delete the entire `HITLApprovalRequired` class.

### 3. `src/agentauth/errors.py:1-20` — Module docstring with HITL references

```python
"""AgentAuth exception hierarchy and error response parsing.

Translates broker HTTP errors into actionable Python exceptions that map to
the Ephemeral Agent Credentialing pattern:
  - ScopeCeilingError: C2 (Task-Scoped Tokens) -- scope attenuation enforced
  - HITLApprovalRequired: HITL gate -- human authorization required (NIST NCCoE)
  ...

The broker returns two error formats:
  - RFC 7807 application/problem+json (most errors)
  - HITL format: {"error": "hitl_approval_required", "approval_id": ..., "expires_at": ...}
"""
```

**Change:**
- Remove the `HITLApprovalRequired` line from the pattern list
- Remove the HITL format bullet point (broker returns only RFC 7807 for the core SDK)

### 4. `src/agentauth/errors.py:164-168` — HITL format detection in parse_error_response

```python
    # HITL format takes priority -- different from RFC 7807
    if parsed_body.get("error") == "hitl_approval_required":
        approval_id: str = str(parsed_body.get("approval_id", ""))
        expires_at: str = str(parsed_body.get("expires_at", ""))
        return HITLApprovalRequired(approval_id=approval_id, expires_at=expires_at)
```

**Change:** Delete this entire block (lines 164-168). The HITL error format check is removed since the core broker never sends this response.

### 5. `src/agentauth/app.py:223-263` — get_token() with approval_token parameter

```python
    def get_token(
        self,
        agent_name: str,
        scope: list[str],
        *,
        task_id: str | None = None,
        orch_id: str | None = None,
        approval_token: str | None = None,
    ) -> str:
        """...
        Args:
            ...
            approval_token: HITL approval token returned after human approval.
                Pass this on retry after catching :exc:`HITLApprovalRequired`.
        ...
        Raises:
            HITLApprovalRequired: Scope requires human approval. Catch this,
                present ``exc.approval_id`` to the user, then retry with
                ``approval_token=<user-approved token>``.
        ...
        """
```

**Change:**
- Remove `approval_token` parameter from the method signature
- Remove `approval_token` from Args docstring
- Remove `HITLApprovalRequired` from Raises docstring
- Remove the `if approval_token is not None:` block that attaches it to launch payload (line 283-284)

### 6. `src/agentauth/app.py:278-284` — approval_token in launch payload

```python
        launch_payload: dict[str, object] = {
            "agent_name": agent_name,
            "allowed_scope": scope,
        }
        if approval_token is not None:
            launch_payload["approval_token"] = approval_token
```

**Change:** Remove the `if approval_token` block. The launch_payload keeps only `agent_name` and `allowed_scope`.

### 7. Files to DELETE entirely

| File | Reason |
|------|--------|
| `tests/integration/test_hitl.py` | HITL integration tests — no longer applicable |
| `tests/sdk-core/s6_hitl.py` | HITL acceptance story — no longer applicable |
| `docs/hitl-implementation-guide.md` | HITL implementation guide — enterprise content |
| `examples/hitl-demo/` | Entire HITL demo app (FastAPI + templates) — enterprise content |

### 8. `README.md` — HITL references throughout

**Change (multiple locations):**
- Line 6 docstring: Remove "and HITL (human-in-the-loop) approval flow control"
- Line 28: Remove "**Human-in-the-loop** — sensitive operations require explicit human approval..." bullet
- Lines 57-85: Remove the HITL example from Quick Start (the `try/except HITLApprovalRequired` block)
- Lines 113-114: Remove `HITLGroup["HITL Approvals<br/>/v1/app/approvals/*"]` from architecture diagram
- Lines 167-179: Remove the Human Approver node and its connection from deployment topology
- Lines 236-270: Delete entire "HITL (Human-in-the-Loop) Approval" section and its sequence diagram
- Lines 300-306: Remove `HITLApprovalRequired` from error hierarchy diagram
- Line 326: Remove "HITL provenance" row from Security Properties table
- Line 349: Remove HITL Implementation Guide from Documentation table
- Update Quick Start import to remove `HITLApprovalRequired`

### 9. API contract verification points

These are the SDK HTTP calls to verify against `agentauth-core/docs/api.md`:

| SDK Method | Endpoint | Fields to verify |
|------------|----------|-----------------|
| `_authenticate_app()` | `POST /v1/app/auth` | Request: `client_id`, `client_secret`. Response: `access_token`, `expires_in`, `token_type`, `scopes` |
| `get_token()` step 3 | `POST /v1/app/launch-tokens` | Request: `agent_name`, `allowed_scope`. Response: `launch_token`, `expires_at` |
| `get_token()` step 5 | `GET /v1/challenge` | Response: `nonce`, `expires_in` |
| `get_token()` step 7 | `POST /v1/register` | Request: `launch_token`, `nonce`, `public_key`, `signature`, `orch_id`, `task_id`, `requested_scope`. Response: `agent_id`, `access_token`, `expires_in` |
| `delegate()` | `POST /v1/delegate` | Request: `delegate_to`, `scope`, `ttl`. Response: `access_token`, `expires_in` |
| `revoke_token()` | `POST /v1/token/release` | No body. Response: 204 |
| `validate_token()` | `POST /v1/token/validate` | Request: `token`. Response: `valid`, `claims` or `error` |

**From code inspection, the field names appear aligned.** But the MEMORY.md from the parent project noted potential mismatches. These MUST be verified against the live broker during Step 8 (Live Test). If mismatches are found, they become fix tasks.

**Known minor issue:** `_ChallengeResponse` TypedDict is missing the `expires_in` field that the broker returns. This is harmless (the SDK doesn't use it) but the TypedDict should be accurate.

---

## Edge Cases & Risks

| Case | What Happens | Mitigation |
|------|-------------|------------|
| Tests import `HITLApprovalRequired` | Import error, test fails | Search all test files for HITL imports and update |
| Unit tests mock HITL error parsing | Tests fail after removing the branch | Delete those test cases or update them |
| README links to deleted docs | 404 on docs link | Remove the link from README docs table |
| API field mismatch found during live test | SDK call fails silently or with wrong error | Live broker test is mandatory before merge (Step 8) |
| Downstream code imports `HITLApprovalRequired` | ImportError at runtime | This is v0.2.0 (pre-1.0, breaking changes expected per SemVer) |

---

## Testing Workflow

> **Before writing any test code**, extract the user stories from the
> `## User Stories` section above into a standalone file:
> `tests/sdk-core/user-stories.md`
>
> This is required by the project workflow (CLAUDE.md). The coding agent
> writes user stories first, saves them to `tests/`, then writes test code
> against them. Do not skip this step.

---

## Implementation Plan

> **After acceptance tests are written**, create the implementation plan
> using the `superpowers:writing-plans` skill.
>
> **Required skill:** `superpowers:writing-plans`
> **Save to:** `.plans/2026-04-01-hitl-removal-api-alignment-plan.md` (NOT `docs/plans/`)
>
> The plan must follow the superpowers format:
> - **Plan header:** Goal, Architecture, Tech Stack
> - **Task structure:** Exact file paths, TDD steps (failing test -> run ->
>   implement -> run -> commit), exact commands with expected output
> - **Task-to-story mapping:** Each task maps to one or more acceptance
>   test stories from `tests/sdk-core/user-stories.md`
> - **Plan header must reference this spec:**
>   `**Spec:** .plans/specs/2026-04-01-hitl-removal-api-alignment-spec.md`
>
> **Execution:** Use `superpowers:executing-plans` (separate session or
> subagent-driven). The coding agent follows the plan task-by-task.
>
> Do not skip this step. The plan is the bridge between "what to build"
> (this spec) and "how to build it" (TDD tasks).
