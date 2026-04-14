"""Unit tests for agentwrit.agent — Agent lifecycle methods.

TDD: tests written before implementation for renew(), release(), delegate().
Uses pytest-httpx to mock broker responses via the transport layer.

Spec references:
- renew(): Section 6.3, ADR SDK-008 (mutates in-place)
- release(): Section 6.3 (broker returns 204, agent marked released)
- delegate(): Section 6.3 (returns DelegatedToken with chain)
- No validate() on Agent: ADR SDK-006
"""
from __future__ import annotations

from unittest.mock import MagicMock

import pytest
from pytest_httpx import HTTPXMock

from agentwrit._transport import AgentWritTransport
from agentwrit.agent import Agent
from agentwrit.app import AgentWritApp
from agentwrit.errors import AgentWritError
from agentwrit.models import DelegatedToken


def _make_agent(httpx_mock: HTTPXMock) -> Agent:
    """Create an Agent with a mocked transport for unit testing."""
    # Mock app auth so AgentWritApp can be constructed
    app = MagicMock(spec=AgentWritApp)
    app._transport = AgentWritTransport(broker_url="http://broker.test", timeout=5.0)
    app.broker_url = "http://broker.test"
    app.timeout = 5.0

    return Agent(
        app=app,
        agent_id="spiffe://agentwrit.local/agent/orch/task/abc123",
        access_token="eyJ.original.token",
        expires_in=300,
        scope=["read:data:*"],
        task_id="task-1",
        orch_id="orch-1",
    )


# --- bearer_header ---


class TestBearerHeader:
    def test_returns_authorization_header(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        assert agent.bearer_header == {"Authorization": "Bearer eyJ.original.token"}


# --- renew() ---


class TestRenew:
    def test_updates_access_token_in_place(self, httpx_mock: HTTPXMock):
        """ADR SDK-008: renew mutates the Agent in-place."""
        agent = _make_agent(httpx_mock)
        old_token = agent.access_token

        httpx_mock.add_response(
            url="http://broker.test/v1/token/renew",
            json={"access_token": "eyJ.renewed.token", "expires_in": 300},
        )

        agent.renew()

        assert agent.access_token == "eyJ.renewed.token"
        assert agent.access_token != old_token
        assert agent.expires_in == 300

    def test_agent_id_unchanged_after_renew(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        original_id = agent.agent_id

        httpx_mock.add_response(
            url="http://broker.test/v1/token/renew",
            json={"access_token": "eyJ.new", "expires_in": 300},
        )

        agent.renew()
        assert agent.agent_id == original_id

    def test_scope_unchanged_after_renew(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/token/renew",
            json={"access_token": "eyJ.new", "expires_in": 300},
        )
        agent.renew()
        assert agent.scope == ["read:data:*"]

    def test_renew_sends_bearer_auth(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/token/renew",
            json={"access_token": "eyJ.new", "expires_in": 300},
        )
        agent.renew()
        request = httpx_mock.get_request()
        assert request is not None
        assert request.headers["Authorization"] == "Bearer eyJ.original.token"

    def test_renew_after_release_raises_error(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        # Release the agent first
        httpx_mock.add_response(
            url="http://broker.test/v1/token/release",
            status_code=204,
        )
        agent.release()

        with pytest.raises(AgentWritError, match="released"):
            agent.renew()


# --- release() ---


class TestRelease:
    def test_release_calls_broker(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/token/release",
            status_code=204,
        )
        agent.release()

        request = httpx_mock.get_request()
        assert request is not None
        assert request.method == "POST"
        assert "/v1/token/release" in str(request.url)

    def test_release_sends_bearer_auth(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/token/release",
            status_code=204,
        )
        agent.release()

        request = httpx_mock.get_request()
        assert request is not None
        assert request.headers["Authorization"] == "Bearer eyJ.original.token"

    def test_release_marks_agent_released(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/token/release",
            status_code=204,
        )
        agent.release()
        assert agent._released is True

    def test_release_idempotent(self, httpx_mock: HTTPXMock):
        """Second release() is a no-op, no HTTP call."""
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/token/release",
            status_code=204,
        )
        agent.release()
        # Second call should not raise or make another HTTP request
        agent.release()
        # Only one request should have been made
        assert len(httpx_mock.get_requests()) == 1


# --- delegate() ---


class TestDelegate:
    def test_returns_delegated_token(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/delegate",
            json={
                "access_token": "eyJ.delegated",
                "expires_in": 60,
                "delegation_chain": [
                    {
                        "agent": "spiffe://agentwrit.local/agent/orch/task/abc123",
                        "scope": ["read:data:*"],
                        "delegated_at": "2026-04-07T00:00:00Z",
                    }
                ],
            },
        )

        result = agent.delegate(
            delegate_to="spiffe://agentwrit.local/agent/orch/task/def456",
            scope=["read:data:customers"],
        )

        assert isinstance(result, DelegatedToken)
        assert result.access_token == "eyJ.delegated"
        assert result.expires_in == 60
        assert len(result.delegation_chain) == 1
        assert result.delegation_chain[0].agent.endswith("abc123")

    def test_delegate_sends_correct_body(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/delegate",
            json={
                "access_token": "eyJ.d",
                "expires_in": 60,
                "delegation_chain": [],
            },
        )
        agent.delegate(
            delegate_to="spiffe://target",
            scope=["read:data:customers"],
            ttl=120,
        )

        request = httpx_mock.get_request()
        assert request is not None
        body = request.read()
        import json
        data = json.loads(body)
        assert data["delegate_to"] == "spiffe://target"
        assert data["scope"] == ["read:data:customers"]
        assert data["ttl"] == 120

    def test_delegate_sends_bearer_auth(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/delegate",
            json={"access_token": "x", "expires_in": 60, "delegation_chain": []},
        )
        agent.delegate(delegate_to="spiffe://t", scope=["s"])

        request = httpx_mock.get_request()
        assert request is not None
        assert request.headers["Authorization"] == "Bearer eyJ.original.token"

    def test_delegate_after_release_raises_error(self, httpx_mock: HTTPXMock):
        agent = _make_agent(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/token/release",
            status_code=204,
        )
        agent.release()

        with pytest.raises(AgentWritError, match="released"):
            agent.delegate(delegate_to="spiffe://t", scope=["s"])


# --- No validate() on Agent (ADR SDK-006) ---


class TestNoValidate:
    def test_agent_has_no_validate_method(self, httpx_mock: HTTPXMock):
        """ADR SDK-006: agents cannot validate themselves."""
        agent = _make_agent(httpx_mock)
        assert not hasattr(agent, "validate")
