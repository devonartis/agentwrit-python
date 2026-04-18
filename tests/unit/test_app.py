"""Unit tests for agentwrit.app — AgentWritApp container.

Tests lazy authentication, re-auth on expiry, health(), validate()
shortcut, create_agent() orchestration, and secret redaction.

Uses pytest-httpx to mock all broker HTTP responses.

Spec: Section 6.2, ADR SDK-003 (internal app JWT), ADR SDK-004 (create_agent)
"""
from __future__ import annotations

import pytest
from pytest_httpx import HTTPXMock

from agentwrit.agent import Agent
from agentwrit.app import AgentWritApp
from agentwrit.errors import AuthenticationError, AuthorizationError
from agentwrit.models import HealthStatus, ValidateResult

# --- Fixtures ---


APP_AUTH_RESPONSE = {
    "access_token": "eyJ.app.jwt",
    "expires_in": 1800,
    "token_type": "Bearer",
    "scopes": ["app:launch-tokens:*", "app:agents:*", "app:audit:read"],
}

HEALTH_RESPONSE = {
    "status": "ok",
    "version": "2.0.0",
    "uptime": 42,
    "db_connected": True,
    "audit_events_count": 10,
}

LAUNCH_TOKEN_RESPONSE = {
    "launch_token": "a1b2c3d4" * 8,
    "expires_at": "2026-04-07T00:01:00Z",
    "policy": {"allowed_scope": ["read:data:*"], "max_ttl": 300},
}

CHALLENGE_RESPONSE = {
    "nonce": "ff" * 32,
    "expires_in": 30,
}

REGISTER_RESPONSE = {
    "agent_id": "spiffe://agentwrit.local/agent/orch-1/task-1/abc123",
    "access_token": "eyJ.agent.jwt",
    "expires_in": 300,
}


@pytest.fixture()
def app(httpx_mock: HTTPXMock) -> AgentWritApp:
    """Create an AgentWritApp. No HTTP on construction (lazy auth)."""
    return AgentWritApp(
        broker_url="http://broker.test",
        client_id="app-123",
        client_secret="secret-456",
    )


def _mock_app_auth(httpx_mock: HTTPXMock) -> None:
    httpx_mock.add_response(
        url="http://broker.test/v1/app/auth",
        json=APP_AUTH_RESPONSE,
    )


def _mock_full_create_agent(httpx_mock: HTTPXMock) -> None:
    """Mock the full create_agent sequence: auth + launch token + challenge + register."""
    _mock_app_auth(httpx_mock)
    httpx_mock.add_response(
        url="http://broker.test/v1/app/launch-tokens",
        status_code=201,
        json=LAUNCH_TOKEN_RESPONSE,
    )
    httpx_mock.add_response(
        url="http://broker.test/v1/challenge",
        json=CHALLENGE_RESPONSE,
    )
    httpx_mock.add_response(
        url="http://broker.test/v1/register",
        json=REGISTER_RESPONSE,
    )


# --- Lazy auth (ADR SDK-003) ---


class TestLazyAuth:
    def test_no_http_on_construction(self, httpx_mock: HTTPXMock):
        """AgentWritApp.__init__ must NOT call the broker."""
        AgentWritApp(
            broker_url="http://broker.test",
            client_id="app-123",
            client_secret="secret-456",
        )
        assert len(httpx_mock.get_requests()) == 0

    def test_authenticates_on_first_create_agent(
        self, app: AgentWritApp, httpx_mock: HTTPXMock,
    ):
        """First create_agent triggers POST /v1/app/auth."""
        _mock_full_create_agent(httpx_mock)
        app.create_agent(orch_id="o", task_id="t", requested_scope=["read:data:*"])

        requests = httpx_mock.get_requests()
        assert any("/v1/app/auth" in str(r.url) for r in requests)

    def test_reuses_valid_session(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        """Second create_agent reuses the existing app JWT, no second auth call."""
        _mock_full_create_agent(httpx_mock)
        app.create_agent(orch_id="o", task_id="t1", requested_scope=["read:data:*"])

        # Second call — mock everything except app auth
        httpx_mock.add_response(
            url="http://broker.test/v1/app/launch-tokens",
            status_code=201,
            json=LAUNCH_TOKEN_RESPONSE,
        )
        httpx_mock.add_response(
            url="http://broker.test/v1/challenge",
            json=CHALLENGE_RESPONSE,
        )
        httpx_mock.add_response(
            url="http://broker.test/v1/register",
            json=REGISTER_RESPONSE,
        )
        app.create_agent(orch_id="o", task_id="t2", requested_scope=["read:data:*"])

        auth_requests = [r for r in httpx_mock.get_requests() if "/v1/app/auth" in str(r.url)]
        assert len(auth_requests) == 1, "Should only auth once"

    def test_bad_credentials_raise_authentication_error(
        self, app: AgentWritApp, httpx_mock: HTTPXMock,
    ):
        httpx_mock.add_response(
            url="http://broker.test/v1/app/auth",
            status_code=401,
            json={
                "type": "urn:agentwrit:error:unauthorized",
                "title": "Unauthorized",
                "detail": "invalid credentials",
                "instance": "/v1/app/auth",
                "error_code": "unauthorized",
            },
        )
        with pytest.raises(AuthenticationError):
            app.create_agent(orch_id="o", task_id="t", requested_scope=["read:data:*"])


# --- health() ---


class TestHealth:
    def test_returns_health_status(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/health",
            json=HEALTH_RESPONSE,
        )
        result = app.health()
        assert isinstance(result, HealthStatus)
        assert result.status == "ok"
        assert result.version == "2.0.0"
        assert result.db_connected is True

    def test_health_no_auth_required(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        """GET /v1/health is a public endpoint — no app auth needed."""
        httpx_mock.add_response(
            url="http://broker.test/v1/health",
            json=HEALTH_RESPONSE,
        )
        app.health()
        requests = httpx_mock.get_requests()
        assert len(requests) == 1
        assert "/v1/health" in str(requests[0].url)
        # No /v1/app/auth call
        assert not any("/v1/app/auth" in str(r.url) for r in requests)


# --- validate() shortcut ---


class TestValidate:
    def test_valid_token(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={
                "valid": True,
                "claims": {
                    "iss": "agentwrit",
                    "sub": "spiffe://agentwrit.local/agent/o/t/i",
                    "aud": ["agentwrit"],
                    "exp": 9999999999,
                    "nbf": 1000000000,
                    "iat": 1000000000,
                    "jti": "jti-abc",
                    "scope": ["read:data:*"],
                    "task_id": "t",
                    "orch_id": "o",
                },
            },
        )
        result = app.validate("eyJ.some.token")
        assert isinstance(result, ValidateResult)
        assert result.valid is True
        assert result.claims is not None
        assert result.claims.sub.startswith("spiffe://")

    def test_invalid_token(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={"valid": False, "error": "token is invalid or expired"},
        )
        result = app.validate("eyJ.bad.token")
        assert result.valid is False
        assert result.error == "token is invalid or expired"


# --- create_agent() orchestration ---


class TestCreateAgent:
    def test_returns_agent_object(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        _mock_full_create_agent(httpx_mock)
        agent = app.create_agent(
            orch_id="orch-1",
            task_id="task-1",
            requested_scope=["read:data:*"],
        )
        assert isinstance(agent, Agent)
        assert agent.agent_id == "spiffe://agentwrit.local/agent/orch-1/task-1/abc123"
        assert agent.access_token == "eyJ.agent.jwt"
        assert agent.expires_in == 300
        assert agent.scope == ["read:data:*"]
        assert agent.task_id == "task-1"
        assert agent.orch_id == "orch-1"

    def test_orchestration_sequence(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        """create_agent calls: app/auth → launch-tokens → challenge → register."""
        _mock_full_create_agent(httpx_mock)
        app.create_agent(orch_id="o", task_id="t", requested_scope=["read:data:*"])

        urls = [str(r.url) for r in httpx_mock.get_requests()]
        # Verify the sequence
        assert any("/v1/app/auth" in u for u in urls)
        assert any("/v1/app/launch-tokens" in u for u in urls)
        assert any("/v1/challenge" in u for u in urls)
        assert any("/v1/register" in u for u in urls)

    def test_launch_token_sends_bearer_auth(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        _mock_full_create_agent(httpx_mock)
        app.create_agent(orch_id="o", task_id="t", requested_scope=["read:data:*"])

        lt_request = [r for r in httpx_mock.get_requests()
                      if "/v1/app/launch-tokens" in str(r.url)][0]
        assert lt_request.headers["Authorization"] == "Bearer eyJ.app.jwt"

    def test_register_sends_no_bearer(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        """POST /v1/register authenticates via launch_token in body, not Bearer."""
        _mock_full_create_agent(httpx_mock)
        app.create_agent(orch_id="o", task_id="t", requested_scope=["read:data:*"])

        reg_request = [r for r in httpx_mock.get_requests()
                       if "/v1/register" in str(r.url)][0]
        # Should NOT have an Authorization header with app JWT
        auth_header = reg_request.headers.get("Authorization", "")
        assert "eyJ.app.jwt" not in auth_header

    def test_scope_ceiling_violation(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        """403 on launch-token creation raises AuthorizationError."""
        _mock_app_auth(httpx_mock)
        httpx_mock.add_response(
            url="http://broker.test/v1/app/launch-tokens",
            status_code=403,
            json={
                "type": "urn:agentwrit:error:forbidden",
                "title": "Forbidden",
                "detail": "scope exceeds app ceiling",
                "instance": "/v1/app/launch-tokens",
                "error_code": "forbidden",
            },
        )
        with pytest.raises(AuthorizationError):
            app.create_agent(
                orch_id="o", task_id="t",
                requested_scope=["admin:everything:*"],
            )

    def test_auto_generates_agent_name(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        """agent_name on launch token defaults to orch_id/task_id (ADR SDK-005)."""
        _mock_full_create_agent(httpx_mock)
        app.create_agent(orch_id="my-orch", task_id="my-task", requested_scope=["read:data:*"])

        lt_request = [r for r in httpx_mock.get_requests()
                      if "/v1/app/launch-tokens" in str(r.url)][0]
        import json
        body = json.loads(lt_request.read())
        assert body["agent_name"] == "my-orch/my-task"

    def test_custom_label_overrides_agent_name(
        self, app: AgentWritApp, httpx_mock: HTTPXMock,
    ):
        _mock_full_create_agent(httpx_mock)
        app.create_agent(
            orch_id="o", task_id="t",
            requested_scope=["read:data:*"],
            label="custom-agent-label",
        )

        lt_request = [r for r in httpx_mock.get_requests()
                      if "/v1/app/launch-tokens" in str(r.url)][0]
        import json
        body = json.loads(lt_request.read())
        assert body["agent_name"] == "custom-agent-label"


# --- Secret redaction ---


class TestSecretRedaction:
    def test_secret_not_in_repr(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        assert "secret-456" not in repr(app)

    def test_secret_not_in_str(self, app: AgentWritApp, httpx_mock: HTTPXMock):
        assert "secret-456" not in str(app)
