"""Unit tests for AgentAuthClient.delegate, revoke_token, validate_token.

Patch point: agentauth.client.requests.Session
No broker required -- all HTTP is mocked.

TDD order: these tests are written before the methods exist in client.py.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUTH_200 = {
    "access_token": "app.jwt.token",
    "expires_in": 300,
    "token_type": "Bearer",
}

AGENT_TOKEN = "agent.jwt.token"


def _make_response(status_code: int, json_body: dict | None = None) -> MagicMock:
    """Return a mock requests.Response."""
    resp = MagicMock()
    resp.status_code = status_code
    if json_body is not None:
        resp.json.return_value = json_body
    return resp


def _make_client(session: MagicMock):
    """Construct an AgentAuthClient with a pre-wired mock session.

    The session mock must already be set up so that .post() returns a 200
    app-auth response (so __init__ doesn't blow up).
    """
    from agentauth.client import AgentAuthClient  # noqa: PLC0415

    return AgentAuthClient(
        broker_url="http://broker.example.com",
        client_id="app-123",
        client_secret="super-secret",
    )


def _make_session_cls_and_instance(extra_responses: list[MagicMock] | None = None):
    """
    Return (mock_session_cls, mock_session_instance).

    mock_session_instance.post() returns AUTH_200 on the first call (app auth),
    then returns responses from extra_responses in order for subsequent calls.
    mock_session_instance.request() returns responses from extra_responses in order.
    """
    auth_resp = _make_response(200, AUTH_200)

    mock_session_instance = MagicMock()
    # post() is used for app auth in __init__; subsequent SDK calls use request()
    mock_session_instance.post.return_value = auth_resp

    if extra_responses:
        mock_session_instance.request.side_effect = list(extra_responses)

    mock_session_cls = MagicMock(return_value=mock_session_instance)
    return mock_session_cls, mock_session_instance


# ---------------------------------------------------------------------------
# delegate() tests
# ---------------------------------------------------------------------------


class TestDelegate:
    """delegate() calls POST /v1/delegate with agent JWT and returns access_token."""

    DELEGATE_200 = {
        "access_token": "delegated.jwt.token",
        "expires_in": 60,
        "delegation_chain": ["spiffe://trust-domain/app", "spiffe://trust-domain/agent-b"],
    }

    def test_delegate_returns_access_token(self):
        """delegate() must return the access_token string from the broker response."""
        delegate_resp = _make_response(200, self.DELEGATE_200)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([delegate_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            result = client.delegate(
                token=AGENT_TOKEN,
                to_agent_id="spiffe://trust-domain/agent-b",
                scope=["read:data:*"],
                ttl=60,
            )

        assert result == "delegated.jwt.token"

    def test_delegate_calls_v1_delegate_endpoint(self):
        """delegate() must call POST /v1/delegate."""
        delegate_resp = _make_response(200, self.DELEGATE_200)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([delegate_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            client.delegate(
                token=AGENT_TOKEN,
                to_agent_id="spiffe://trust-domain/agent-b",
                scope=["read:data:*"],
                ttl=60,
            )

        call_args = mock_session_instance.request.call_args
        url = call_args[0][1] if call_args[0] else call_args[1].get("url", "")
        assert "/v1/delegate" in url

    def test_delegate_passes_correct_body(self):
        """delegate() must send delegate_to, scope, and ttl in the request body."""
        delegate_resp = _make_response(200, self.DELEGATE_200)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([delegate_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            client.delegate(
                token=AGENT_TOKEN,
                to_agent_id="spiffe://trust-domain/agent-b",
                scope=["read:data:*"],
                ttl=90,
            )

        call_kwargs = mock_session_instance.request.call_args[1]
        body = call_kwargs.get("json", {})
        assert body["delegate_to"] == "spiffe://trust-domain/agent-b"
        assert body["scope"] == ["read:data:*"]
        assert body["ttl"] == 90

    def test_delegate_sets_authorization_bearer_header(self):
        """delegate() must pass the agent JWT as Authorization: Bearer in the request."""
        delegate_resp = _make_response(200, self.DELEGATE_200)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([delegate_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            client.delegate(
                token=AGENT_TOKEN,
                to_agent_id="spiffe://trust-domain/agent-b",
                scope=["read:data:*"],
                ttl=60,
            )

        call_kwargs = mock_session_instance.request.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert headers.get("Authorization") == f"Bearer {AGENT_TOKEN}"


# ---------------------------------------------------------------------------
# revoke_token() tests
# ---------------------------------------------------------------------------


class TestRevokeToken:
    """revoke_token() calls POST /v1/token/release with agent JWT, returns None on 204."""

    def test_revoke_token_succeeds_on_204(self):
        """revoke_token() must return None (no exception) when broker responds 204."""
        revoke_resp = _make_response(204)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([revoke_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            result = client.revoke_token(token=AGENT_TOKEN)

        assert result is None

    def test_revoke_token_calls_v1_token_release_endpoint(self):
        """revoke_token() must call POST /v1/token/release."""
        revoke_resp = _make_response(204)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([revoke_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            client.revoke_token(token=AGENT_TOKEN)

        call_args = mock_session_instance.request.call_args
        url = call_args[0][1] if call_args[0] else call_args[1].get("url", "")
        assert "/v1/token/release" in url

    def test_revoke_token_sets_authorization_bearer_header(self):
        """revoke_token() must pass the agent JWT as Authorization: Bearer."""
        revoke_resp = _make_response(204)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([revoke_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            client.revoke_token(token=AGENT_TOKEN)

        call_kwargs = mock_session_instance.request.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert headers.get("Authorization") == f"Bearer {AGENT_TOKEN}"


# ---------------------------------------------------------------------------
# validate_token() tests
# ---------------------------------------------------------------------------


class TestValidateToken:
    """validate_token() calls POST /v1/token/validate (no auth) and returns full dict."""

    VALIDATE_200_VALID = {
        "valid": True,
        "claims": {
            "sub": "spiffe://trust-domain/agent-a",
            "scope": ["read:data:*"],
            "exp": 9999999999,
        },
    }

    VALIDATE_200_INVALID = {
        "valid": False,
        "error": "token expired",
    }

    def test_validate_token_returns_full_response_dict(self):
        """validate_token() must return the complete response dict from the broker."""
        validate_resp = _make_response(200, self.VALIDATE_200_VALID)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([validate_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            result = client.validate_token(token="some.jwt.string")

        assert result == self.VALIDATE_200_VALID
        assert result["valid"] is True
        assert "claims" in result

    def test_validate_token_calls_v1_token_validate_endpoint(self):
        """validate_token() must call POST /v1/token/validate."""
        validate_resp = _make_response(200, self.VALIDATE_200_VALID)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([validate_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            client.validate_token(token="some.jwt.string")

        call_args = mock_session_instance.request.call_args
        url = call_args[0][1] if call_args[0] else call_args[1].get("url", "")
        assert "/v1/token/validate" in url

    def test_validate_token_sends_token_in_body(self):
        """validate_token() must send {"token": jwt_string} in the request body."""
        validate_resp = _make_response(200, self.VALIDATE_200_VALID)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([validate_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            client.validate_token(token="some.jwt.string")

        call_kwargs = mock_session_instance.request.call_args[1]
        body = call_kwargs.get("json", {})
        assert body == {"token": "some.jwt.string"}

    def test_validate_token_has_no_authorization_header(self):
        """validate_token() is a public endpoint -- must NOT set Authorization header."""
        validate_resp = _make_response(200, self.VALIDATE_200_VALID)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([validate_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            client.validate_token(token="some.jwt.string")

        call_kwargs = mock_session_instance.request.call_args[1]
        headers = call_kwargs.get("headers", {})
        assert "Authorization" not in headers

    def test_validate_token_returns_invalid_response(self):
        """validate_token() must return the dict even when valid=False."""
        validate_resp = _make_response(200, self.VALIDATE_200_INVALID)
        mock_session_cls, mock_session_instance = _make_session_cls_and_instance([validate_resp])

        with patch("agentauth.client.requests.Session", mock_session_cls):
            client = _make_client(mock_session_instance)
            result = client.validate_token(token="expired.jwt.string")

        assert result["valid"] is False
        assert result["error"] == "token expired"
