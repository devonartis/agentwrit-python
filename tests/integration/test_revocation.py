"""Integration tests: self-revocation (SDK-S8).

Verifies that an agent can self-revoke its credential via POST /v1/token/release.
After revocation, the token is invalid per POST /v1/token/validate.

Requires: broker running, AGENTAUTH_CLIENT_ID, AGENTAUTH_CLIENT_SECRET set.
"""

from __future__ import annotations

import pytest
import requests as requests_lib

from agentauth import AgentAuthClient


@pytest.mark.integration
class TestRevocation:
    """SDK-S8: Agent self-revokes its token when done."""

    def test_revoked_token_is_invalid(
        self, client: AgentAuthClient, broker_url: str
    ) -> None:
        """Token is invalid after revoke_token() is called."""
        token: str = client.get_token("revoke-agent", ["read:data:*"])

        # Confirm valid before revocation
        before = requests_lib.post(
            f"{broker_url}/v1/token/validate",
            json={"token": token},
            timeout=10,
        )
        assert before.json()["valid"] is True

        # Revoke
        client.revoke_token(token)

        # Confirm invalid after revocation
        after = requests_lib.post(
            f"{broker_url}/v1/token/validate",
            json={"token": token},
            timeout=10,
        )
        assert after.json()["valid"] is False

    def test_revoke_produces_audit_event(
        self,
        client: AgentAuthClient,
        broker_url: str,
        admin_token: str,
    ) -> None:
        """Revocation produces a token_released audit event (SDK-S12)."""
        token: str = client.get_token("audit-revoke-agent", ["read:data:*"])
        client.revoke_token(token)

        audit_resp = requests_lib.get(
            f"{broker_url}/v1/audit/events",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"event_type": "token_released", "limit": "5"},
            timeout=10,
        )
        assert audit_resp.status_code == 200
        events: list[dict[str, object]] = audit_resp.json()["events"]
        assert len(events) > 0, "Expected a token_released audit event"
        assert events[0]["event_type"] == "token_released"
