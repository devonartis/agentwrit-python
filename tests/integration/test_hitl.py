"""Integration tests: HITL approval flow (SDK-S6).

Verifies the human-in-the-loop approval flow using the sdk-integration test app.
That app has hitl_scopes=["write:data:*"], so:
  - read:data:*  → tokens issued immediately (not HITL-gated)
  - write:data:* → raises HITLApprovalRequired, requires human approval

HITL approval flow:
  1. client.get_token with write:data:* raises HITLApprovalRequired
  2. App backend calls POST /v1/app/approvals/{id}/approve with the APP JWT
     (app:launch-tokens:* scope -- NOT admin token) and the approving human's identity
  3. Retry client.get_token with the returned approval_token → JWT issued

Requires: AGENTAUTH_CLIENT_ID, AGENTAUTH_CLIENT_SECRET, AGENTAUTH_ADMIN_SECRET set.
"""

from __future__ import annotations

import pytest
import requests as requests_lib

from agentauth import AgentAuthClient, HITLApprovalRequired


@pytest.mark.integration
class TestHITLFlow:
    """SDK-S6: HITL approval flow end-to-end."""

    def test_hitl_scope_raises_hitl_approval_required(
        self, client: AgentAuthClient
    ) -> None:
        """Requesting write:data:* (HITL-gated) raises HITLApprovalRequired."""
        with pytest.raises(HITLApprovalRequired) as exc_info:
            client.get_token("hitl-raise-agent", ["write:data:sensitive"])

        err: HITLApprovalRequired = exc_info.value
        # approval_id has format apr-<12hex>
        assert err.approval_id.startswith("apr-"), f"Expected apr- prefix, got: {err.approval_id}"
        assert err.expires_at, "Expected non-empty expires_at"

    def test_hitl_full_flow_raise_approve_retry(
        self,
        broker_url: str,
        client: AgentAuthClient,
        app_token: str,
    ) -> None:
        """Full HITL flow: raise → approve → retry → valid JWT with original_principal.

        Uses app_token (app:launch-tokens:* scope) for the approval call.
        The admin token does NOT have app:launch-tokens:* -- only the app JWT does.
        In production: end-user sees approval UI, confirms, app backend calls approve.
        """
        # Step 1: write:data:* triggers HITL gate
        with pytest.raises(HITLApprovalRequired) as exc_info:
            client.get_token("hitl-full-agent", ["write:data:records"])
        approval_id: str = exc_info.value.approval_id

        # Step 2: App backend approves with the app JWT (app:launch-tokens:* scope)
        # principal must be prefixed with "user:" per broker API contract
        approve_resp = requests_lib.post(
            f"{broker_url}/v1/app/approvals/{approval_id}/approve",
            headers={"Authorization": f"Bearer {app_token}"},
            json={"principal": "user:integration-test@example.com"},
            timeout=10,
        )
        assert approve_resp.status_code == 200, f"Approval failed: {approve_resp.text}"
        approval_token: str = approve_resp.json()["approval_token"]

        # Step 3: Retry with the broker-signed approval_token
        token: str = client.get_token(
            "hitl-full-agent",
            ["write:data:records"],
            approval_token=approval_token,
        )
        assert isinstance(token, str)
        assert len(token.split(".")) == 3, "Expected valid JWT"

        # Step 4: JWT claims show original_principal from the approval
        validate_resp = requests_lib.post(
            f"{broker_url}/v1/token/validate",
            json={"token": token},
            timeout=10,
        )
        result: dict[str, object] = validate_resp.json()
        assert result["valid"] is True
        claims: dict[str, object] = result["claims"]  # type: ignore[assignment]
        assert claims.get("original_principal") == "user:integration-test@example.com"

    def test_non_hitl_scope_succeeds_without_approval(
        self, client: AgentAuthClient
    ) -> None:
        """read:data:* is NOT in hitl_scopes so it issues a token immediately."""
        token: str = client.get_token("hitl-safe-agent", ["read:data:*"])
        assert isinstance(token, str)
        assert len(token.split(".")) == 3
