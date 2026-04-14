"""Environment configuration for the MedAssist demo."""

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
            llm_base_url=os.environ.get("LLM_BASE_URL", "https://api.openai.com/v1"),
            llm_api_key=os.environ.get("LLM_API_KEY", ""),
            llm_model=os.environ.get("LLM_MODEL", "gpt-4o-mini"),
        )


APP_SCOPE_CEILING: list[str] = [
    "read:records:*",
    "write:records:*",
    "read:labs:*",
    "write:prescriptions:*",
    "read:formulary:*",
    "read:billing:*",
    "write:billing:*",
    "read:insurance:*",
]
