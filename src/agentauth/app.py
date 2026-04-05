"""AgentAuthApp -- main entry point for the AgentAuth Python SDK.

Implements the Ephemeral Agent Credentialing pattern (v1.2):
  - C1 (Ephemeral Identity Issuance): Ed25519 challenge-response via get_token()
  - C2 (Task-Scoped Tokens): action:resource:identifier scope on every JWT
  - C3 (Zero-Trust Enforcement): every broker call validated independently
  - C4 (Expiration & Revocation): short TTLs + explicit revoke_token()
  - C7 (Delegation Chain): scope attenuation via delegate()

Standards alignment:
  - NIST IR 8596: unique AI agent identities via SPIFFE IDs
  - NIST SP 800-207: zero-trust per-request validation
  - OWASP ASI03: least-privilege via scope ceiling enforcement
  - IETF WIMSE: delegation chain re-binding at each hop

SECURITY INVARIANT: client_secret must NEVER appear in repr, str, logs,
or error messages emitted from this module.
"""

from __future__ import annotations

import threading
import time
from typing import TypedDict

import requests

from agentauth.crypto import generate_keypair, sign_nonce
from agentauth.errors import parse_error_response
from agentauth.retry import request_with_retry
from agentauth.token import TokenCache

# ------------------------------------------------------------------
# Broker response shapes (typed for mypy)
# ------------------------------------------------------------------


class _AppAuthResponse(TypedDict):
    """POST /v1/app/auth response -- app authenticates with client_id + client_secret."""

    access_token: str
    expires_in: int
    token_type: str
    scopes: list[str]


class _LaunchTokenResponse(TypedDict):
    """POST /v1/app/launch-tokens response -- single-use launch token for agent registration."""

    launch_token: str
    expires_at: str


class _ChallengeResponse(TypedDict):
    """GET /v1/challenge response -- 64-char hex nonce with 30s TTL."""

    nonce: str
    expires_in: int


class _RegisterResponse(TypedDict):
    """POST /v1/register response -- agent JWT with SPIFFE ID (C1 Ephemeral Identity)."""

    agent_id: str
    access_token: str
    expires_in: int


class _DelegateResponse(TypedDict):
    """POST /v1/delegate response -- scope-attenuated JWT (C7 Delegation Chain)."""

    access_token: str
    expires_in: int


class _ValidateTokenResponse(TypedDict, total=False):
    """POST /v1/token/validate response -- online token validation (C3 Zero-Trust)."""

    valid: bool
    claims: dict[str, object]
    error: str


class AgentAuthApp:
    """Client for the AgentAuth credential broker.

    Handles app authentication automatically on construction and re-authenticates
    transparently when the app token is close to expiry.

    Args:
        broker_url: Base URL of the AgentAuth broker (trailing slash is stripped).
        client_id: The app's ``client_id`` issued by the operator.
        client_secret: The app's ``client_secret`` issued by the operator.
            NEVER logged, printed, or included in error messages.
        max_retries: Maximum retry attempts for transient broker failures (default 3).
        verify: Whether to verify TLS certificates (default True).
    """

    def __init__(
        self,
        broker_url: str,
        client_id: str,
        client_secret: str,
        *,
        max_retries: int = 3,
        verify: bool = True,
    ) -> None:
        # Store connection parameters.
        # broker_url is stripped of trailing slash to normalize URL construction.
        self._broker_url: str = broker_url.rstrip("/")
        self._client_id: str = client_id
        # SECURITY: client_secret is stored but NEVER exposed in repr, str,
        # error messages, or logs. See __repr__() at the bottom of this file.
        self._client_secret: str = client_secret
        self._max_retries: int = max_retries

        # HTTP session — reused for connection pooling and TLS verification.
        # verify=True by default enforces TLS certificate validation (C3 Zero-Trust).
        self._session: requests.Session = requests.Session()
        self._session.verify = verify
        self._session.headers.update({"Content-Type": "application/json"})

        # App-level JWT state. The app authenticates with the broker using
        # client_id + client_secret, and receives a short-lived JWT that
        # authorizes the app to create launch tokens for agents.
        # Protected by _app_token_lock for thread-safe access.
        self._app_token: str | None = None
        self._app_token_expires_at: float = 0.0
        self._app_token_lock: threading.Lock = threading.Lock()

        # Agent token cache — stores issued agent JWTs keyed by
        # (agent_name, frozenset(scope)). Thread-safe internally.
        # Tokens are auto-renewed at 80% of their TTL.
        self._token_cache: TokenCache = TokenCache()

        # Authenticate the app immediately on construction.
        # This is a deliberate fail-fast design: if client_id/client_secret
        # are wrong, AuthenticationError is raised HERE at init time,
        # not later during a get_token() call.
        self._authenticate_app()

    # ------------------------------------------------------------------
    # App authentication
    # ------------------------------------------------------------------

    def _authenticate_app(self) -> None:
        """POST /v1/app/auth to obtain the app-level JWT.

        Raises:
            AuthenticationError: On 401 -- bad client_id / client_secret.
            AgentAuthError: On other broker errors.
        """
        url = f"{self._broker_url}/v1/app/auth"
        payload: dict[str, str] = {
            "client_id": self._client_id,
            "client_secret": self._client_secret,
        }

        # Direct session.post -- NOT _request -- so that init failures are
        # NOT retried (fail fast, avoid obscure retry delays on wrong creds).
        response = self._session.post(url, json=payload)

        if response.status_code != 200:
            try:
                body: dict[str, object] = response.json()
            except Exception:
                body = {}
            raise parse_error_response(
                response.status_code,
                body,
                client_id=self._client_id,
            )

        auth_data: _AppAuthResponse = response.json()
        with self._app_token_lock:
            self._app_token = auth_data["access_token"]
            self._app_token_expires_at = time.time() + auth_data["expires_in"]

    def _ensure_app_token(self) -> str:
        """Return a valid app token, re-authenticating if necessary.

        Thread-safe: reads and writes to app token state are protected by lock.

        Returns:
            The current app JWT string.
        """
        with self._app_token_lock:
            token: str | None = self._app_token
            expires_at: float = self._app_token_expires_at

        # 10-second buffer before actual expiry
        if token is not None and time.time() < expires_at - 10:
            return token
        self._authenticate_app()
        with self._app_token_lock:
            return self._app_token  # type: ignore[return-value]

    # ------------------------------------------------------------------
    # Generic request helper
    # ------------------------------------------------------------------

    def _request(
        self,
        method: str,
        url: str,
        *,
        json: dict[str, object] | None = None,
        auth_token: str | None = None,
    ) -> requests.Response:
        """Thin wrapper around request_with_retry for all SDK HTTP calls."""
        return request_with_retry(
            self._session,
            method,
            url,
            json=json,
            auth_token=auth_token,
            max_retries=self._max_retries,
        )

    # ------------------------------------------------------------------
    # Agent token operations
    # ------------------------------------------------------------------

    def get_token(
        self,
        agent_name: str,
        scope: list[str],
        *,
        task_id: str | None = None,
        orch_id: str | None = None,
    ) -> str:
        """Obtain a scoped agent credential via the 3-step broker flow.

        Steps:
            1. Check cache -- return immediately on hit (no HTTP).
            2. Ensure app token is valid (re-auth if expired).
            3. POST /v1/app/launch-tokens -- get a single-use launch token.
            4. Generate an ephemeral Ed25519 keypair (never persisted).
            5. GET /v1/challenge -- fetch a 30-second nonce.
            6. Sign the nonce with the ephemeral private key.
            7. POST /v1/register -- exchange (launch_token + signed nonce +
               public_key) for an agent JWT. NO Bearer auth on this call;
               the launch_token in the body authenticates the request.
            8. Cache the result and return the agent JWT.

        Args:
            agent_name: Logical name for the agent (used as a cache key).
            scope: List of scope strings (e.g. ``["read:data:*"]``).
            task_id: Optional task identifier threaded through to /v1/register.
            orch_id: Optional orchestrator identifier threaded through.
        Returns:
            Agent JWT string.

        Raises:
            ScopeCeilingError: Requested scope exceeds the app's ceiling.
            AgentAuthError: On any other broker error.
        """
        # 1. Cache check -- BEFORE any HTTP calls (G13: include task_id/orch_id in key)
        cached = self._token_cache.get(
            agent_name, scope, task_id=task_id, orch_id=orch_id,
        )
        if cached is not None and not self._token_cache.needs_renewal(
            agent_name, scope, task_id=task_id, orch_id=orch_id,
        ):
            return cached

        # 2. Ensure app token is fresh
        app_token = self._ensure_app_token()

        # 3. POST /v1/app/launch-tokens
        # The launch token is a single-use, short-lived token that authorizes
        # one agent registration. It binds the agent_name and scope to a
        # specific registration attempt.
        launch_url = f"{self._broker_url}/v1/app/launch-tokens"
        launch_payload: dict[str, object] = {
            "agent_name": agent_name,
            "allowed_scope": scope,
        }

        launch_resp = self._request(
            "POST",
            launch_url,
            json=launch_payload,
            auth_token=app_token,
        )
        if not launch_resp.ok:
            try:
                body = launch_resp.json()
            except Exception:
                body = {}
            raise parse_error_response(launch_resp.status_code, body)

        launch_data = launch_resp.json()
        launch_token = launch_data["launch_token"]

        # 4. Generate ephemeral Ed25519 keypair (never persisted to disk)
        private_key, public_key_b64 = generate_keypair()

        # 5. GET /v1/challenge
        challenge_url = f"{self._broker_url}/v1/challenge"
        challenge_resp = self._request("GET", challenge_url)
        if not challenge_resp.ok:
            try:
                body = challenge_resp.json()
            except Exception:
                body = {}
            raise parse_error_response(challenge_resp.status_code, body)

        nonce = challenge_resp.json()["nonce"]

        # 6. Sign the nonce
        signature = sign_nonce(private_key, nonce)

        # 7. POST /v1/register
        # This is the core identity issuance step (C1 Ephemeral Identity).
        # IMPORTANT: This endpoint does NOT use Bearer auth. The launch_token
        # in the body IS the authentication. The broker validates:
        #   - launch_token is valid and unused
        #   - nonce matches the challenge and is within its 30-second TTL
        #   - public_key matches the signature over the nonce
        #   - requested_scope is within the launch token's allowed_scope
        # On success, the broker returns an agent JWT with a unique SPIFFE ID.
        #
        # orch_id and task_id are REQUIRED by the broker but the SDK makes
        # them optional for the developer with sensible defaults.
        register_url = f"{self._broker_url}/v1/register"
        register_payload: dict[str, object] = {
            "launch_token": launch_token,
            "nonce": nonce,
            "public_key": public_key_b64,
            "signature": signature,
            "requested_scope": scope,
            "orch_id": orch_id or "sdk",
            "task_id": task_id or "default",
        }

        register_resp = self._request(
            "POST",
            register_url,
            json=register_payload,
            # auth_token intentionally omitted -- launch_token in body is the auth
        )
        if not register_resp.ok:
            try:
                body = register_resp.json()
            except Exception:
                body = {}
            raise parse_error_response(register_resp.status_code, body)

        reg_data: _RegisterResponse = register_resp.json()
        agent_token: str = reg_data["access_token"]
        expires_in: int = reg_data["expires_in"]

        # 8. Cache the result (G13: include task_id/orch_id in key)
        self._token_cache.put(
            agent_name,
            scope,
            agent_token,
            expires_in=expires_in,
            task_id=task_id,
            orch_id=orch_id,
        )

        return agent_token

    def delegate(
        self,
        token: str,
        to_agent_id: str,
        scope: list[str],
        ttl: int = 60,
    ) -> str:
        """POST /v1/delegate -- create a delegated token for another agent.

        Args:
            token: The calling agent's JWT (used as Bearer auth).
            to_agent_id: SPIFFE ID of the agent to delegate to.
            scope: List of scopes to delegate (must be subset of token's scope).
            ttl: Lifetime of the delegated token in seconds (default 60).

        Returns:
            The delegated access_token string.
        """
        url: str = f"{self._broker_url}/v1/delegate"
        payload: dict[str, object] = {
            "delegate_to": to_agent_id,
            "scope": scope,
            "ttl": ttl,
        }
        response = self._request("POST", url, json=payload, auth_token=token)
        if response.status_code != 200:
            try:
                error_body: dict[str, object] = response.json()
            except Exception:
                error_body = {}
            raise parse_error_response(response.status_code, error_body)
        delegate_data: _DelegateResponse = response.json()
        return delegate_data["access_token"]

    def revoke_token(self, token: str) -> None:
        """POST /v1/token/release -- self-revoke an agent token.

        Args:
            token: The agent JWT to revoke (used as Bearer auth).

        Returns:
            None on success (204 from broker).
        """
        url: str = f"{self._broker_url}/v1/token/release"
        response = self._request("POST", url, auth_token=token)
        if response.status_code not in (200, 204):
            try:
                revoke_error_body: dict[str, object] = response.json()
            except Exception:
                revoke_error_body = {}
            raise parse_error_response(response.status_code, revoke_error_body)

    def validate_token(self, token: str) -> _ValidateTokenResponse:
        """POST /v1/token/validate -- online token validation (no auth required).

        Args:
            token: The JWT string to validate.

        Returns:
            Full response dict: {"valid": bool, "claims": {...}} or
            {"valid": false, "error": "..."}.
        """
        url: str = f"{self._broker_url}/v1/token/validate"
        response = self._request("POST", url, json={"token": token})
        if response.status_code != 200:
            try:
                validate_error_body: dict[str, object] = response.json()
            except Exception:
                validate_error_body = {}
            raise parse_error_response(response.status_code, validate_error_body)
        validate_data: _ValidateTokenResponse = response.json()
        return validate_data

    # ------------------------------------------------------------------
    # Representation -- NEVER expose client_secret
    # ------------------------------------------------------------------

    def __repr__(self) -> str:
        return f"AgentAuthApp(broker_url={self._broker_url!r}, client_id={self._client_id!r})"
