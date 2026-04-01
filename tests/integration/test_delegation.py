"""Integration tests: delegation flow (SDK-S7).

Verifies that an agent can delegate a SUBSET of its scope to another registered
agent via POST /v1/delegate. The broker enforces scope attenuation -- you cannot
delegate more scope than you hold.

Story: SDK-S7 (Developer creates a delegation token)
See: tests/sdk-core/user-stories.md

Requires: AGENTAUTH_CLIENT_ID, AGENTAUTH_CLIENT_SECRET set.
"""

from __future__ import annotations

import pytest
import requests as requests_lib

from agentauth import AgentAuthClient
from agentauth.errors import ScopeCeilingError


@pytest.mark.integration
class TestDelegation:
    """SDK-S7: Delegation -- agent grants attenuated scope to another agent."""

    def test_delegate_returns_attenuated_token(
        self, client: AgentAuthClient, broker_url: str
    ) -> None:
        """Delegated JWT has the requested attenuated scope.

        Uses read:data:* as the delegator scope. Scope attenuation is
        demonstrated by delegating read:data:results (a narrower subset).
        """
        agent_token: str = client.get_token("delegator-agent", ["read:data:*"])

        # Validate to get agent_id (SPIFFE ID) for the delegate
        validate_resp = requests_lib.post(
            f"{broker_url}/v1/token/validate",
            json={"token": agent_token},
            timeout=10,
        )
        assert validate_resp.status_code == 200
        delegator_claims: dict[str, object] = validate_resp.json()["claims"]  # type: ignore[assignment]

        # Register a second agent to receive the delegation
        delegate_token: str = client.get_token(
            "delegate-agent",
            ["read:data:*"],
            task_id="delegate-task",
            orch_id="delegation-test",
        )
        delegate_validate = requests_lib.post(
            f"{broker_url}/v1/token/validate",
            json={"token": delegate_token},
            timeout=10,
        )
        delegate_claims: dict[str, object] = delegate_validate.json()["claims"]  # type: ignore[assignment]
        delegate_agent_id: str = str(delegate_claims["sub"])

        # Delegate read:data:results (subset of write:data:*)
        delegated: str = client.delegate(
            token=agent_token,
            to_agent_id=delegate_agent_id,
            scope=["read:data:results"],
            ttl=60,
        )
        assert isinstance(delegated, str)
        assert len(delegated.split(".")) == 3

        # Validate delegated token -- scope must be attenuated
        delegated_result = requests_lib.post(
            f"{broker_url}/v1/token/validate",
            json={"token": delegated},
            timeout=10,
        )
        assert delegated_result.status_code == 200
        delegated_claims: dict[str, object] = delegated_result.json()["claims"]  # type: ignore[assignment]
        assert "read:data:results" in delegated_claims["scope"]
        # Must NOT have read:data:* -- scope was attenuated to the narrower subset
        assert "read:data:*" not in delegated_claims["scope"]
