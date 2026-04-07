from __future__ import annotations

from agentauth.app import AgentAuthApp
from agentauth.agent import Agent
from agentauth.errors import (
    AgentAuthError,
    AuthenticationError,
    AuthorizationError,
    RateLimitError,
    ProblemResponseError,
    TransportError,
    CryptoError,
)
from agentauth.models import (
    AgentClaims,
    DelegationRecord,
    DelegatedToken,
    HealthStatus,
    ProblemDetail,
    RegisterResult,
    ValidateResult,
)
from agentauth.scope import scope_is_subset, validate

__version__ = "0.3.0"

__all__ = [
    "AgentAuthApp",
    "Agent",
    "AgentAuthError",
    "AuthenticationError",
    "AuthorizationError",
    "RateLimitError",
    "ProblemResponseError",
    "TransportError",
    "CryptoError",
    "AgentClaims",
    "DelegationRecord",
    "DelegatedToken",
    "HealthStatus",
    "ProblemDetail",
    "RegisterResult",
    "ValidateResult",
    "scope_is_subset",
    "validate",
    "__version__",
]
