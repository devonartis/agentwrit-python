"""AgentWrit Python SDK — ephemeral, task-scoped credentials for AI agents.

Implements the App-as-Container model: AgentWritApp is the developer's
entry point, Agent is an ephemeral per-task principal created by the app.
All agent authority flows from the app's scope ceiling set by the operator.

Spec: .plans/specs/NEW_SPECS_TO_USED.md
ADRs: .plans/specs/SPEC_ADR.md (SDK-001 through SDK-012)
"""

from __future__ import annotations

from agentwrit.agent import Agent
from agentwrit.app import AgentWritApp
from agentwrit.errors import (
    AgentWritError,
    AuthenticationError,
    AuthorizationError,
    CryptoError,
    ProblemResponseError,
    RateLimitError,
    TransportError,
)
from agentwrit.models import (
    AgentClaims,
    DelegatedToken,
    DelegationRecord,
    HealthStatus,
    ProblemDetail,
    RegisterResult,
    ValidateResult,
)
from agentwrit.scope import scope_is_subset, validate

__version__ = "0.3.0"

__all__ = [
    "Agent",
    "AgentWritApp",
    "AgentWritError",
    "AgentClaims",
    "AuthenticationError",
    "AuthorizationError",
    "CryptoError",
    "DelegatedToken",
    "DelegationRecord",
    "HealthStatus",
    "ProblemDetail",
    "ProblemResponseError",
    "RateLimitError",
    "RegisterResult",
    "TransportError",
    "ValidateResult",
    "__version__",
    "scope_is_subset",
    "validate",
]
