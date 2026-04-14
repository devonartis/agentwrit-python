"""Unit tests for agentwrit._transport — HTTP transport + RFC 7807 error dispatch.

Uses pytest-httpx to mock httpx.Client responses. Tests verify that:
- Successful responses are returned as-is
- RFC 7807 error bodies are parsed into ProblemDetail
- HTTP status codes dispatch to correct exception types
- Network failures raise TransportError
"""
from __future__ import annotations

import httpx
import pytest
from pytest_httpx import HTTPXMock

from agentwrit._transport import AgentWritTransport
from agentwrit.errors import (
    AuthenticationError,
    AuthorizationError,
    ProblemResponseError,
    RateLimitError,
    TransportError,
)


@pytest.fixture()
def transport() -> AgentWritTransport:
    return AgentWritTransport(broker_url="http://broker.test", timeout=5.0)


# --- Success path ---


class TestSuccessResponse:
    def test_returns_response_on_200(self, transport: AgentWritTransport, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/health",
            json={"status": "ok", "version": "2.0.0", "uptime": 42,
                  "db_connected": True, "audit_events_count": 0},
        )
        resp = transport.request("GET", "/v1/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"

    def test_returns_response_on_201(self, transport: AgentWritTransport, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/app/launch-tokens",
            status_code=201,
            json={"launch_token": "abc123", "expires_at": "2026-04-07T00:00:00Z"},
        )
        resp = transport.request("POST", "/v1/app/launch-tokens", json={"agent_name": "a"})
        assert resp.status_code == 201

    def test_returns_response_on_204(self, transport: AgentWritTransport, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/release",
            status_code=204,
        )
        resp = transport.request("POST", "/v1/token/release")
        assert resp.status_code == 204


# --- RFC 7807 error dispatch ---


class TestErrorDispatch:
    def _problem_json(self, status: int, error_code: str, detail: str) -> dict[str, object]:
        return {
            "type": f"urn:agentwrit:error:{error_code}",
            "title": "Error",
            "status": status,
            "detail": detail,
            "instance": "/v1/test",
            "error_code": error_code,
        }

    def test_401_raises_authentication_error(
        self, transport: AgentWritTransport, httpx_mock: HTTPXMock,
    ):
        httpx_mock.add_response(
            url="http://broker.test/v1/app/auth",
            status_code=401,
            json=self._problem_json(401, "unauthorized", "invalid credentials"),
        )
        with pytest.raises(AuthenticationError) as exc_info:
            transport.request("POST", "/v1/app/auth")
        assert exc_info.value.status_code == 401
        assert exc_info.value.problem.error_code == "unauthorized"

    def test_403_raises_authorization_error(
        self, transport: AgentWritTransport, httpx_mock: HTTPXMock,
    ):
        httpx_mock.add_response(
            url="http://broker.test/v1/app/launch-tokens",
            status_code=403,
            json=self._problem_json(403, "forbidden", "scope exceeds ceiling"),
        )
        with pytest.raises(AuthorizationError) as exc_info:
            transport.request("POST", "/v1/app/launch-tokens")
        assert exc_info.value.status_code == 403
        assert "scope exceeds ceiling" in exc_info.value.problem.detail

    def test_429_raises_rate_limit_error(
        self, transport: AgentWritTransport, httpx_mock: HTTPXMock,
    ):
        httpx_mock.add_response(
            url="http://broker.test/v1/app/auth",
            status_code=429,
            json=self._problem_json(429, "rate_limited", "rate limit exceeded"),
        )
        with pytest.raises(RateLimitError) as exc_info:
            transport.request("POST", "/v1/app/auth")
        assert exc_info.value.status_code == 429

    def test_400_raises_problem_response_error(
        self, transport: AgentWritTransport, httpx_mock: HTTPXMock,
    ):
        httpx_mock.add_response(
            url="http://broker.test/v1/register",
            status_code=400,
            json=self._problem_json(400, "invalid_request", "missing field"),
        )
        with pytest.raises(ProblemResponseError) as exc_info:
            transport.request("POST", "/v1/register")
        assert exc_info.value.status_code == 400

    def test_500_raises_problem_response_error(
        self, transport: AgentWritTransport, httpx_mock: HTTPXMock,
    ):
        httpx_mock.add_response(
            url="http://broker.test/v1/register",
            status_code=500,
            json=self._problem_json(500, "internal_error", "unexpected failure"),
        )
        with pytest.raises(ProblemResponseError) as exc_info:
            transport.request("POST", "/v1/register")
        assert exc_info.value.status_code == 500


# --- ProblemDetail parsing ---


class TestProblemDetailParsing:
    def test_parses_all_rfc7807_fields(
        self, transport: AgentWritTransport, httpx_mock: HTTPXMock,
    ):
        httpx_mock.add_response(
            url="http://broker.test/v1/app/auth",
            status_code=401,
            json={
                "type": "urn:agentwrit:error:unauthorized",
                "title": "Unauthorized",
                "status": 401,
                "detail": "invalid client credentials",
                "instance": "/v1/app/auth",
                "error_code": "unauthorized",
                "request_id": "abc123",
                "hint": "check your client_secret",
            },
        )
        with pytest.raises(AuthenticationError) as exc_info:
            transport.request("POST", "/v1/app/auth")
        problem = exc_info.value.problem
        assert problem.type == "urn:agentwrit:error:unauthorized"
        assert problem.title == "Unauthorized"
        assert problem.detail == "invalid client credentials"
        assert problem.instance == "/v1/app/auth"
        assert problem.error_code == "unauthorized"
        assert problem.request_id == "abc123"
        assert problem.hint == "check your client_secret"

    def test_handles_non_json_error_body(
        self, transport: AgentWritTransport, httpx_mock: HTTPXMock,
    ):
        httpx_mock.add_response(
            url="http://broker.test/v1/app/auth",
            status_code=502,
            text="Bad Gateway",
        )
        with pytest.raises(ProblemResponseError) as exc_info:
            transport.request("POST", "/v1/app/auth")
        assert exc_info.value.status_code == 502
        assert "Bad Gateway" in exc_info.value.problem.detail


# --- Network failures ---


class TestTransportErrors:
    def test_connection_refused_raises_transport_error(
        self, httpx_mock: HTTPXMock,
    ):
        transport = AgentWritTransport(broker_url="http://unreachable.test:9999", timeout=0.1)
        httpx_mock.add_exception(
            httpx.ConnectError("Connection refused"),
            url="http://unreachable.test:9999/v1/health",
        )
        with pytest.raises(TransportError) as exc_info:
            transport.request("GET", "/v1/health")
        assert "broker unreachable" in str(exc_info.value)

    def test_timeout_raises_transport_error(
        self, httpx_mock: HTTPXMock,
    ):
        transport = AgentWritTransport(broker_url="http://slow.test", timeout=0.1)
        httpx_mock.add_exception(
            httpx.ReadTimeout("Read timed out"),
            url="http://slow.test/v1/health",
        )
        with pytest.raises(TransportError):
            transport.request("GET", "/v1/health")


# --- Headers ---


class TestHeaders:
    def test_passes_custom_headers(
        self, transport: AgentWritTransport, httpx_mock: HTTPXMock,
    ):
        httpx_mock.add_response(url="http://broker.test/v1/token/renew", json={})
        transport.request(
            "POST", "/v1/token/renew",
            headers={"Authorization": "Bearer eyJ..."},
        )
        request = httpx_mock.get_request()
        assert request is not None
        assert request.headers["Authorization"] == "Bearer eyJ..."
