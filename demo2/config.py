"""Environment configuration for the Support Ticket demo."""

from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class DemoConfig:
    """All external configuration loaded from environment variables."""

    broker_url: str
    client_id: str
    client_secret: str
    admin_secret: str
    llm_base_url: str
    llm_api_key: str
    llm_model: str

    @classmethod
    def from_env(cls) -> DemoConfig:
        return cls(
            broker_url=os.environ.get("AGENTAUTH_BROKER_URL", "http://localhost:8080"),
            client_id=os.environ.get("AGENTAUTH_CLIENT_ID", ""),
            client_secret=os.environ.get("AGENTAUTH_CLIENT_SECRET", ""),
            admin_secret=os.environ.get("AGENTAUTH_ADMIN_SECRET", ""),
            llm_base_url=os.environ.get("LLM_BASE_URL", ""),
            llm_api_key=os.environ.get("LLM_API_KEY", "EMPTY"),
            llm_model=os.environ.get("LLM_MODEL", ""),
        )


# Scope ceiling for the support app — registered with broker at setup time.
# Agents get subsets of this, never the full ceiling.
APP_SCOPE_CEILING: list[str] = [
    "read:tickets:*",
    "read:customers:*",
    "write:customers:*",
    "read:kb:*",
    "read:billing:*",
    "write:billing:*",
    "write:notes:*",
    "write:email:internal",
    "delete:account:*",
]
