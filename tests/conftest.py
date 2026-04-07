"""Shared test fixtures for AgentAuth SDK integration tests.

Integration tests use a single broker app called "sdk-integration" registered
with scope ceiling: ["read:data:*", "write:data:*"].

Setup (run once before integration tests):

1. Start the broker:
   ./broker/scripts/stack_up.sh

2. Register the test app via aactl or admin API.

3. Export environment variables:
   export AGENTAUTH_BROKER_URL=http://127.0.0.1:8080
   export AGENTAUTH_ADMIN_SECRET=<your-secret>
   export AGENTAUTH_CLIENT_ID=<client_id>
   export AGENTAUTH_CLIENT_SECRET=<client_secret>

4. Run integration tests:
   uv run pytest tests/integration/ -v -m integration
"""

from __future__ import annotations

import os

import httpx
import pytest

from agentauth import AgentAuthApp


@pytest.fixture(scope="session")
def broker_url() -> str:
    """Base URL of the AgentAuth broker."""
    return os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")


@pytest.fixture(scope="session")
def app_credentials() -> dict[str, str]:
    """Credentials for the sdk-integration test app."""
    client_id: str | None = os.environ.get("AGENTAUTH_CLIENT_ID")
    client_secret: str | None = os.environ.get("AGENTAUTH_CLIENT_SECRET")
    if not client_id or not client_secret:
        pytest.skip(
            "Integration tests require AGENTAUTH_CLIENT_ID and "
            "AGENTAUTH_CLIENT_SECRET -- see tests/conftest.py"
        )
    return {"client_id": client_id, "client_secret": client_secret}


@pytest.fixture(scope="session")
def admin_token(broker_url: str) -> str:
    """Admin JWT for audit queries in tests."""
    secret: str | None = os.environ.get("AGENTAUTH_ADMIN_SECRET")
    if not secret:
        pytest.skip("AGENTAUTH_ADMIN_SECRET required for admin tests")
    resp = httpx.post(
        f"{broker_url}/v1/admin/auth",
        json={"secret": secret},
        timeout=10,
    )
    assert resp.status_code == 200, f"Admin auth failed: {resp.text}"
    token: str = resp.json()["access_token"]
    return token


@pytest.fixture(scope="session")
def client(broker_url: str, app_credentials: dict[str, str]) -> AgentAuthApp:
    """Initialized AgentAuthApp for integration tests.

    Session-scoped to avoid rate limit (10 req/min per client_id, burst 3).
    """
    return AgentAuthApp(
        broker_url=broker_url,
        client_id=app_credentials["client_id"],
        client_secret=app_credentials["client_secret"],
    )
