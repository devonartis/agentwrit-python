"""Unit tests for agentauth.errors -- exception hierarchy and parse_error_response."""

import json

import pytest

from agentauth.errors import (
    AgentAuthError,
    AuthenticationError,
    BrokerUnavailableError,
    RateLimitError,
    ScopeCeilingError,
    parse_error_response,
)

# ── Hierarchy ──────────────────────────────────────────────────────────────


class TestExceptionHierarchy:
    """All custom errors inherit from AgentAuthError, which inherits from Exception."""

    def test_base_inherits_from_exception(self):
        assert issubclass(AgentAuthError, Exception)

    def test_authentication_error_inherits(self):
        assert issubclass(AuthenticationError, AgentAuthError)

    def test_scope_ceiling_error_inherits(self):
        assert issubclass(ScopeCeilingError, AgentAuthError)

    def test_rate_limit_error_inherits(self):
        assert issubclass(RateLimitError, AgentAuthError)

    def test_broker_unavailable_error_inherits(self):
        assert issubclass(BrokerUnavailableError, AgentAuthError)


# ── Base Error ─────────────────────────────────────────────────────────────


class TestAgentAuthError:
    def test_message(self):
        err = AgentAuthError("something broke")
        assert str(err) == "something broke"

    def test_status_code(self):
        err = AgentAuthError("bad", status_code=500)
        assert err.status_code == 500

    def test_error_code(self):
        err = AgentAuthError("bad", error_code="unknown")
        assert err.error_code == "unknown"

    def test_defaults_none(self):
        err = AgentAuthError("x")
        assert err.status_code is None
        assert err.error_code is None

    def test_catchable_as_exception(self):
        with pytest.raises(Exception):
            raise AgentAuthError("boom")


# ── AuthenticationError ────────────────────────────────────────────────────


class TestAuthenticationError:
    def test_client_id_in_message(self):
        err = AuthenticationError("invalid credentials", client_id="app-123")
        assert "app-123" in str(err)

    def test_client_id_attribute(self):
        err = AuthenticationError("bad", client_id="app-xyz")
        assert err.client_id == "app-xyz"

    def test_secret_never_in_message(self):
        """client_secret must NEVER appear in error output."""
        err = AuthenticationError("invalid credentials", client_id="app-123", status_code=401)
        msg = str(err)
        assert "secret" not in msg.lower()

    def test_secret_never_in_repr(self):
        err = AuthenticationError("bad", client_id="app-123")
        assert "secret" not in repr(err).lower()

    def test_inherits_status_code(self):
        err = AuthenticationError("bad", client_id="c1", status_code=401)
        assert err.status_code == 401


# ── ScopeCeilingError ──────────────────────────────────────────────────────


class TestScopeCeilingError:
    def test_requested_scope_attribute(self):
        err = ScopeCeilingError(
            detail="scope violation",
            requested_scope=["read:data:*", "write:data:*"],
        )
        assert err.requested_scope == ["read:data:*", "write:data:*"]

    def test_message_includes_scope(self):
        err = ScopeCeilingError(
            detail="scope violation",
            requested_scope=["read:data:*"],
        )
        assert "read:data:*" in str(err)

    def test_message_includes_detail(self):
        err = ScopeCeilingError(detail="scope exceeds app ceiling")
        assert "scope exceeds app ceiling" in str(err)

    def test_status_code_is_403(self):
        err = ScopeCeilingError(detail="nope", status_code=403)
        assert err.status_code == 403


# ── RateLimitError ─────────────────────────────────────────────────────────


class TestRateLimitError:
    def test_retry_after_attribute(self):
        err = RateLimitError("slow down", retry_after=30)
        assert err.retry_after == 30

    def test_retry_after_none(self):
        err = RateLimitError("slow down")
        assert err.retry_after is None

    def test_status_code_is_429(self):
        err = RateLimitError("slow down", retry_after=5)
        assert err.status_code == 429


# ── Simple subclasses ──────────────────────────────────────────────────────


class TestSimpleSubclasses:
    def test_broker_unavailable_instantiates(self):
        err = BrokerUnavailableError("broker down")
        assert str(err) == "broker down"


# ── parse_error_response ──────────────────────────────────────────────────


class TestParseErrorResponse:
    """parse_error_response dispatches on status_code and body content."""

    def test_401_returns_authentication_error(self):
        body = {
            "type": "about:blank",
            "title": "Unauthorized",
            "status": 401,
            "detail": "invalid client credentials",
            "error_code": "authentication_failed",
        }
        err = parse_error_response(401, body, client_id="app-123")
        assert isinstance(err, AuthenticationError)
        assert err.client_id == "app-123"
        assert err.status_code == 401

    def test_403_scope_violation_returns_scope_ceiling_error(self):
        body = {
            "type": "about:blank",
            "title": "Forbidden",
            "status": 403,
            "detail": "requested scope exceeds ceiling",
            "error_code": "scope_violation",
        }
        err = parse_error_response(403, body)
        assert isinstance(err, ScopeCeilingError)
        assert err.status_code == 403

    def test_429_returns_rate_limit_error(self):
        body = {
            "type": "about:blank",
            "title": "Too Many Requests",
            "status": 429,
            "detail": "rate limit exceeded",
            "error_code": "rate_limited",
        }
        err = parse_error_response(429, body, retry_after=60)
        assert isinstance(err, RateLimitError)
        assert err.retry_after == 60
        assert err.status_code == 429

    def test_unknown_status_returns_base_error(self):
        body = {
            "type": "about:blank",
            "title": "Internal Server Error",
            "status": 500,
            "detail": "something went wrong",
            "error_code": "internal",
        }
        err = parse_error_response(500, body)
        assert isinstance(err, AgentAuthError)
        assert err.status_code == 500

    def test_empty_body_returns_base_error(self):
        err = parse_error_response(502, {})
        assert isinstance(err, AgentAuthError)

    def test_body_as_string_json(self):
        """parse_error_response should handle body passed as a JSON string."""
        body_str = json.dumps(
            {
                "type": "about:blank",
                "title": "Unauthorized",
                "status": 401,
                "detail": "bad creds",
                "error_code": "authentication_failed",
            }
        )
        err = parse_error_response(401, body_str, client_id="app-1")
        assert isinstance(err, AuthenticationError)
