"""Agent — an ephemeral per-task principal created by AgentAuthApp.

Maps to the broker's agent identity model: each Agent holds a SPIFFE ID
(from POST /v1/register), a JWT access token, and lifecycle methods that
call the broker directly.

Broker endpoints used:
- POST /v1/token/renew  (Agent.renew)   — no body, Bearer auth
- POST /v1/token/release (Agent.release) — no body, Bearer auth, 204
- POST /v1/delegate      (Agent.delegate) — body + Bearer auth

ADR SDK-006: Agent has NO validate() method. Validation is the app's
responsibility — a compromised agent cannot be trusted to validate itself.

ADR SDK-008: renew() mutates in-place. Same agent, fresh token.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from agentauth.errors import AgentAuthError
from agentauth.models import DelegatedToken, DelegationRecord

if TYPE_CHECKING:
    from agentauth.app import AgentAuthApp


class Agent:
    """An ephemeral agent registered under an AgentAuthApp.

    Created by AgentAuthApp.create_agent(). Holds the agent JWT and
    a back-reference to its parent app for transport reuse.
    """

    def __init__(
        self,
        app: AgentAuthApp,
        agent_id: str,
        access_token: str,
        expires_in: int,
        scope: list[str],
        task_id: str,
        orch_id: str,
    ) -> None:
        self._app = app
        self.agent_id = agent_id
        self.access_token = access_token
        self.expires_in = expires_in
        self.scope = scope
        self.task_id = task_id
        self.orch_id = orch_id
        self._released = False

    @property
    def bearer_header(self) -> dict[str, str]:
        """Returns {"Authorization": "Bearer <token>"} for HTTP requests."""
        return {"Authorization": f"Bearer {self.access_token}"}

    def renew(self) -> None:
        """POST /v1/token/renew — renew this agent's token in place.

        The broker revokes the current JTI and issues a replacement with
        the same scope, TTL, and subject. Updates access_token and
        expires_in on this Agent instance. The agent_id does not change.
        """
        if self._released:
            raise AgentAuthError("agent has been released and cannot be renewed")

        response = self._app._transport.request(
            "POST",
            "/v1/token/renew",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        data = response.json()
        self.access_token = data["access_token"]
        self.expires_in = data["expires_in"]

    def release(self) -> None:
        """POST /v1/token/release — self-revoke on task completion.

        Returns None on success (broker returns 204 No Content).
        After calling release(), this agent is no longer usable.
        Idempotent: second call is a no-op.
        """
        if self._released:
            return

        self._app._transport.request(
            "POST",
            "/v1/token/release",
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        self._released = True

    def delegate(
        self,
        delegate_to: str,
        scope: list[str],
        *,
        ttl: int | None = None,
    ) -> DelegatedToken:
        """POST /v1/delegate — create a scope-attenuated delegation token.

        delegate_to: SPIFFE ID of the target agent (must already be registered).
        scope: must be a subset of this agent's scope.
        ttl: delegation lifetime in seconds (broker defaults to 60 if omitted).
        Max delegation depth: 5.
        """
        if self._released:
            raise AgentAuthError("agent has been released and cannot delegate")

        payload: dict[str, object] = {
            "delegate_to": delegate_to,
            "scope": scope,
        }
        if ttl is not None:
            payload["ttl"] = ttl

        response = self._app._transport.request(
            "POST",
            "/v1/delegate",
            json=payload,
            headers={"Authorization": f"Bearer {self.access_token}"},
        )
        data = response.json()

        chain = [
            DelegationRecord(
                agent=d["agent"],
                scope=d["scope"],
                delegated_at=d["delegated_at"],
            )
            for d in data.get("delegation_chain", [])
        ]

        return DelegatedToken(
            access_token=data["access_token"],
            expires_in=data["expires_in"],
            delegation_chain=chain,
        )

    def __repr__(self) -> str:
        return (
            f"Agent(agent_id={self.agent_id!r}, "
            f"orch_id={self.orch_id!r}, task_id={self.task_id!r})"
        )
