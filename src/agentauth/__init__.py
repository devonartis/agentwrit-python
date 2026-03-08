"""AgentAuth Python SDK — ephemeral, task-scoped credentials for AI agents.

This package provides a Python client for the AgentAuth credential broker.
It wraps the broker's 8-step Ed25519 challenge-response flow into simple
function calls, handling key generation, token caching, renewal, retry,
and HITL (human-in-the-loop) approval flow control.

Quick start::

    from agentauth import AgentAuthClient

    client = AgentAuthClient(broker_url, client_id, client_secret)
    token = client.get_token("my-agent", ["read:data:*"])

For full documentation, see: https://github.com/devonartis/agentauth-python-sdk

Exports:
    AgentAuthClient         — Main client class (the primary entry point)
    AgentAuthError          — Base exception for all SDK errors
    AuthenticationError     — 401: bad credentials
    ScopeCeilingError       — 403: scope exceeds app ceiling
    HITLApprovalRequired    — 403: human approval needed (flow control, not failure)
    RateLimitError          — 429: rate limited after all retries
    BrokerUnavailableError  — 5xx / connection failure after all retries
    TokenExpiredError       — Token has expired
"""

__version__ = "0.1.0"

from agentauth.client import AgentAuthClient
from agentauth.errors import (
    AgentAuthError,
    AuthenticationError,
    BrokerUnavailableError,
    HITLApprovalRequired,
    RateLimitError,
    ScopeCeilingError,
    TokenExpiredError,
)

__all__ = [
    "AgentAuthClient",
    "__version__",
    "AgentAuthError",
    "AuthenticationError",
    "BrokerUnavailableError",
    "HITLApprovalRequired",
    "RateLimitError",
    "ScopeCeilingError",
    "TokenExpiredError",
]
