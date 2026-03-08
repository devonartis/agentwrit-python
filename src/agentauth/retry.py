"""Retry logic for AgentAuth broker HTTP requests.

Supports pattern component C3 (Zero-Trust Enforcement) by ensuring transient
broker failures do not prevent legitimate agent operations, while respecting
the broker's rate limits (per NIST NCCoE recommendation on graceful backoff).

Single function: request_with_retry()

Retry policy:
  - 2xx / 3xx / 4xx (except 429): return immediately, no retry
  - 429 (Rate Limit): sleep Retry-After header value (or 2**attempt),
    retry up to max_retries; raise RateLimitError when exhausted
  - 5xx: sleep 2**attempt seconds, retry up to max_retries;
    raise BrokerUnavailableError when exhausted
  - requests.ConnectionError: sleep 2**attempt seconds, retry up to
    max_retries; raise BrokerUnavailableError when exhausted

The `time` module is imported at module level so tests can patch
`agentauth.retry.time.sleep` directly.
"""

from __future__ import annotations

import time

import requests

from agentauth.errors import BrokerUnavailableError, parse_error_response


def request_with_retry(
    session: requests.Session,
    method: str,
    url: str,
    *,
    json: dict[str, object] | None = None,
    auth_token: str | None = None,
    max_retries: int = 3,
) -> requests.Response:
    """Make an HTTP request with retry logic for transient broker failures.

    Args:
        session: A requests.Session to use for the request.
        method: HTTP method string (e.g. "GET", "POST").
        url: Full URL to request.
        json: Optional JSON-serialisable body dict.
        auth_token: If provided, sets ``Authorization: Bearer {auth_token}``.
        max_retries: Maximum total attempts (default 3).

    Returns:
        The first successful (non-retried) requests.Response.

    Raises:
        BrokerUnavailableError: All attempts failed due to 5xx or
            ConnectionError.
        RateLimitError: All attempts failed due to HTTP 429.
    """
    last_429_retry_after: int | None = None
    last_status: int | None = None

    for attempt in range(max_retries):
        headers: dict[str, str] = {}
        if auth_token is not None:
            headers["Authorization"] = f"Bearer {auth_token}"

        try:
            response = session.request(method, url, json=json, headers=headers)
        except requests.ConnectionError as exc:
            backoff = 2**attempt
            if attempt < max_retries - 1:
                time.sleep(backoff)
                continue
            raise BrokerUnavailableError(
                f"broker unreachable after {max_retries} attempts: {exc}"
            ) from exc

        status = response.status_code
        last_status = status

        # 429 Rate Limit
        if status == 429:
            retry_after_raw = response.headers.get("Retry-After")
            if retry_after_raw is not None:
                try:
                    retry_after = int(retry_after_raw)
                except ValueError:
                    retry_after = 2**attempt
            else:
                retry_after = 2**attempt

            last_429_retry_after = retry_after

            if attempt < max_retries - 1:
                time.sleep(retry_after)
                continue

            # All retries exhausted -- parse body for a proper RateLimitError
            try:
                body = response.json()
            except Exception:
                body = {}
            raise parse_error_response(429, body, retry_after=last_429_retry_after)

        # 5xx Server Error
        if 500 <= status < 600:
            backoff = 2**attempt
            if attempt < max_retries - 1:
                time.sleep(backoff)
                continue
            # All retries exhausted
            raise BrokerUnavailableError(
                f"broker returned {status} after {max_retries} attempts",
                status_code=status,
            )

        # 2xx / 3xx / 4xx (non-429): return immediately
        return response

    # Should not reach here, but satisfy type checkers
    raise BrokerUnavailableError(  # pragma: no cover
        "broker unavailable",
        status_code=last_status,
    )
