"""
╔══════════════════════════════════════════════════════════════════════════════╗
║  UNIT TESTS -- agentauth.retry.request_with_retry                          ║
║  No broker required. All HTTP interactions are mocked.                     ║
╚══════════════════════════════════════════════════════════════════════════════╝

Tests cover:
  - 200 returned immediately (call_count == 1)
  - 4xx (403) returned immediately without retry (call_count == 1)
  - 500 triggers retry with sleep(1), succeeds on attempt 2
  - All retries exhausted on 5xx raises BrokerUnavailableError
  - 429 reads Retry-After header, sleeps that value, retries
  - All 429 retries exhausted raises RateLimitError with retry_after attribute
  - requests.ConnectionError triggers retry with backoff
  - All connection errors exhausted raises BrokerUnavailableError
  - auth_token sets Authorization: Bearer {token} header
  - No auth_token means no Authorization header
"""

from __future__ import annotations

from unittest.mock import MagicMock, call, patch

import pytest
import requests

from agentauth.errors import BrokerUnavailableError, RateLimitError
from agentauth.retry import request_with_retry

# ── Helpers ──────────────────────────────────────────────────────────────────


def make_response(status_code: int, body: dict | None = None, headers: dict | None = None):
    """Build a minimal mock requests.Response."""
    resp = MagicMock(spec=requests.Response)
    resp.status_code = status_code
    resp.json.return_value = body or {}
    resp.headers = headers or {}
    resp.text = ""
    return resp


def make_session(*responses):
    """Return a mock session whose .request() returns responses in sequence."""
    session = MagicMock()
    session.request.side_effect = list(responses)
    return session


# ── Happy path ────────────────────────────────────────────────────────────────


class TestImmediateSuccess:
    def test_200_returns_immediately_call_count_1(self):
        resp = make_response(200)
        session = make_session(resp)

        result = request_with_retry(session, "GET", "http://broker/v1/test")

        assert result is resp
        assert session.request.call_count == 1

    def test_201_returns_immediately(self):
        resp = make_response(201)
        session = make_session(resp)

        result = request_with_retry(session, "POST", "http://broker/v1/test")

        assert result.status_code == 201
        assert session.request.call_count == 1


# ── 4xx: no retry ─────────────────────────────────────────────────────────────


class TestClientErrorNoRetry:
    def test_403_returns_immediately_without_retry(self):
        resp = make_response(403, {"error": "forbidden"})
        session = make_session(resp)

        result = request_with_retry(session, "POST", "http://broker/v1/test")

        assert result.status_code == 403
        assert session.request.call_count == 1

    def test_401_returns_immediately(self):
        resp = make_response(401)
        session = make_session(resp)

        result = request_with_retry(session, "GET", "http://broker/v1/test")

        assert result.status_code == 401
        assert session.request.call_count == 1

    def test_404_returns_immediately(self):
        resp = make_response(404)
        session = make_session(resp)

        result = request_with_retry(session, "GET", "http://broker/v1/missing")

        assert result.status_code == 404
        assert session.request.call_count == 1


# ── 5xx: retry then succeed ────────────────────────────────────────────────────


class TestServerErrorRetry:
    def test_500_retries_with_sleep_1_succeeds_on_attempt_2(self):
        resp_500 = make_response(500)
        resp_200 = make_response(200)
        session = make_session(resp_500, resp_200)

        with patch("agentauth.retry.time.sleep") as mock_sleep:
            result = request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert result.status_code == 200
        assert session.request.call_count == 2
        # First attempt is attempt 0 -> sleep(2**0) == sleep(1)
        mock_sleep.assert_called_once_with(1)

    def test_503_retries_twice_then_succeeds(self):
        resp_503 = make_response(503)
        resp_200 = make_response(200)
        session = make_session(resp_503, resp_503, resp_200)

        with patch("agentauth.retry.time.sleep") as mock_sleep:
            result = request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert result.status_code == 200
        assert session.request.call_count == 3
        assert mock_sleep.call_args_list == [call(1), call(2)]

    def test_all_retries_exhausted_on_5xx_raises_broker_unavailable(self):
        resp_500 = make_response(500, {"detail": "internal server error"})
        session = make_session(resp_500, resp_500, resp_500)

        with patch("agentauth.retry.time.sleep"):
            with pytest.raises(BrokerUnavailableError):
                request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert session.request.call_count == 3

    def test_broker_unavailable_error_has_status_code(self):
        resp_500 = make_response(500)
        session = make_session(resp_500, resp_500, resp_500)

        with patch("agentauth.retry.time.sleep"):
            with pytest.raises(BrokerUnavailableError) as exc_info:
                request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert exc_info.value.status_code == 500


# ── 429: Retry-After ──────────────────────────────────────────────────────────


class TestRateLimit:
    def test_429_reads_retry_after_header_sleeps_that_value_retries(self):
        resp_429 = make_response(429, {}, headers={"Retry-After": "30"})
        resp_200 = make_response(200)
        session = make_session(resp_429, resp_200)

        with patch("agentauth.retry.time.sleep") as mock_sleep:
            result = request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert result.status_code == 200
        assert session.request.call_count == 2
        mock_sleep.assert_called_once_with(30)

    def test_429_without_retry_after_uses_exponential_backoff(self):
        resp_429 = make_response(429, {}, headers={})
        resp_200 = make_response(200)
        session = make_session(resp_429, resp_200)

        with patch("agentauth.retry.time.sleep") as mock_sleep:
            result = request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert result.status_code == 200
        # Attempt 0 -> sleep(2**0) == 1
        mock_sleep.assert_called_once_with(1)

    def test_all_429_retries_exhausted_raises_rate_limit_error(self):
        resp_429 = make_response(429, {"detail": "too many requests"}, headers={"Retry-After": "5"})
        session = make_session(resp_429, resp_429, resp_429)

        with patch("agentauth.retry.time.sleep"):
            with pytest.raises(RateLimitError):
                request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert session.request.call_count == 3

    def test_rate_limit_error_has_retry_after_attribute(self):
        resp_429 = make_response(429, {}, headers={"Retry-After": "42"})
        session = make_session(resp_429, resp_429, resp_429)

        with patch("agentauth.retry.time.sleep"):
            with pytest.raises(RateLimitError) as exc_info:
                request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert exc_info.value.retry_after == 42


# ── ConnectionError: retry with backoff ──────────────────────────────────────


class TestConnectionError:
    def test_connection_error_triggers_retry_with_backoff(self):
        resp_200 = make_response(200)
        session = make_session(requests.ConnectionError("refused"), resp_200)

        with patch("agentauth.retry.time.sleep") as mock_sleep:
            result = request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert result.status_code == 200
        assert session.request.call_count == 2
        mock_sleep.assert_called_once_with(1)

    def test_all_connection_errors_exhausted_raises_broker_unavailable(self):
        session = make_session(
            requests.ConnectionError("refused"),
            requests.ConnectionError("refused"),
            requests.ConnectionError("refused"),
        )

        with patch("agentauth.retry.time.sleep"):
            with pytest.raises(BrokerUnavailableError):
                request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert session.request.call_count == 3

    def test_connection_error_backoff_is_exponential(self):
        resp_200 = make_response(200)
        session = make_session(
            requests.ConnectionError("refused"),
            requests.ConnectionError("refused"),
            resp_200,
        )

        with patch("agentauth.retry.time.sleep") as mock_sleep:
            result = request_with_retry(session, "GET", "http://broker/v1/test", max_retries=3)

        assert result.status_code == 200
        # Attempt 0 -> sleep(1), attempt 1 -> sleep(2)
        assert mock_sleep.call_args_list == [call(1), call(2)]


# ── Authorization header ─────────────────────────────────────────────────────


class TestAuthorizationHeader:
    def test_auth_token_sets_bearer_header(self):
        resp = make_response(200)
        session = make_session(resp)

        request_with_retry(session, "GET", "http://broker/v1/test", auth_token="mytoken123")

        _, kwargs = session.request.call_args
        headers = kwargs.get("headers", {})
        assert headers.get("Authorization") == "Bearer mytoken123"

    def test_no_auth_token_means_no_authorization_header(self):
        resp = make_response(200)
        session = make_session(resp)

        request_with_retry(session, "GET", "http://broker/v1/test")

        _, kwargs = session.request.call_args
        headers = kwargs.get("headers", {})
        assert "Authorization" not in headers

    def test_auth_token_preserved_across_retries(self):
        resp_500 = make_response(500)
        resp_200 = make_response(200)
        session = make_session(resp_500, resp_200)

        with patch("agentauth.retry.time.sleep"):
            request_with_retry(
                session, "GET", "http://broker/v1/test", auth_token="persisttoken", max_retries=3
            )

        assert session.request.call_count == 2
        for c in session.request.call_args_list:
            _, kwargs = c
            assert kwargs.get("headers", {}).get("Authorization") == "Bearer persisttoken"


# ── JSON body passthrough ─────────────────────────────────────────────────────


class TestJsonBody:
    def test_json_body_passed_to_request(self):
        resp = make_response(200)
        session = make_session(resp)
        payload = {"key": "value"}

        request_with_retry(session, "POST", "http://broker/v1/test", json=payload)

        _, kwargs = session.request.call_args
        assert kwargs.get("json") == payload

    def test_no_json_body_when_not_provided(self):
        resp = make_response(200)
        session = make_session(resp)

        request_with_retry(session, "GET", "http://broker/v1/test")

        _, kwargs = session.request.call_args
        assert kwargs.get("json") is None
