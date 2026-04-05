"""Unit tests for AgentAuthApp.__init__ and _authenticate_app.

Patch point: agentauth.app.requests.Session
No broker required -- all HTTP is mocked.

TDD order: these tests are written before client.py exists.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from agentauth.errors import AuthenticationError

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUTH_200 = {
    "access_token": "eyJhbGciOiJFZERTQSJ9.test",
    "expires_in": 300,
    "token_type": "Bearer",
    "scopes": ["read:data:*"],
}


def _make_session_mock(status_code: int = 200, json_body: dict | None = None):
    """Return a mock requests.Session whose post() returns the given response."""
    if json_body is None:
        json_body = AUTH_200

    mock_response = MagicMock()
    mock_response.status_code = status_code
    mock_response.json.return_value = json_body

    mock_session_instance = MagicMock()
    mock_session_instance.post.return_value = mock_response

    mock_session_cls = MagicMock(return_value=mock_session_instance)
    return mock_session_cls, mock_session_instance, mock_response


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestAgentAuthAppInit:
    """__init__ calls _authenticate_app which POSTs to /v1/app/auth."""

    def test_init_calls_post_app_auth_once(self):
        """__init__ must call POST /v1/app/auth exactly once."""
        mock_session_cls, mock_session_instance, _ = _make_session_mock()

        with patch("agentauth.app.requests.Session", mock_session_cls):
            from agentauth.app import AgentAuthApp  # noqa: PLC0415

            AgentAuthApp(
                broker_url="http://broker.example.com",
                client_id="app-123",
                client_secret="super-secret",
            )

        mock_session_instance.post.assert_called_once()

    def test_post_url_contains_v1_app_auth(self):
        """The URL used in the POST must include '/v1/app/auth'."""
        mock_session_cls, mock_session_instance, _ = _make_session_mock()

        with patch("agentauth.app.requests.Session", mock_session_cls):
            from agentauth.app import AgentAuthApp  # noqa: PLC0415

            AgentAuthApp(
                broker_url="http://broker.example.com",
                client_id="app-123",
                client_secret="super-secret",
            )

        call_args = mock_session_instance.post.call_args
        url_called = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "/v1/app/auth" in url_called

    def test_bad_credentials_raise_authentication_error(self):
        """A 401 response from /v1/app/auth must raise AuthenticationError."""
        body_401 = {
            "type": "https://httpstatuses.com/401",
            "title": "Unauthorized",
            "status": 401,
            "detail": "invalid client credentials",
            "error_code": "unauthorized",
        }
        mock_session_cls, _, _ = _make_session_mock(status_code=401, json_body=body_401)

        with patch("agentauth.app.requests.Session", mock_session_cls):
            from agentauth.app import AgentAuthApp  # noqa: PLC0415

            with pytest.raises(AuthenticationError):
                AgentAuthApp(
                    broker_url="http://broker.example.com",
                    client_id="app-123",
                    client_secret="wrong-secret",
                )

    def test_trailing_slash_stripped_from_broker_url(self):
        """broker_url with trailing slash must not produce double-slash URLs."""
        mock_session_cls, mock_session_instance, _ = _make_session_mock()

        with patch("agentauth.app.requests.Session", mock_session_cls):
            from agentauth.app import AgentAuthApp  # noqa: PLC0415

            AgentAuthApp(
                broker_url="http://broker.example.com/",  # trailing slash
                client_id="app-123",
                client_secret="super-secret",
            )

        call_args = mock_session_instance.post.call_args
        url_called = call_args[0][0] if call_args[0] else call_args[1].get("url", "")
        assert "//" not in url_called.split("://", 1)[1], (
            f"Double slash detected in URL: {url_called}"
        )
        assert url_called == "http://broker.example.com/v1/app/auth"

    def test_secret_not_in_repr(self):
        """repr(client) must NOT contain the client_secret."""
        mock_session_cls, _, _ = _make_session_mock()
        secret = "super-secret-do-not-leak"

        with patch("agentauth.app.requests.Session", mock_session_cls):
            from agentauth.app import AgentAuthApp  # noqa: PLC0415

            client = AgentAuthApp(
                broker_url="http://broker.example.com",
                client_id="app-123",
                client_secret=secret,
            )

        assert secret not in repr(client), f"client_secret found in repr: {repr(client)}"

    def test_secret_not_in_str(self):
        """str(client) must NOT contain the client_secret."""
        mock_session_cls, _, _ = _make_session_mock()
        secret = "super-secret-do-not-leak"

        with patch("agentauth.app.requests.Session", mock_session_cls):
            from agentauth.app import AgentAuthApp  # noqa: PLC0415

            client = AgentAuthApp(
                broker_url="http://broker.example.com",
                client_id="app-123",
                client_secret=secret,
            )

        assert secret not in str(client), f"client_secret found in str: {str(client)}"
