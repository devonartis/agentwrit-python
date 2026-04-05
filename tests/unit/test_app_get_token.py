"""Unit tests for AgentAuthApp.get_token().

Patch point: agentauth.app.requests.Session
No broker required -- all HTTP is mocked.

Key: _authenticate_app calls session.post() directly (not via _request).
     get_token calls _request() -> request_with_retry() -> session.request().
     Tests must configure session.post for init and session.request for get_token.

TDD order: tests written before get_token() implementation.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import requests as requests_lib

from agentauth.errors import ScopeCeilingError

# ---------------------------------------------------------------------------
# Fixtures / constants
# ---------------------------------------------------------------------------

BROKER_URL = "http://broker.example.com"
CLIENT_ID = "app-123"
CLIENT_SECRET = "super-secret"

# App auth response (POST /v1/app/auth)
APP_AUTH_200 = {
    "access_token": "app-jwt-token",
    "expires_in": 300,
    "token_type": "Bearer",
    "scopes": ["read:data:*", "write:data:*"],
}

# POST /v1/app/launch-tokens 201
LAUNCH_TOKEN_201 = {
    "launch_token": "a" * 64,
    "expires_at": "2026-03-07T00:05:00Z",
    "policy": {"allowed_scope": ["read:data:*"]},
}

# GET /v1/challenge 200
CHALLENGE_200 = {
    "nonce": "b" * 64,
    "expires_in": 30,
}

# POST /v1/register 200
REGISTER_200 = {
    "agent_id": "spiffe://cluster/ns/default/sa/my-agent",
    "access_token": "agent-jwt-token",
    "expires_in": 300,
}

# 403 scope violation (RFC 7807)
SCOPE_VIOLATION_403_BODY = {
    "type": "https://httpstatuses.com/403",
    "title": "Forbidden",
    "status": 403,
    "detail": "requested scope exceeds app ceiling",
    "error_code": "scope_violation",
}


# ---------------------------------------------------------------------------
# Helper -- build a mock response
# ---------------------------------------------------------------------------


def _make_mock_response(status_code: int, json_body: dict, ok: bool | None = None):
    """Return a mock requests.Response."""
    r = MagicMock(spec=requests_lib.Response)
    r.status_code = status_code
    r.json.return_value = json_body
    r.ok = ok if ok is not None else (200 <= status_code < 300)
    r.headers = {}
    return r


# ---------------------------------------------------------------------------
# Helper -- build a fully-wired client with the initial app auth mocked
# ---------------------------------------------------------------------------


def _make_client(session_instance):
    """Construct an AgentAuthApp against the provided session mock.

    _authenticate_app calls session.post() directly (not via _request).
    get_token calls _request -> request_with_retry -> session.request().

    This helper pre-configures session.post to return APP_AUTH_200 for the
    single __init__ app-auth call.  Tests then configure session.request
    for the subsequent get_token HTTP calls.
    """
    app_auth_resp = _make_mock_response(200, APP_AUTH_200)
    session_instance.post.return_value = app_auth_resp

    mock_session_cls = MagicMock(return_value=session_instance)

    with patch("agentauth.app.requests.Session", mock_session_cls):
        from agentauth.app import AgentAuthApp  # noqa: PLC0415

        client = AgentAuthApp(
            broker_url=BROKER_URL,
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        )

    return client


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestGetTokenSuccessFlow:
    """Happy path: three HTTP calls, token returned."""

    def test_returns_agent_access_token(self):
        """get_token() returns the access_token from /v1/register."""
        session = MagicMock()
        client = _make_client(session)

        launch_resp = _make_mock_response(201, LAUNCH_TOKEN_201)
        challenge_resp = _make_mock_response(200, CHALLENGE_200)
        register_resp = _make_mock_response(200, REGISTER_200)

        # get_token goes through _request -> request_with_retry -> session.request()
        session.request.side_effect = [launch_resp, challenge_resp, register_resp]

        token = client.get_token("my-agent", ["read:data:*"])

        assert token == "agent-jwt-token"

    def test_three_http_calls_made(self):
        """Exactly 3 session.request calls are made for a fresh get_token."""
        session = MagicMock()
        client = _make_client(session)
        session.request.reset_mock()

        launch_resp = _make_mock_response(201, LAUNCH_TOKEN_201)
        challenge_resp = _make_mock_response(200, CHALLENGE_200)
        register_resp = _make_mock_response(200, REGISTER_200)

        session.request.side_effect = [launch_resp, challenge_resp, register_resp]

        client.get_token("my-agent", ["read:data:*"])

        assert session.request.call_count == 3, (
            f"Expected 3 session.request calls, got {session.request.call_count}"
        )

    def test_launch_tokens_url(self):
        """POST /v1/app/launch-tokens is called with the correct URL (call 1)."""
        session = MagicMock()
        client = _make_client(session)
        session.request.reset_mock()

        launch_resp = _make_mock_response(201, LAUNCH_TOKEN_201)
        challenge_resp = _make_mock_response(200, CHALLENGE_200)
        register_resp = _make_mock_response(200, REGISTER_200)

        session.request.side_effect = [launch_resp, challenge_resp, register_resp]

        client.get_token("my-agent", ["read:data:*"])

        first_call = session.request.call_args_list[0]
        method = first_call[0][0]
        url = first_call[0][1]
        assert method == "POST"
        assert "/v1/app/launch-tokens" in url

    def test_challenge_url(self):
        """GET /v1/challenge is called with the correct URL (call 2)."""
        session = MagicMock()
        client = _make_client(session)
        session.request.reset_mock()

        launch_resp = _make_mock_response(201, LAUNCH_TOKEN_201)
        challenge_resp = _make_mock_response(200, CHALLENGE_200)
        register_resp = _make_mock_response(200, REGISTER_200)

        session.request.side_effect = [launch_resp, challenge_resp, register_resp]

        client.get_token("my-agent", ["read:data:*"])

        second_call = session.request.call_args_list[1]
        method = second_call[0][0]
        url = second_call[0][1]
        assert method == "GET"
        assert "/v1/challenge" in url

    def test_register_url(self):
        """POST /v1/register is called with the correct URL (call 3)."""
        session = MagicMock()
        client = _make_client(session)
        session.request.reset_mock()

        launch_resp = _make_mock_response(201, LAUNCH_TOKEN_201)
        challenge_resp = _make_mock_response(200, CHALLENGE_200)
        register_resp = _make_mock_response(200, REGISTER_200)

        session.request.side_effect = [launch_resp, challenge_resp, register_resp]

        client.get_token("my-agent", ["read:data:*"])

        third_call = session.request.call_args_list[2]
        method = third_call[0][0]
        url = third_call[0][1]
        assert method == "POST"
        assert "/v1/register" in url


class TestGetTokenPassthrough:
    """task_id and orch_id are passed through correctly."""

    def test_task_id_and_orch_id_in_register_body(self):
        """task_id and orch_id appear in the /v1/register request body."""
        session = MagicMock()
        client = _make_client(session)
        session.request.reset_mock()

        launch_resp = _make_mock_response(201, LAUNCH_TOKEN_201)
        challenge_resp = _make_mock_response(200, CHALLENGE_200)
        register_resp = _make_mock_response(200, REGISTER_200)

        session.request.side_effect = [launch_resp, challenge_resp, register_resp]

        client.get_token(
            "my-agent",
            ["read:data:*"],
            task_id="task-xyz",
            orch_id="orch-abc",
        )

        # /v1/register is the third call
        third_call = session.request.call_args_list[2]
        register_body = third_call[1].get("json") or third_call[0][2]

        assert register_body["task_id"] == "task-xyz"
        assert register_body["orch_id"] == "orch-abc"

    def test_register_body_has_launch_token_not_bearer_header(self):
        """POST /v1/register must have launch_token in body, NOT a Bearer header.

        The launch_token in the body authenticates /v1/register -- not a Bearer token.
        The Authorization header for this call must be absent.
        """
        session = MagicMock()
        client = _make_client(session)
        session.request.reset_mock()

        launch_resp = _make_mock_response(201, LAUNCH_TOKEN_201)
        challenge_resp = _make_mock_response(200, CHALLENGE_200)
        register_resp = _make_mock_response(200, REGISTER_200)

        session.request.side_effect = [launch_resp, challenge_resp, register_resp]

        client.get_token("my-agent", ["read:data:*"])

        third_call = session.request.call_args_list[2]
        register_body = third_call[1].get("json") or third_call[0][2]
        register_headers = third_call[1].get("headers", {})

        # launch_token is in the body
        assert "launch_token" in register_body
        assert register_body["launch_token"] == LAUNCH_TOKEN_201["launch_token"]

        # No Bearer token sent for /v1/register
        assert "Authorization" not in register_headers


class TestGetTokenErrors:
    """Error cases: scope violation 403."""

    def test_scope_violation_403_raises_scope_ceiling_error(self):
        """A 403 scope_violation response raises ScopeCeilingError."""
        session = MagicMock()
        client = _make_client(session)
        session.request.reset_mock()

        scope_resp = _make_mock_response(403, SCOPE_VIOLATION_403_BODY, ok=False)
        session.request.return_value = scope_resp

        with pytest.raises(ScopeCeilingError):
            client.get_token("my-agent", ["admin:data:*"])


class TestGetTokenCache:
    """Cache hit: second call does NOT make additional HTTP requests."""

    def test_cache_hit_skips_http(self):
        """Second call with same agent_name+scope returns cached token without HTTP."""
        session = MagicMock()
        client = _make_client(session)
        session.request.reset_mock()

        launch_resp = _make_mock_response(201, LAUNCH_TOKEN_201)
        challenge_resp = _make_mock_response(200, CHALLENGE_200)
        register_resp = _make_mock_response(200, REGISTER_200)

        session.request.side_effect = [launch_resp, challenge_resp, register_resp]

        # First call -- populates cache
        token1 = client.get_token("my-agent", ["read:data:*"])
        assert token1 == "agent-jwt-token"

        request_count_after_first = session.request.call_count
        assert request_count_after_first == 3

        # Second call with same args -- must hit cache, no HTTP
        token2 = client.get_token("my-agent", ["read:data:*"])
        assert token2 == "agent-jwt-token"

        assert session.request.call_count == request_count_after_first, (
            "Second call must NOT make additional HTTP requests (cache hit)"
        )

    def test_cache_stores_correct_token(self):
        """Token stored in cache matches what get_token() returned."""
        session = MagicMock()
        client = _make_client(session)
        session.request.reset_mock()

        launch_resp = _make_mock_response(201, LAUNCH_TOKEN_201)
        challenge_resp = _make_mock_response(200, CHALLENGE_200)
        register_resp = _make_mock_response(200, REGISTER_200)

        session.request.side_effect = [launch_resp, challenge_resp, register_resp]

        token = client.get_token("my-agent", ["read:data:*"])

        cached = client._token_cache.get("my-agent", ["read:data:*"])
        assert cached == token == "agent-jwt-token"
