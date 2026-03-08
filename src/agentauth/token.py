"""In-memory token cache for the AgentAuth SDK.

This module provides the TokenCache class, which stores agent JWTs in memory
and manages their lifecycle — expiry detection, proactive renewal signaling,
and thread-safe concurrent access.

How caching works:
    1. When get_token() issues a new agent JWT, it calls put() to store the
       token keyed by (agent_name, frozenset(scope)).
    2. On subsequent get_token() calls with the same arguments, get() returns
       the cached token immediately (zero network calls).
    3. When 80% of the token's TTL has elapsed, needs_renewal() returns True,
       triggering the SDK to fetch a fresh token from the broker proactively.
    4. Expired tokens are automatically evicted on the next get() access.

Thread safety:
    All public methods are protected by threading.Lock. Multiple threads
    can safely call get_token() concurrently without external synchronization.

Pattern alignment:
    - C2 (Short-Lived Task-Scoped Tokens): caching reduces broker load while
      ensuring tokens are renewed before expiry.

Patch point for tests: agentauth.token.time.time
"""

from __future__ import annotations

import threading
import time
from typing import NamedTuple


class _Entry(NamedTuple):
    token: str
    stored_at: float  # wall-clock seconds at put() time
    expires_in: int  # TTL in seconds as provided by the broker


def _make_key(agent_name: str, scope: list[str]) -> tuple[str, frozenset[str]]:
    """Build a cache key that is invariant to scope order."""
    return (agent_name, frozenset(scope))


class TokenCache:
    """In-memory token cache with expiry and renewal-threshold detection.

    Args:
        renewal_threshold: Fraction of a token's TTL that must elapse before
            :meth:`needs_renewal` returns ``True``.  Defaults to ``0.8``
            (trigger renewal when 80 % of the TTL has elapsed).
    """

    def __init__(self, renewal_threshold: float = 0.8) -> None:
        self._renewal_threshold = renewal_threshold
        self._store: dict[tuple[str, frozenset[str]], _Entry] = {}
        self._lock = threading.Lock()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get(self, agent_name: str, scope: list[str]) -> str | None:
        """Return the cached token, or *None* if absent or expired."""
        key = _make_key(agent_name, scope)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return None
            if self._is_expired(entry):
                del self._store[key]
                return None
            return entry.token

    def put(
        self,
        agent_name: str,
        scope: list[str],
        token: str,
        *,
        expires_in: int,
    ) -> None:
        """Store *token* in the cache.

        Args:
            agent_name: Logical name of the agent.
            scope: List of scope strings (order is irrelevant).
            token: The JWT or opaque token string to cache.
            expires_in: Token lifetime in seconds, as returned by the broker.
        """
        key = _make_key(agent_name, scope)
        entry = _Entry(
            token=token,
            stored_at=time.time(),
            expires_in=expires_in,
        )
        with self._lock:
            self._store[key] = entry

    def needs_renewal(self, agent_name: str, scope: list[str]) -> bool:
        """Return *True* when the token has consumed >= *renewal_threshold* of its TTL.

        Returns *False* if the key is unknown.
        Thread-safe: entry fields are captured inside the lock before release.
        """
        key = _make_key(agent_name, scope)
        with self._lock:
            entry = self._store.get(key)
            if entry is None:
                return False
            # Capture inside lock to avoid TOCTOU with concurrent remove/put
            stored_at: float = entry.stored_at
            expires_in_secs: int = entry.expires_in

        elapsed: float = time.time() - stored_at
        if expires_in_secs == 0:
            return True
        fraction_elapsed: float = elapsed / expires_in_secs
        return fraction_elapsed >= self._renewal_threshold

    def remove(self, agent_name: str, scope: list[str]) -> None:
        """Remove a cache entry.  No-op if the key does not exist."""
        key = _make_key(agent_name, scope)
        with self._lock:
            self._store.pop(key, None)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _is_expired(entry: _Entry) -> bool:
        """Return True if the entry's wall-clock TTL has elapsed."""
        age = time.time() - entry.stored_at
        return age >= entry.expires_in
