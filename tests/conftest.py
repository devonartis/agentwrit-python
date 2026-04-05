"""Shared test fixtures for AgentAuth SDK integration tests.

## What is the test app?

Integration tests use a single broker app called "sdk-integration" registered
with two scope tiers:
  - read:data:*   -- issued immediately
  - write:data:*  -- issued immediately

This single app covers all test scenarios:
  - Normal flow: client.get_token("agent", ["read:data:*"]) → JWT directly
  - Write flow:  client.get_token("agent", ["write:data:*"]) → JWT directly

The app ID (app-sdk-integration-...) and client credentials below are local
test fixtures only -- valid against a locally running broker Docker container.
They are NOT production credentials and NOT shared anywhere.

## Setup (run once before integration tests)

1. Start the broker:
   ```bash
   cd /path/to/authAgent2
   export AA_ADMIN_SECRET=<your-secret>
   ./scripts/stack_up.sh
   ```

2. Get an admin token:
   ```bash
   curl -s -X POST http://127.0.0.1:8080/v1/admin/auth \\
     -H "Content-Type: application/json" \\
     -d '{"secret": "<your-secret>"}'
   # Response: {"access_token": "eyJ...", "expires_in": 300}
   ```

3. Register the test app:
   ```bash
   curl -s -X POST http://127.0.0.1:8080/v1/admin/apps \\
     -H "Authorization: Bearer <admin-token>" \\
     -H "Content-Type: application/json" \\
     -d '{
       "name": "sdk-integration",
       "scopes": ["read:data:*", "write:data:*"]
     }'
   # Response: {"client_id": "...", "client_secret": "..."}
   # Save these values as env vars below.
   ```

4. Export environment variables:
   ```bash
   export AGENTAUTH_BROKER_URL=http://127.0.0.1:8080
   export AGENTAUTH_ADMIN_SECRET=<your-secret>
   export AGENTAUTH_CLIENT_ID=<client_id from step 3>
   export AGENTAUTH_CLIENT_SECRET=<client_secret from step 3>
   ```

5. Run integration tests:
   ```bash
   uv run pytest tests/integration/ -v -m integration
   ```
"""

from __future__ import annotations

import os

import pytest
import requests as requests_lib

from agentauth import AgentAuthApp


@pytest.fixture(scope="session")
def broker_url() -> str:
    """Base URL of the AgentAuth broker. Defaults to local Docker instance."""
    return os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")


@pytest.fixture(scope="session")
def app_credentials() -> dict[str, str]:
    """Credentials for the sdk-integration test app.

    This is a LOCAL test app registered against the Docker broker.
    It has scopes ["read:data:*", "write:data:*"].
    Set AGENTAUTH_CLIENT_ID and AGENTAUTH_CLIENT_SECRET before running.
    """
    client_id: str | None = os.environ.get("AGENTAUTH_CLIENT_ID")
    client_secret: str | None = os.environ.get("AGENTAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        pytest.skip(
            "Integration tests require AGENTAUTH_CLIENT_ID and "
            "AGENTAUTH_CLIENT_SECRET -- see tests/conftest.py setup instructions"
        )
    return {"client_id": client_id, "client_secret": client_secret}


@pytest.fixture(scope="session")
def admin_token(broker_url: str) -> str:
    """Admin JWT used for audit queries in tests.

    Admin token has: admin:launch-tokens:*, admin:revoke:*, admin:audit:*
    NOTE: Some endpoints require app:launch-tokens:* scope --
    use app_token fixture for those, not this one.
    """
    secret: str | None = os.environ.get("AGENTAUTH_ADMIN_SECRET")
    if not secret:
        pytest.skip(
            "AGENTAUTH_ADMIN_SECRET required for tests that query audit events"
        )
    resp = requests_lib.post(
        f"{broker_url}/v1/admin/auth",
        json={"secret": secret},
        timeout=10,
    )
    assert resp.status_code == 200, f"Admin auth failed: {resp.text}"
    token: str = resp.json()["access_token"]
    return token


@pytest.fixture(scope="session")
def app_token(client: AgentAuthApp) -> str:
    """App-level JWT for the sdk-integration test app.

    Carries scope: app:launch-tokens:*, app:agents:*, app:audit:read
    Used by tests that need an app-scoped JWT.

    Reuses the already-authenticated client's token to avoid making a second
    POST /v1/app/auth call that would hit the per-client_id rate limit.
    """
    # _ensure_app_token() returns valid app JWT, re-auths only if near expiry.
    # Using the client's internal method avoids a redundant auth call.
    return client._ensure_app_token()  # noqa: SLF001


@pytest.fixture(scope="session")
def client(broker_url: str, app_credentials: dict[str, str]) -> AgentAuthApp:
    """Initialized AgentAuthApp for the sdk-integration test app.

    Session-scoped: one client shared across all integration tests to avoid
    triggering the broker's rate limit (10 req/min per client_id, burst 3)
    from repeated POST /v1/app/auth calls at fixture setup.

    Scopes available:
      - read:data:*   → issued immediately
      - write:data:*  → issued immediately
    """
    return AgentAuthApp(
        broker_url=broker_url,
        client_id=app_credentials["client_id"],
        client_secret=app_credentials["client_secret"],
    )
