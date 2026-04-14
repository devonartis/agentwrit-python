"""Unit tests for agentwrit.errors — exception hierarchy.

Verifies inheritance, ProblemResponseError construction with ProblemDetail,
and that each subclass maps to the correct HTTP status code semantics.

Spec: Section 9 (Error Model)
"""
from __future__ import annotations

from agentwrit.errors import (
    AgentWritError,
    AuthenticationError,
    AuthorizationError,
    CryptoError,
    ProblemResponseError,
    RateLimitError,
    TransportError,
)
from agentwrit.models import ProblemDetail

# --- Hierarchy ---


class TestExceptionHierarchy:
    """All custom errors inherit from AgentWritError → Exception."""

    def test_base_inherits_from_exception(self):
        assert issubclass(AgentWritError, Exception)

    def test_problem_response_inherits_from_base(self):
        assert issubclass(ProblemResponseError, AgentWritError)

    def test_authentication_error_inherits(self):
        assert issubclass(AuthenticationError, ProblemResponseError)

    def test_authorization_error_inherits(self):
        assert issubclass(AuthorizationError, ProblemResponseError)

    def test_rate_limit_error_inherits(self):
        assert issubclass(RateLimitError, ProblemResponseError)

    def test_transport_error_is_not_problem_response(self):
        assert issubclass(TransportError, AgentWritError)
        assert not issubclass(TransportError, ProblemResponseError)

    def test_crypto_error_is_not_problem_response(self):
        assert issubclass(CryptoError, AgentWritError)
        assert not issubclass(CryptoError, ProblemResponseError)

    def test_all_catchable_via_base(self):
        """A single except AgentWritError catches every SDK exception."""
        problem = ProblemDetail(type="t", title="T", detail="d", instance="/")
        errors = [
            ProblemResponseError(problem, 400),
            AuthenticationError(problem, 401),
            AuthorizationError(problem, 403),
            RateLimitError(problem, 429),
            TransportError("fail"),
            CryptoError("fail"),
        ]
        for err in errors:
            assert isinstance(err, AgentWritError)


# --- ProblemResponseError ---


class TestProblemResponseError:
    def test_stores_problem_and_status(self):
        problem = ProblemDetail(
            type="urn:agentwrit:error:forbidden",
            title="Forbidden",
            detail="scope exceeds ceiling",
            instance="/v1/app/launch-tokens",
            status=403,
            error_code="forbidden",
        )
        err = ProblemResponseError(problem, 403)
        assert err.problem is problem
        assert err.status_code == 403

    def test_str_contains_title_and_detail(self):
        problem = ProblemDetail(
            type="t", title="Bad Request", detail="missing field", instance="/",
        )
        err = ProblemResponseError(problem, 400)
        msg = str(err)
        assert "Bad Request" in msg
        assert "missing field" in msg


# --- Specific error types ---


class TestAuthenticationError:
    def test_401_construction(self):
        problem = ProblemDetail(
            type="t", title="Unauthorized", detail="invalid credentials",
            instance="/v1/app/auth",
        )
        err = AuthenticationError(problem, 401)
        assert err.status_code == 401
        assert "invalid credentials" in str(err)


class TestAuthorizationError:
    def test_403_scope_violation(self):
        problem = ProblemDetail(
            type="t", title="Forbidden",
            detail="scope exceeds app ceiling",
            instance="/v1/app/launch-tokens",
            error_code="forbidden",
        )
        err = AuthorizationError(problem, 403)
        assert err.status_code == 403
        assert err.problem.error_code == "forbidden"


class TestRateLimitError:
    def test_429_construction(self):
        problem = ProblemDetail(
            type="t", title="Too Many Requests",
            detail="rate limit exceeded",
            instance="/v1/app/auth",
        )
        err = RateLimitError(problem, 429)
        assert err.status_code == 429


class TestTransportError:
    def test_string_message(self):
        err = TransportError("broker unreachable at http://localhost:8080")
        assert "broker unreachable" in str(err)


class TestCryptoError:
    def test_string_message(self):
        err = CryptoError("Ed25519 signing failed")
        assert "Ed25519" in str(err)
