from __future__ import annotations

import time
from typing import Any
from agentauth.app_types import _AppSession
from agentauth.errors import AuthenticationError, TransportError
from agentauth.models import HealthStatus, ValidateResult
from agentauth import validate as module_validate
from agentauth._transport import AgentAuthTransport

class AgentAuthApp:
    """The developer's app container. Manages authentication internally,
    creates agents, validates tokens, and gates tool access.

    All agent authority flows from this app's scope ceiling.
    """

    def __init__(
        self,
        broker_url: str,
        client_id: str,
        client_secret: str,
        *,
        timeout: float = 10.0,
        user_agent: str | None = None,
    ) -> None:
        """Initialize the AgentAuthApp.

        Args:
            broker_url: Base URL of the AgentAuth broker.
            client_id: App client ID from operator.
            client_secret: App client secret from operator.
            timeout: HTTP request timeout in seconds.
            user_agent: Optional User-Agent header.
        """
        self.broker_url = broker_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.timeout = timeout
        self.user_agent = user_agent
        
        self._transport = AgentAuthTransport(
            broker_url=self.broker_url,
            timeout=self.timeout,
            user_agent=self.user_agent
        )
        self._session: _AppSession | None = None

    def _ensure_app_authenticated(self) -> None:
        """Internal method to ensure the app has a valid JWT.

        Business Logic:
        Implements "Lazy Authentication". The app doesn't authenticate during 
        `__init__`. Instead, it waits until the first operation that requires 
        authorization (like `create_agent` or `health`). 
        
        If no session exists, or the current session JWT is expired (or close 
        to expiry), it performs a `POST /v1/app/auth` to obtain a new one.
        """
        now = time.time()
        
        # Re-authenticate if no session exists, or if the token is within 
        # a 60-second buffer of expiring.
        if (
            self._session is None or 
            self._session.expires_at is None or 
            (self._session.expires_at - now) <<  60
        ):
            self._authenticate()

    def _authenticate(self) -> None:
        """Performs the actual authentication request to the broker.

        Business Logic:
        Exchange `client_id` and `client_secret` for an app JWT.
        Updates the internal `_session` with the new JWT and expiry.

        Raises:
            AuthenticationError: If credentials are invalid.
            TransportError: If the broker is unreachable.
        """
        response = self._transport.request(
            "POST",
            "/v1/app/auth",
            json={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            }
        )
        
        data = response.json()
        
        # The broker returns expires_at as a timestamp (int)
        self._session = _AppSession(
            access_token=data["access_token"],
            expires_at=float(data["expires_at"]),
            scopes=data.get("scopes", []),
        )

    def create_agent(
        self,
        orch_id: str,
        task_id: str,
        requested_scope: list[str],
        *,
        private_key: Any | None = None,
        max_ttl: int = 300,
        label: str | None = None,
    ) -> Agent:
        """Create an ephemeral agent under this app.
        
        Implementation:
        Uses the `AgentCreationOrchestrator` to perform the multi-step
        challenge-response registration ceremony.
        """
        from agentauth.orchestrator import AgentCreationOrchestrator
        orchestrator = AgentCreationOrchestrator(self)
        return orchestrator.orchestrate(
            orch_id=orch_id,
            task_id=task_id,
            requested_scope=requested_scope,
            private_key=private_key,
            max_ttl=max_ttl,
            label=label
        )

    def validate(self, token: str) -> ValidateResult:
        """POST /v1/token/validate -- verify any token via the broker.

        Convenience shortcut for `agentauth.validate(self.broker_url, token)`.
        """
        return module_validate(self.broker_url, token, timeout=self.timeout)

    def health(self) -> HealthStatus:
        """GET /v1/health -- broker health check.

        Ensures the app can communicate with the broker and that the 
        broker's internal services (like the DB) are operational.
        """
        self._ensure_app_authenticated()
        
        response = self._transport.request("GET", "/v1/health")
        data = response.json()
        
        return HealthStatus(
            status=data["status"],
            version=data["version"],
            uptime=data["uptime"],
            db_connected=data["db_connected"],
            audit_events_count=data["audit_events_count"],
        )

    def close(self) -> None:
        """Closes the underlying transport client."""
        self._transport.close()
