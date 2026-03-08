"""
# ============================================================
# TEST: Token Cache
# File: tests/unit/test_token_cache.py
# Module: agentauth.token
# Type: Unit (no broker, no I/O)
# ============================================================
#
# COVERAGE GOALS
# --------------
# - get() returns None for unknown key
# - put() then get() returns the token
# - Scope order is irrelevant (frozenset key)
# - Expired token (expires_in=0) returns None
# - needs_renewal() returns False before threshold, True after
# - remove() clears the entry
# - threading.Lock is present on the cache instance
#
# PATCH POINT
# -----------
# agentauth.token.time.time  -- controls simulated wall clock
# ============================================================
"""

import threading
from unittest.mock import patch

import pytest

from agentauth.token import TokenCache

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture()
def cache() -> TokenCache:
    """Default TokenCache with 0.8 renewal threshold."""
    return TokenCache(renewal_threshold=0.8)


# ---------------------------------------------------------------------------
# Basic get / put
# ---------------------------------------------------------------------------


class TestGetPut:
    def test_get_unknown_returns_none(self, cache: TokenCache) -> None:
        """get() on a key that was never put must return None."""
        result = cache.get("agent-1", ["read:data:*"])
        assert result is None

    def test_put_then_get_returns_token(self, cache: TokenCache) -> None:
        """A token stored with put() is returned by get()."""
        cache.put("agent-1", ["read:data:*"], "tok-abc", expires_in=300)
        result = cache.get("agent-1", ["read:data:*"])
        assert result == "tok-abc"

    def test_different_agents_are_isolated(self, cache: TokenCache) -> None:
        """Two agents with the same scope do not share tokens."""
        cache.put("agent-A", ["read:data:*"], "tok-A", expires_in=300)
        cache.put("agent-B", ["read:data:*"], "tok-B", expires_in=300)
        assert cache.get("agent-A", ["read:data:*"]) == "tok-A"
        assert cache.get("agent-B", ["read:data:*"]) == "tok-B"

    def test_same_agent_different_scopes_are_isolated(self, cache: TokenCache) -> None:
        """Same agent, different scopes produce different cache entries."""
        cache.put("agent-1", ["read:data:*"], "tok-read", expires_in=300)
        cache.put("agent-1", ["write:data:*"], "tok-write", expires_in=300)
        assert cache.get("agent-1", ["read:data:*"]) == "tok-read"
        assert cache.get("agent-1", ["write:data:*"]) == "tok-write"


# ---------------------------------------------------------------------------
# Scope order invariance
# ---------------------------------------------------------------------------


class TestScopeOrder:
    def test_scope_order_does_not_affect_cache_key(self, cache: TokenCache) -> None:
        """put() with one scope order is retrievable with reversed order."""
        scopes_a = ["write:data:*", "read:data:*"]
        scopes_b = ["read:data:*", "write:data:*"]

        cache.put("agent-1", scopes_a, "tok-multi", expires_in=300)
        result = cache.get("agent-1", scopes_b)
        assert result == "tok-multi"

    def test_needs_renewal_scope_order_invariant(self, cache: TokenCache) -> None:
        """needs_renewal() is also scope-order-agnostic."""
        scopes_a = ["write:data:*", "read:data:*"]
        scopes_b = ["read:data:*", "write:data:*"]

        cache.put("agent-1", scopes_a, "tok-multi", expires_in=100)
        # Before threshold -- False either way
        assert cache.needs_renewal("agent-1", scopes_b) is False


# ---------------------------------------------------------------------------
# Expiry
# ---------------------------------------------------------------------------


class TestExpiry:
    def test_expired_token_returns_none(self, cache: TokenCache) -> None:
        """expires_in=0 means the token is already expired; get() returns None."""
        cache.put("agent-1", ["read:data:*"], "tok-dead", expires_in=0)
        result = cache.get("agent-1", ["read:data:*"])
        assert result is None

    def test_token_evicted_after_ttl_passes(self, cache: TokenCache) -> None:
        """Simulate clock advancing past TTL; get() returns None."""
        with patch("agentauth.token.time.time") as mock_time:
            mock_time.return_value = 1000.0
            cache.put("agent-1", ["read:data:*"], "tok-short", expires_in=10)

            # Advance past expiry
            mock_time.return_value = 1011.0
            result = cache.get("agent-1", ["read:data:*"])
        assert result is None

    def test_token_valid_just_before_expiry(self, cache: TokenCache) -> None:
        """Token is still returned when clock is just before expiry."""
        with patch("agentauth.token.time.time") as mock_time:
            mock_time.return_value = 1000.0
            cache.put("agent-1", ["read:data:*"], "tok-alive", expires_in=10)

            # One second before expiry
            mock_time.return_value = 1009.0
            result = cache.get("agent-1", ["read:data:*"])
        assert result == "tok-alive"


# ---------------------------------------------------------------------------
# needs_renewal
# ---------------------------------------------------------------------------


class TestNeedsRenewal:
    def test_needs_renewal_false_before_threshold(self, cache: TokenCache) -> None:
        """needs_renewal() is False when less than 80% of TTL has elapsed."""
        with patch("agentauth.token.time.time") as mock_time:
            mock_time.return_value = 1000.0
            cache.put("agent-1", ["read:data:*"], "tok-fresh", expires_in=100)

            # 50% elapsed (50 of 100 seconds)
            mock_time.return_value = 1050.0
            assert cache.needs_renewal("agent-1", ["read:data:*"]) is False

    def test_needs_renewal_true_at_threshold(self, cache: TokenCache) -> None:
        """needs_renewal() is True when exactly 80% of TTL has elapsed."""
        with patch("agentauth.token.time.time") as mock_time:
            mock_time.return_value = 1000.0
            cache.put("agent-1", ["read:data:*"], "tok-aging", expires_in=100)

            # 80% elapsed (80 of 100 seconds)
            mock_time.return_value = 1080.0
            assert cache.needs_renewal("agent-1", ["read:data:*"]) is True

    def test_needs_renewal_true_past_threshold(self, cache: TokenCache) -> None:
        """needs_renewal() is True well past the renewal threshold."""
        with patch("agentauth.token.time.time") as mock_time:
            mock_time.return_value = 1000.0
            cache.put("agent-1", ["read:data:*"], "tok-old", expires_in=100)

            # 95% elapsed
            mock_time.return_value = 1095.0
            assert cache.needs_renewal("agent-1", ["read:data:*"]) is True

    def test_needs_renewal_false_for_unknown_key(self, cache: TokenCache) -> None:
        """needs_renewal() returns False when the key does not exist."""
        result = cache.needs_renewal("ghost-agent", ["read:data:*"])
        assert result is False

    def test_custom_renewal_threshold(self) -> None:
        """A custom renewal_threshold=0.5 triggers renewal at 50% elapsed."""
        cache = TokenCache(renewal_threshold=0.5)
        with patch("agentauth.token.time.time") as mock_time:
            mock_time.return_value = 1000.0
            cache.put("agent-1", ["read:data:*"], "tok-half", expires_in=100)

            # 60% elapsed -- past 50% threshold
            mock_time.return_value = 1060.0
            assert cache.needs_renewal("agent-1", ["read:data:*"]) is True

            # Reset and check 40% elapsed -- before 50% threshold
            mock_time.return_value = 1000.0
            cache_b = TokenCache(renewal_threshold=0.5)
            cache_b.put("agent-1", ["read:data:*"], "tok-half", expires_in=100)
            mock_time.return_value = 1040.0
            assert cache_b.needs_renewal("agent-1", ["read:data:*"]) is False


# ---------------------------------------------------------------------------
# remove
# ---------------------------------------------------------------------------


class TestRemove:
    def test_remove_clears_entry(self, cache: TokenCache) -> None:
        """remove() makes get() return None afterwards."""
        cache.put("agent-1", ["read:data:*"], "tok-del", expires_in=300)
        assert cache.get("agent-1", ["read:data:*"]) == "tok-del"

        cache.remove("agent-1", ["read:data:*"])
        assert cache.get("agent-1", ["read:data:*"]) is None

    def test_remove_nonexistent_key_is_safe(self, cache: TokenCache) -> None:
        """remove() on a key that doesn't exist does not raise."""
        cache.remove("ghost-agent", ["read:data:*"])  # must not raise

    def test_remove_scope_order_invariant(self, cache: TokenCache) -> None:
        """remove() with different scope order removes the same entry."""
        cache.put("agent-1", ["write:data:*", "read:data:*"], "tok-x", expires_in=300)
        cache.remove("agent-1", ["read:data:*", "write:data:*"])
        assert cache.get("agent-1", ["write:data:*", "read:data:*"]) is None

    def test_remove_does_not_affect_other_entries(self, cache: TokenCache) -> None:
        """remove() only removes the targeted entry."""
        cache.put("agent-1", ["read:data:*"], "tok-read", expires_in=300)
        cache.put("agent-1", ["write:data:*"], "tok-write", expires_in=300)

        cache.remove("agent-1", ["read:data:*"])
        assert cache.get("agent-1", ["read:data:*"]) is None
        assert cache.get("agent-1", ["write:data:*"]) == "tok-write"


# ---------------------------------------------------------------------------
# Thread safety -- structural check
# ---------------------------------------------------------------------------


class TestThreadSafety:
    def test_lock_attribute_exists(self, cache: TokenCache) -> None:
        """TokenCache must have a threading.Lock (or RLock) attribute."""
        # Inspect instance for a lock -- it may be stored under any private name
        lock_found = False
        for attr_name in vars(cache):
            attr = getattr(cache, attr_name)
            if isinstance(attr, (type(threading.Lock()), type(threading.RLock()))):
                lock_found = True
                break
        assert lock_found, (
            "TokenCache must hold a threading.Lock or threading.RLock instance. "
            "None found on the cache object."
        )
