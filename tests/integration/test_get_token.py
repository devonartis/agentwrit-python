"""Integration tests: full token acquisition flow (SDK-S2, SDK-S3).

Verifies the complete 8-step flow: app auth -> launch token -> Ed25519
keygen -> challenge nonce -> sign -> register -> JWT returned.

Also verifies token caching (SDK-S3): second call with same args returns
the cached token without additional broker calls.

Requires: broker running, AGENTAUTH_CLIENT_ID, AGENTAUTH_CLIENT_SECRET set.
"""

from __future__ import annotations

import pytest
import requests as requests_lib

from agentauth import AgentAuthClient


def _validate(broker_url: str, token: str) -> dict[str, object]:
    """Helper: validate a token via the broker's public endpoint."""
    resp = requests_lib.post(
        f"{broker_url}/v1/token/validate",
        json={"token": token},
        timeout=10,
    )
    assert resp.status_code == 200
    result: dict[str, object] = resp.json()
    return result


@pytest.mark.integration
class TestGetToken:
    """SDK-S2: Developer gets a token in three lines."""

    def test_get_token_returns_valid_jwt(
        self, client: AgentAuthClient, broker_url: str
    ) -> None:
        """get_token returns a JWT that validates successfully against the broker."""
        token: str = client.get_token("test-agent", ["read:data:*"])

        # Must be a non-empty JWT string (3 dot-separated parts)
        assert isinstance(token, str)
        assert len(token.split(".")) == 3, "Expected JWT with 3 dot-separated parts"

        # Validate against broker
        result = _validate(broker_url, token)
        assert result["valid"] is True

    def test_token_claims_contain_correct_scope(
        self, client: AgentAuthClient, broker_url: str
    ) -> None:
        """Issued JWT contains the requested scope in its claims."""
        token: str = client.get_token("scope-agent", ["read:data:*"])
        result = _validate(broker_url, token)

        assert result["valid"] is True
        claims: dict[str, object] = result["claims"]  # type: ignore[assignment]
        assert "read:data:*" in claims["scope"]

    def test_token_sub_is_spiffe_format(
        self, client: AgentAuthClient, broker_url: str
    ) -> None:
        """Agent JWT subject is a SPIFFE ID (spiffe://agentauth.local/agent/...)."""
        token: str = client.get_token("spiffe-agent", ["read:data:*"])
        result = _validate(broker_url, token)

        claims: dict[str, object] = result["claims"]  # type: ignore[assignment]
        sub: str = str(claims["sub"])
        assert sub.startswith("spiffe://"), f"Expected SPIFFE sub, got: {sub}"
        assert "/agent/" in sub

    def test_task_id_and_orch_id_appear_in_claims(
        self, client: AgentAuthClient, broker_url: str
    ) -> None:
        """task_id and orch_id passed to get_token appear in the JWT claims."""
        token: str = client.get_token(
            "task-agent",
            ["read:data:*"],
            task_id="task-integration-001",
            orch_id="test-pipeline",
        )
        result = _validate(broker_url, token)

        claims: dict[str, object] = result["claims"]  # type: ignore[assignment]
        assert claims.get("task_id") == "task-integration-001"
        assert claims.get("orch_id") == "test-pipeline"


@pytest.mark.integration
class TestTokenCaching:
    """SDK-S3: Token caching -- second call returns cached token."""

    def test_second_call_returns_same_token(self, client: AgentAuthClient) -> None:
        """Two get_token calls with identical args return the same JWT string."""
        token1: str = client.get_token("cache-agent", ["read:data:*"])
        token2: str = client.get_token("cache-agent", ["read:data:*"])
        assert token1 == token2, "Expected cached token on second call"

    def test_different_scope_gets_different_token(self, client: AgentAuthClient) -> None:
        """Different scopes produce separate cache entries (scope is part of the key).

        Uses two read scopes to demonstrate cache isolation by scope key.
        """
        token_all: str = client.get_token("cache-key-agent", ["read:data:*"])
        token_narrow: str = client.get_token("cache-key-agent", ["read:data:logs"])
        assert token_all != token_narrow
