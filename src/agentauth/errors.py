from __future__ import annotations

from agentauth.models import ProblemDetail


class AgentAuthError(Exception):
    """Base exception for all SDK errors.

    All errors raised by the SDK inherit from this base class to allow
    users to catch any AgentAuth-related failure.
    """

class ProblemResponseError(AgentAuthError):
    """Broker returned an RFC 7807 error response.

    This error maps directly to the `application/problem+json` content type
    used by the AgentAuth broker. It provides structured error information
    about why a request failed (e.g., invalid scope, expired nonce).

    The presence of this error indicates that the broker received the
    request and explicitly rejected it based on its internal business rules.

    See: https://datatracker.ietf.org/doc/html/rfc7807
    """
    problem: ProblemDetail
    status_code: int

    def __init__(self, problem: ProblemDetail, status_code: int) -> None:
        super().__init__(f"{problem.title}: {problem.detail}")
        self.problem = problem
        self.status_code = status_code

class AuthenticationError(ProblemResponseError):
    """401 Unauthorized -- invalid or missing credentials.

    Business Logic: The broker rejected the application's identity.
    This usually means the `client_id` or `client_secret` provided to
    `AgentAuthApp` are incorrect or have been rotated by the operator.
    """

class AuthorizationError(ProblemResponseError):
    """403 Forbidden -- scope ceiling violation or revoked token.

    Business Logic: The request was authenticated, but the principal
    is not permitted to perform this action. This occurs in three main scenarios:
    1. Scope Ceiling Violation: The app is trying to create an agent with
       more authority than the operator initially granted to the app.
    2. Token Revocation: The agent's token was explicitly invalidated by the
       broker (e.g., via an operator-level revocation or agent `release()`).
    3. Delegation Violation: An agent attempted to delegate authority to
       another agent in a way that violates the hierarchy (e.g., increasing scope).
    """

class RateLimitError(ProblemResponseError):
    """429 Too Many Requests.

    Business Logic: The client is hitting the broker's protective limits.
    The broker enforces rate limits to prevent DDoS attacks and to ensure
    availability for all registered applications.
    """

class TransportError(AgentAuthError):
    """Network, DNS, timeout, or connection failure.

    Business Logic: The SDK was unable to reach the broker. This is a
    connectivity issue (e.g., incorrect `broker_url`, network outage, or
    broker downtime) and is not an application-level rejection from the
    broker itself.
    """

class CryptoError(AgentAuthError):
    """Ed25519 key generation, signing, or encoding failure.

    Business Logic: A failure in the cryptographic ceremony required to
    register an agent. This is a client-side failure occurring during
    the challenge-response process.
    """
