from __future__ import annotations

from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class DelegationRecord:
    """A record of an agent delegation.
    
    Business Logic: This represents one step in the 'chain of trust'. 
    When an agent delegates authority, it creates a new token that carries 
    the identity of the delegator. The broker uses these records to 
    enforce the maximum delegation depth (5) and to ensure that 
    authority is only ever attenuated (narrowed), never expanded.
    """
    agent: str            # SPIFFE ID of delegator
    scope: list[str]
    delegated_at: str     # RFC 3339

@dataclass(frozen=True)
class AgentClaims:
    """Mirrors TknClaims from internal/token/tkn_claims.go.
    
    Business Logic: These claims represent the 'identity' and 'authority' 
    of an ephemeral agent. Unlike a standard user JWT, these claims 
    explicitly include `orch_id` and `task_id` to tie the agent's lifecycle 
    to a specific unit of work in the developer's orchestration system.
    The `sub` field is a SPIFFE URI, ensuring the agent is a first-class 
    identity in the trust domain.
    """
    iss: str              # always "agentauth"
    sub: str              # SPIFFE URI
    aud: list[str]
    exp: int              # Unix timestamp
    nbf: int              # Unix timestamp
    iat: int              # Unix timestamp
    jti: str              # unique token ID
    scope: list[str]
    task_id: str
    orch_id: str
    sid: str | None = None
    delegation_chain: list[DelegationRecord] | None = None
    chain_hash: str | None = None

@dataclass(frozen=True)
class ValidateResult:
    """The result of a token validation check via POST /v1/token/validate.
    
    Business Logic: This is the authoritative way for a resource server 
    or the App to verify if an agent is still trusted. Because validation 
    is performed by the broker, it catches not just malformed tokens, 
    but also tokens that have been revoked by an operator or via `release()`.
    """
    valid: bool
    claims: AgentClaims | None = None
    error: str | None = None

@dataclass(frozen=True)
class DelegatedToken:
    """A token received via an agent's delegate() call.
    
    Business Logic: This is a 'sub-token' that carries a subset of the 
    original agent's authority. It is designed for 'least-privilege' 
    workflows where a primary agent (e.g., a Researcher) delegates 
    a specific, narrow task to a secondary agent (e.g., a Tool-User).
    """
    access_token: str
    expires_in: int
    delegation_chain: list[DelegationRecord]

@dataclass(frozen=True)
class RegisterResult:
    """Result of an agent registration attempt via POST /v1/register.
    
    Business Logic: This is the outcome of the Ed25519 challenge-response 
    ceremony. A successful registration results in a unique, ephemeral 
    identity (SPIFFE ID) and a short-lived access token.
    """
    agent_id: str         # SPIFFE URI
    access_token: str
    expires_in: int

@dataclass(frozen=True)
class HealthStatus:
    """The current health status of the broker.
    
    Business Logic: Provides high-level visibility into whether the 
    broker is ready to accept new registrations or validate tokens.
    """
    status: str           # "ok"
    version: str          # e.g. "2.0.0"
    uptime: int           # seconds
    db_connected: bool
    audit_events_count: int

@dataclass(frozen=True)
class ProblemDetail:
    """RFC 7807 problem detail from broker error responses.
    
    Business Logic: Standardized error reporting. This allows the SDK 
    to translate cryptic HTTP failures into meaningful developer 
    messages that explain *why* a business rule was violated 
    (e.g., "Scope ceiling violation").
    """
    type: str
    title: str
    detail: str
    instance: str
    status: int | None = None
    error_code: str | None = None
    request_id: str | None = None
    hint: str | None = None
