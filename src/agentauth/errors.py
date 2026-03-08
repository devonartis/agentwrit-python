"""AgentAuth exception hierarchy and error response parsing.

Translates broker HTTP errors into actionable Python exceptions that map to
the Ephemeral Agent Credentialing pattern:
  - ScopeCeilingError: C2 (Task-Scoped Tokens) -- scope attenuation enforced
  - HITLApprovalRequired: HITL gate -- human authorization required (NIST NCCoE)
  - RateLimitError: broker rate limiting respected (C3 Zero-Trust)
  - BrokerUnavailableError: transient failure (retry exhausted)
  - TokenExpiredError: C4 (Automatic Expiration)

All SDK exceptions inherit from AgentAuthError. The parse_error_response()
function converts broker HTTP error bodies into the appropriate exception type.

The broker returns two error formats:
  - RFC 7807 application/problem+json (most errors)
  - HITL format: {"error": "hitl_approval_required", "approval_id": ..., "expires_at": ...}

SECURITY INVARIANT: client_secret must NEVER appear in any error message,
repr, or log output from this module.
"""

from __future__ import annotations

import json


class AgentAuthError(Exception):
    """Base exception for all AgentAuth SDK errors."""

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.error_code = error_code


class AuthenticationError(AgentAuthError):
    """Broker rejected app or agent credentials (HTTP 401)."""

    def __init__(
        self,
        message: str,
        *,
        client_id: str | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.client_id = client_id
        if client_id is not None:
            message = f"{message} (client_id={client_id})"
        super().__init__(message, status_code=status_code, error_code=error_code)


class ScopeCeilingError(AgentAuthError):
    """Requested scope exceeds the app's allowed ceiling (HTTP 403, scope_violation)."""

    def __init__(
        self,
        *,
        detail: str,
        requested_scope: list[str] | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.requested_scope = requested_scope
        message = detail
        if requested_scope is not None:
            message = f"{detail} (requested: {requested_scope})"
        super().__init__(message, status_code=status_code, error_code=error_code)


class HITLApprovalRequired(AgentAuthError):  # noqa: N818
    """Scope requires human-in-the-loop approval (HTTP 403, hitl_approval_required).

    The developer's app must present the approval_id to the end-user,
    then retry the request with the resulting approval_token.
    """

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


class RateLimitError(AgentAuthError):
    """Broker rate limit exceeded (HTTP 429)."""

    def __init__(
        self,
        message: str,
        *,
        retry_after: int | None = None,
        status_code: int | None = None,
        error_code: str | None = None,
    ) -> None:
        self.retry_after = retry_after
        super().__init__(message, status_code=status_code or 429, error_code=error_code)


class BrokerUnavailableError(AgentAuthError):
    """Broker is unreachable or returned a 5xx error."""


class TokenExpiredError(AgentAuthError):
    """Agent token has expired and must be re-obtained."""


# ── Response parser ────────────────────────────────────────────────────────


# Broker error body shapes (RFC 7807 and HITL-specific)
class _RFC7807Body:
    """Type alias for RFC 7807 problem+json response fields."""


def parse_error_response(
    status_code: int,
    body: dict[str, object] | str,
    *,
    retry_after: int | None = None,
    client_id: str | None = None,
) -> AgentAuthError:
    """Convert a broker HTTP error response into the appropriate exception.

    Checks for the HITL format first (body has "error": "hitl_approval_required"),
    then dispatches on status_code and error_code.

    Args:
        status_code: HTTP status code from the broker response.
        body: Parsed JSON body (dict) or raw JSON string.
        retry_after: Value of the Retry-After header, if present.
        client_id: The client_id used in the request (for error context).

    Returns:
        An AgentAuthError subclass instance (not raised -- caller decides).
    """
    parsed_body: dict[str, object]

    if isinstance(body, str):
        try:
            raw: object = json.loads(body)
            parsed_body = raw if isinstance(raw, dict) else {}
        except (json.JSONDecodeError, TypeError):
            parsed_body = {}
    elif isinstance(body, dict):
        parsed_body = body
    else:
        parsed_body = {}

    # HITL format takes priority -- different from RFC 7807
    if parsed_body.get("error") == "hitl_approval_required":
        approval_id: str = str(parsed_body.get("approval_id", ""))
        expires_at: str = str(parsed_body.get("expires_at", ""))
        return HITLApprovalRequired(approval_id=approval_id, expires_at=expires_at)

    detail_raw: object = parsed_body.get("detail", parsed_body.get("title", ""))
    detail: str = str(detail_raw) if detail_raw else ""
    error_code_raw: object = parsed_body.get("error_code")
    error_code: str | None = str(error_code_raw) if error_code_raw is not None else None

    if status_code == 401:
        return AuthenticationError(
            detail or "authentication failed",
            client_id=client_id,
            status_code=status_code,
            error_code=error_code,
        )

    # scope_violation: at POST /v1/register (scope exceeds launch token ceiling)
    # forbidden: at POST /v1/app/launch-tokens (scope exceeds app data ceiling)
    if status_code == 403 and error_code in ("scope_violation", "forbidden"):
        return ScopeCeilingError(
            detail=detail or "scope violation",
            status_code=status_code,
            error_code=error_code,
        )

    if status_code == 429:
        return RateLimitError(
            detail or "rate limit exceeded",
            retry_after=retry_after,
            status_code=status_code,
            error_code=error_code,
        )

    return AgentAuthError(
        detail or f"broker error (HTTP {status_code})",
        status_code=status_code,
        error_code=error_code,
    )
