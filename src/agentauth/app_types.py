from __future__ import annotations

from dataclasses import dataclass


@dataclass
class _AppSession:
    """Internal representation of an authenticated application session.

    Business Logic:
    Tracks the app's JWT and its expiry time. This is used by `AgentAuthApp`
    to implement lazy authentication and automatic re-authentication
    before the token expires.
    """
    access_token: str
    expires_at: float
    scopes: list[str]
