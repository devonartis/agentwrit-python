from __future__ import annotations

import time
import base64
from typing import Any
from agentauth.app import AgentAuthApp
from agentauth.agent import Agent
from agentauth.errors import (
    AuthorizationError,
    AuthenticationError,
    ProblemResponseError,
)
from agentauth.models import RegisterResult, AgentClaims, DelegationRecord

# This module will be used by AgentAuthApp to orchestrate the creation of agents.
# It implements the multi-step handshake required by the broker.

class AgentCreationOrchestrator:
    """Internal orchestrator for the agent registration lifecycle.

    Business Logic:
    The registration process is a multi-step 'ceremony' designed to prove
    that the app (the container) is authorizing a specific ephemeral
    agent to exist. 

    The sequence is:
    1. App Auth (handled by App)
    2. Launch Token Creation: App asks broker for a token with a specific scope ceiling.
    3. Challenge: Agent gets a random nonce from the broker.
    4. Signing: Agent signs the nonce with its private key.
    5. Registration: Agent presents the signature, public key, and launch token.
    6. Identity Minting: Broker verifies everything and issues the Agent JWT.

    This class encapsulates this complexity so the user only sees `app.create_agent()`.
    """

    def __init__(self, app: AgentAuthApp) -> None:
        self._app = app
        self._transport = app._transport

    def orchestrate(
        self,
        orch_id: str,
        task_id: str,
        requested_scope: list[str],
        *,
        private_key: Any | None = None,
        max_ttl: int = 300,
        label: str | None = None,
    ) -> Agent:
        """Executes the full agent creation flow.

        Args:
            orch_id: Identifier for the orchestration system.
            task_id: Identifier for the specific unit of work.
            requested_scope: The scope the agent is requesting.
            private_key: The agent's Ed25519 private key. If None, one is generated.
            max_ttl: Maximum lifetime for the agent token.
            label: Optional audit label for the launch token.

        Returns:
            A connected Agent object.

        Raises:
            AuthorizationError: If the requested scope exceeds the app's ceiling.
            AuthenticationError: If app credentials fail.
            ProblemResponseError: For broker-side business rule rejections.
        """
        # 1. Ensure the App is authenticated
        self._app._ensure_app_authenticated()

        # 2. Create Launch Token
        # The broker requires an 'agent_name'. We auto-generate it from orch/task.
        agent_name = label or f"{orch_id}/{task_id}"
        
        lt_response = self._transport.request(
            "POST",
            "/v1/app/launch-tokens",
            json={
                "agent_name": agent_name,
                "allowed_scope": requested_scope,
                "ttl": max_ttl,
                "single_use": True,
            }
        )
        launch_token = lt_response.json()["launch_token"]

        # 3. Get Challenge (Nonce)
        challenge_response = self._transport.request("GET", "/v1/challenge")
        challenge_data = challenge_response.json()
        nonce_hex = challenge_data["nonce"]

        # 4. Cryptographic Signing
        # If no key provided, generate one for this ephemeral agent.
        from agentauth.crypto import (
            generate_keypair, 
            sign_nonce, 
            export_public_key_b64, 
            encode_signature_b64
        )
        
        if private_key is None:
            private_key = generate_keypair()

        signature_bytes = sign_nonce(private_key, nonce_hex)
        public_key_b64 = export_public_key_b64(private_key)
        signature_b64 = encode_signature_b64(signature_bytes)

        # 5. Register Agent
        reg_response = self._transport.request(
            "POST",
            "/v1/register",
            json={
                "launch_token": launch_token,
                "nonce": nonce_hex,
                "public_key": public_key_b64,
                "signature": signature_b64,
                "orch_id": orch_id,
                "task_id": task_id,
                "requested_scope": requested_scope,
            }
        )
        reg_data = reg_response.json()

        # 6. Build the Agent object
        # We need to parse the claims from the issued access_token to populate the Agent object.
        # In a real implementation, we would decode the JWT locally (if possible) 
        # or rely on the registration response if it includes claims.
        # For the MVP, we'll assume the registration response is complete.
        
        # Note: We need the claims to populate agent.scope, agent.task_id, etc.
        # If the broker doesn't return them in /register, we'd need a decode step.
        # Let's assume for now the agent_id and token are sufficient and 
        # we'll use a simplified construction.
        
        return Agent(
            app=self._app,
            agent_id=reg_data["agent_id"],
            access_token=reg_data["access_token"],
            expires_in=reg_data["expires_in"],
            scope=requested_scope, # Simplification for MVP
            task_id=task_id,
            orch_id=orch_id,
        )
