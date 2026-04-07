from __future__ import annotations

import httpx
from typing import Any
from agentauth.errors import ProblemResponseError, AuthenticationError, AuthorizationError, RateLimitError, TransportError
from agentauth.models import ProblemDetail

class AgentAuthTransport:
    """Internal HTTP transport handler for the AgentAuth SDK.

    Business Logic:
    This class encapsulates all communication with the AgentAuth broker.
    Its primary responsibility is to manage the `httpx.Client` and to
    translate the broker's HTTP responses into the SDK's typed exception
    hierarchy.

    Specifically, it handles the parsing of `application/problem+json` (RFC 7807)
    responses, ensuring that business-rule rejections from the broker are
    raised as meaningful `ProblemResponseError` subclasses.

    Note: This is an internal class and should not be used by end-users.
    """

    def __init__(
        self,
        broker_url: str,
        timeout: float = 10.0,
        user_agent: str | None = None,
    ) -> None:
        self.broker_url = broker_url.rstrip("/")
        self.client = httpx.Client(
            timeout=timeout,
            headers={"User-Agent": user_agent or "agentauth-python/0.3.0"}
        )

    def _handle_error_response(self, response: httpx.Response) -> None:
        """Parses RFC 7807 error responses and raises appropriate SDK exceptions.

        Business Logic:
        The broker uses standard Problem Details to explain why a request
        was rejected. We map HTTP status codes to specific error types:
        - 401 -> AuthenticationError
        - 403 -> AuthorizationError
        - 429 -> RateLimitError
        - Others -> ProblemResponseError

        Args:
            response: The HTTP response object from the broker.

        Raises:
            AuthenticationError, AuthorizationError, RateLimitError,
            ProblemResponseError, TransportError
        """
        try:
            # Attempt to parse RFC 7807 body
            content_type = response.headers.get("content-type", "")
            if "application/problem+json" in content_type:
                data = response.json()
                problem = ProblemDetail(
                    type=data.get("type", ""),
                    title=data.get("title", ""),
                    detail=data.get("detail", ""),
                    instance=data.get("instance", ""),
                    status=data.get("status"),
                    error_code=data.get("error_code"),
                    request_id=data.get("request_id"),
                    hint=data.get("hint"),
                )
            else:
                # Fallback if broker doesn't provide structured error
                problem = ProblemDetail(
                    type="about:blank",
                    title="Unknown Error",
                    detail=response.text or "No error detail provided.",
                    instance=response.url.path,
                )

            status = response.status_code
            if status == 401:
                raise AuthenticationError(problem, status)
            if status == 403:
                raise AuthorizationError(problem, status)
            if status == 429:
                raise RateLimitError(problem, status)
            
            raise ProblemResponseError(problem, status)

        except (ValueError, KeyError) as e:
            # If JSON parsing fails, raise a generic error with raw text
            raise ProblemResponseError(
                ProblemDetail(
                    type="about:blank",
                    title="Error Parsing Response",
                    detail=f"Failed to parse error body: {str(e)}",
                    instance=response.url.path,
                ),
                response.status_code,
            )

    def request(self, method: str, path: str, **kwargs: Any) -> httpx.Response:
        """Executes an HTTP request against the broker.

        Args:
            method: HTTP method (GET, POST, etc.)
            path: Endpoint path (e.g., '/v1/app/auth')
            **kwargs: Arguments passed to httpx.Client.request

        Returns:
            A successful httpx.Response object.

        Raises:
            ProblemResponseError: If the broker returns a non-success status.
            TransportError: If a network-level failure occurs.
        """
        url = f"{self.broker_url}/{path.lstrip('/')}"
        try:
            response = self.client.request(method, url, **kwargs)
            
            if response.is_success:
                return response
            
            self._handle_error_response(response)
            # This line is technically unreachable due to exceptions in _handle_error_response
            raise TransportError(ProblemDetail(
                type="about:blank",
                title="Unexpected Error",
                detail="An unexpected error occurred during transport.",
                instance=url
            ), response.status_code)

        except httpx.RequestError as e:
            # Network-level failures (DNS, connection refused, timeout)
            raise TransportError(
                ProblemDetail(
                    type="about:blank",
                    title="Transport Error",
                    detail=str(e),
                    instance=url
                ),
                0  # Status code not available for network failures
            ) from e

    def close(self) -> None:
        """Closes the underlying HTTP client."""
        self.client.close()
