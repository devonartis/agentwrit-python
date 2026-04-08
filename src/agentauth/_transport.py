"""Internal HTTP transport for the AgentAuth SDK.

Wraps httpx.Client and translates broker HTTP responses into the SDK's
typed exception hierarchy. Parses RFC 7807 application/problem+json
bodies into ProblemDetail and dispatches to the correct error subclass
based on HTTP status code.

Broker error mapping:
  - 401 → AuthenticationError (invalid credentials)
  - 403 → AuthorizationError (scope violation, revoked token)
  - 429 → RateLimitError (rate limit exceeded)
  - Other 4xx/5xx → ProblemResponseError
  - Network failure → TransportError

This module is internal. End users should not import it directly.
"""

from __future__ import annotations

import httpx

from agentauth.errors import (
    AuthenticationError,
    AuthorizationError,
    ProblemResponseError,
    RateLimitError,
    TransportError,
)
from agentauth.models import ProblemDetail


class AgentAuthTransport:
    """Internal HTTP transport handler for the AgentAuth SDK.

    Manages the httpx.Client and translates broker RFC 7807 error
    responses into the SDK's typed exception hierarchy.
    """

    def __init__(
        self,
        broker_url: str,
        timeout: float = 10.0,
        user_agent: str | None = None,
    ) -> None:
        self.broker_url = broker_url.rstrip("/")
        self._client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent or "agentauth-python/0.3.0"},
        )

    def _parse_problem(self, response: httpx.Response) -> ProblemDetail:
        """Parse an RFC 7807 body, or synthesize one from the raw response."""
        try:
            data = response.json()
            return ProblemDetail(
                type=data.get("type", ""),
                title=data.get("title", ""),
                detail=data.get("detail", ""),
                instance=data.get("instance", str(response.url.path)),
                status=data.get("status"),
                error_code=data.get("error_code"),
                request_id=data.get("request_id"),
                hint=data.get("hint"),
            )
        except Exception:
            return ProblemDetail(
                type="about:blank",
                title=f"HTTP {response.status_code}",
                detail=response.text or "No error detail provided.",
                instance=str(response.url.path),
                status=response.status_code,
            )

    def _raise_for_status(self, response: httpx.Response) -> None:
        """Dispatch non-success responses to typed SDK exceptions."""
        problem = self._parse_problem(response)
        status = response.status_code

        if status == 401:
            raise AuthenticationError(problem, status)
        if status == 403:
            raise AuthorizationError(problem, status)
        if status == 429:
            raise RateLimitError(problem, status)
        raise ProblemResponseError(problem, status)

    def request(
        self,
        method: str,
        path: str,
        *,
        json: dict[str, object] | None = None,
        headers: dict[str, str] | None = None,
    ) -> httpx.Response:
        """Execute an HTTP request against the broker.

        Returns the response on success (2xx). Raises typed SDK
        exceptions on error responses or network failures.
        """
        url = f"{self.broker_url}/{path.lstrip('/')}"
        try:
            response = self._client.request(
                method, url, json=json, headers=headers,
            )
        except httpx.RequestError as exc:
            raise TransportError(
                f"broker unreachable at {url}: {exc}"
            ) from exc

        if response.is_success:
            return response

        self._raise_for_status(response)
        # _raise_for_status always raises; this satisfies the type checker
        raise AssertionError("unreachable")  # pragma: no cover

    def close(self) -> None:
        """Close the underlying HTTP client."""
        self._client.close()
