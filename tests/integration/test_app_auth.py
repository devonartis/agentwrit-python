"""Integration tests: app authentication (SDK-S1, SDK-S12).

These tests verify that AgentAuthClient authenticates against a real broker
and that the broker records correct audit events (SDK-S12: standard API).

Requires: broker running, AGENTAUTH_CLIENT_ID, AGENTAUTH_CLIENT_SECRET,
          AGENTAUTH_ADMIN_SECRET set.
"""

from __future__ import annotations

import os

import pytest
import requests as requests_lib

from agentauth import AgentAuthClient
from agentauth.errors import AuthenticationError


@pytest.mark.integration
class TestAppAuth:
    """SDK-S1: Developer initializes the client."""

    def test_client_initializes_against_real_broker(
        self, broker_url: str, app_credentials: dict[str, str]
    ) -> None:
        """Client init calls POST /v1/app/auth and succeeds with valid credentials."""
        client = AgentAuthClient(
            broker_url=broker_url,
            client_id=app_credentials["client_id"],
            client_secret=app_credentials["client_secret"],
        )
        # If we get here without exception, app auth succeeded
        assert repr(client).startswith("AgentAuthClient(")

    def test_bad_credentials_raise_authentication_error(self, broker_url: str) -> None:
        """Wrong credentials raise AuthenticationError immediately (no retry)."""
        with pytest.raises(AuthenticationError) as exc_info:
            AgentAuthClient(
                broker_url=broker_url,
                client_id="bad-client-id",
                client_secret="bad-secret",
            )
        assert exc_info.value.status_code == 401

    def test_secret_not_in_error_message(self, broker_url: str) -> None:
        """client_secret never appears in error output (SDK-S10)."""
        secret: str = "super-secret-must-not-leak"
        with pytest.raises(AuthenticationError) as exc_info:
            AgentAuthClient(
                broker_url=broker_url,
                client_id="bad-id",
                client_secret=secret,
            )
        assert secret not in str(exc_info.value)
        assert secret not in repr(exc_info.value)


@pytest.mark.integration
class TestAuditTrail:
    """SDK-S12: SDK uses the standard broker API, visible in audit trail."""

    def test_app_auth_creates_audit_event(
        self,
        broker_url: str,
        app_credentials: dict[str, str],
        admin_token: str,
    ) -> None:
        """POST /v1/app/auth produces an app_authenticated audit event."""
        AgentAuthClient(
            broker_url=broker_url,
            client_id=app_credentials["client_id"],
            client_secret=app_credentials["client_secret"],
        )

        audit_resp = requests_lib.get(
            f"{broker_url}/v1/audit/events",
            headers={"Authorization": f"Bearer {admin_token}"},
            params={"event_type": "app_authenticated", "limit": "5"},
            timeout=10,
        )
        assert audit_resp.status_code == 200
        events: list[dict[str, object]] = audit_resp.json()["events"]
        assert len(events) > 0, "Expected at least one app_authenticated event"
        latest: dict[str, object] = events[0]
        assert latest["event_type"] == "app_authenticated"
        assert latest["outcome"] == "success"
