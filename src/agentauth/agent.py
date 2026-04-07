from __future__ import annotations

import time
from typing import Any
from agentauth.app import AgentAuthApp
from agentauth.models import AgentClaims, DelegatedToken
from agentauth.errors import AuthorizationError

class Agent:
    """An ephemeral agent registered under an AgentAuthApp.

    Business Logic:
    The Agent is a first-class principal in the AgentAuth trust model. 
    Unlike a simple token string, the Agent object maintains its own 
    identity (SPIFFE ID), scope, and lifecycle methods.

    An agent is ephemeral and task-scoped. It is created by an App to 
    perform a specific unit of work. Once the work is complete, the 
    agent should be 'released' to revoke its credentials and minimize 
    the security footprint.

    The Agent holds a back-reference to its parent `AgentAuthApp` to 
    facilitate lifecycle operations like renewal and delegation 
    without requiring the user to manage multiple objects.
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
        """Returns the Authorization header for HTTP requests.
        
        Usage:
            resp = httpx.get(url, headers=agent.bearer_header)
        """
        return {"Authorization": f"Bearer {self.access_token}"}

    def renew(self) -> None:
        """POST /v1/token/renew -- renew this agent's token in place.

        Business Logic:
        As an agent performs long-running tasks, its token may expire. 
        `renew()` performs a renewal ceremony with the broker.
        The broker issues a new token with the same identity and scope, 
        and automatically revokes the previous one.
        
        This method mutates the `Agent` instance in-place, ensuring that 
        the developer does not need to update their local object references.

        Raises:
            AuthorizationError: If the agent has already been released.
        """
        if self._released:
            raise AuthorizationError(
                # We'll need to construct a proper ProblemDetail for this in a real implementation
                # but for now, we raise to signal the state violation.
                None, # Placeholder
                403
            ) # type: ignore[arg-type]
        
        # Implementation deferred to Phase 3 orchestration
        raise NotImplementedError("Phase 3: Agent.renew() not yet implemented")

    def release(self) -> None:
        """POST /v1/token/release -- self-revoke on task completion.

        Business Logic:
        This is a critical security practice. Once an agent has finished 
        its task, it should explicitly signal the broker to revoke its 
        credentials. This reduces the window of opportunity for an 
        attacker to use a hijacked token.

        After calling `release()`, the agent instance is marked as released 
        and cannot be used for further operations.
        """
        if self._released:
            return
            
        # Implementation deferred to Phase 3 orchestration
        raise NotImplementedError("Phase 3: Agent.release() not yet implemented")

    def delegate(
        self,
        delegate_to: str,
        scope: list[str],
        *,
        ttl: int | None = None,
    ) -> DelegatedToken:
        """POST /v1/delegate -- create a scope-attenuated delegation token.

        Business Logic:
        Supports the 'Principle of Least Privilege' by allowing an agent 
        to spawn a secondary agent with a narrower set of permissions.
        
        Example:
            A 'Researcher' agent delegates only 'read:files' to a 
            'Summarizer' agent.

        Constraints:
        1. The new scope must be a subset of the current agent's scope.
        2. The maximum delegation depth is 5 (enforced by the broker).
        3. The `delegate_to` must be the SPIFFE ID of an existing agent.

        Returns:
            A `DelegatedToken` containing the new credentials and the 
            updated delegation chain.

        Raises:
            AuthorizationError: If the requested scope exceeds current authority.
        """
        # Implementation deferred to Phase 3 orchestration
        raise NotImplementedError("Phase 3: Agent.delegate() not yet implemented")

    def __repr__(self) -> str:
        return f"<<AgentAgent agent_id={self.agent_id} orch_id={self.orch_id} task_id={self.task_id}>"
