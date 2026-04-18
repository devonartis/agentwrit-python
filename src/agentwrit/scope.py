from __future__ import annotations

import httpx

from agentwrit.models import ValidateResult


def scope_is_subset(requested: list[str], allowed: list[str]) -> bool:
    """Client-side mirror of the broker's ScopeIsSubset check.

    Business Logic:
    Enforces the rule that authority cannot widen. Equal or narrower scope
    is accepted — a requested scope is covered if every scope in `requested`
    is covered by at least one scope in `allowed`. This mirrors the broker's
    non-strict subset check in authz/scope.go.

    Coverage Rules:
    - Exact match: `read:data:customers` matches `read:data:customers`.
    - Wildcard match: `read:data:customers` matches `read:data:*`.
    - Wildcard match (full): `read:data:customers` matches `*`.

    Args:
        requested: The list of scopes being requested for a task or tool.
        allowed: The list of scopes currently held by the principal.

    Returns:
        True if all requested scopes are covered by the allowed scopes, False otherwise.
    """
    if not requested:
        return True
    if not allowed:
        return False

    def matches(req: str, allow: str) -> bool:
        # Split into [action, resource, identifier]
        req_parts = req.split(":")
        allow_parts = allow.split(":")

        if len(req_parts) != 3 or len(allow_parts) != 3:
            return req == allow

        # Action and Resource must match exactly (or allowed has wildcard)
        # Standard: action:resource:identifier
        if req_parts[0] != allow_parts[0] or req_parts[1] != allow_parts[1]:
            return False

        # Identifier check
        return allow_parts[2] == "*" or req_parts[2] == allow_parts[2]

    for req in requested:
        if not any(matches(req, allow) for allow in allowed):
            return False

    return True

def validate(broker_url: str, token: str, *, timeout: float = 10.0) -> ValidateResult:
    """POST /v1/token/validate -- verify any token via the broker.

    Business Logic:
    This is the authoritative way for a resource server or the App to verify
    if an agent is still trusted. Because validation is performed by the
    broker, it catches not just malformed tokens, but also tokens that
    have been revoked by an operator or via `release()`.

    Note: The broker returns HTTP 200 even for invalid tokens. The
    `valid` boolean in the response body discriminates success from failure.

    Args:
        broker_url: Base URL of the AgentWrit broker.
        token: The JWT access token to validate.
        timeout: HTTP request timeout in seconds.

    Returns:
        A ValidateResult containing the validity status and claims if valid.
    """
    with httpx.Client(timeout=timeout) as client:
        response = client.post(
            f"{broker_url.rstrip('/')}/v1/token/validate",
            json={"token": token}
        )

        # The spec says this endpoint always returns 200.
        # We should handle unexpected non-200s as TransportErrors or similar,
        # but for now we follow the happy path of the contract.
        response.raise_for_status()

        data = response.json()

        if not data.get("valid"):
            return ValidateResult(
                valid=False,
                error=data.get("error")
            )

        # If valid, we need to parse the claims into the AgentClaims model.
        # This is a simplified implementation for the MVP.
        from agentwrit.models import AgentClaims, DelegationRecord

        claims_data = data.get("claims")
        if not claims_data:
            return ValidateResult(valid=False, error="Missing claims in valid response")

        # Reconstruct delegation chain if present
        delegation_chain = None
        if "delegation_chain" in claims_data and claims_data["delegation_chain"]:
            delegation_chain = [
                DelegationRecord(
                    agent=d["agent"],
                    scope=d["scope"],
                    delegated_at=d["delegated_at"]
                )
                for d in claims_data["delegation_chain"]
            ]

        # Spec Section 8.1: required fields use data[key], optional use .get()
        claims = AgentClaims(
            iss=claims_data["iss"],
            sub=claims_data["sub"],
            aud=claims_data.get("aud", []),
            exp=claims_data["exp"],
            nbf=claims_data["nbf"],
            iat=claims_data["iat"],
            jti=claims_data["jti"],
            scope=claims_data["scope"],
            task_id=claims_data["task_id"],
            orch_id=claims_data["orch_id"],
            sid=claims_data.get("sid"),
            delegation_chain=delegation_chain,
            chain_hash=claims_data.get("chain_hash"),
        )

        return ValidateResult(valid=True, claims=claims)
