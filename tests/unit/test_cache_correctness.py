"""Cache correctness regression tests for v0.3.0 Phase 2.

Covers findings G13 (task_id/orch_id keying), G14 (eviction on release),
G15 (concurrent registration serialization).
"""

from __future__ import annotations

from agentauth.token import TokenCache


def test_distinct_task_id_yields_distinct_entries() -> None:
    """G13: cache key includes task_id -- no aliasing across tasks."""
    cache = TokenCache()
    cache.put("analyst", ["read:data:*"], "token-q4", expires_in=300, task_id="q4-2026")
    cache.put("analyst", ["read:data:*"], "token-q1", expires_in=300, task_id="q1-2026")

    assert cache.get("analyst", ["read:data:*"], task_id="q4-2026") == "token-q4"
    assert cache.get("analyst", ["read:data:*"], task_id="q1-2026") == "token-q1"


def test_distinct_orch_id_yields_distinct_entries() -> None:
    """G13: cache key includes orch_id -- no aliasing across orchestrators."""
    cache = TokenCache()
    cache.put("worker", ["read:*"], "token-a", expires_in=300, orch_id="pipeline-A")
    cache.put("worker", ["read:*"], "token-b", expires_in=300, orch_id="pipeline-B")

    assert cache.get("worker", ["read:*"], orch_id="pipeline-A") == "token-a"
    assert cache.get("worker", ["read:*"], orch_id="pipeline-B") == "token-b"


def test_missing_task_id_does_not_alias_to_present_task_id() -> None:
    """G13: task_id=None is a distinct key from task_id='X'."""
    cache = TokenCache()
    cache.put("agent", ["read:*"], "token-tagged", expires_in=300, task_id="X")
    assert cache.get("agent", ["read:*"]) is None  # task_id=None -- no match
    assert cache.get("agent", ["read:*"], task_id="X") == "token-tagged"


def test_remove_by_token_evicts_matching_entry() -> None:
    """G14: cache.remove_by_token evicts whichever entry holds this JWT."""
    cache = TokenCache()
    cache.put("agent", ["read:*"], "jwt-abc", expires_in=300, task_id="t1")
    cache.put("agent", ["read:*"], "jwt-xyz", expires_in=300, task_id="t2")

    cache.remove_by_token("jwt-abc")

    assert cache.get("agent", ["read:*"], task_id="t1") is None
    assert cache.get("agent", ["read:*"], task_id="t2") == "jwt-xyz"


def test_remove_by_token_no_match_is_noop() -> None:
    """G14: remove_by_token is idempotent when the JWT is not cached."""
    cache = TokenCache()
    cache.put("agent", ["read:*"], "jwt-abc", expires_in=300)

    cache.remove_by_token("jwt-nonexistent")  # must not raise

    assert cache.get("agent", ["read:*"]) == "jwt-abc"


def test_concurrent_get_token_produces_one_registration() -> None:
    """G15: per-key lock + double-checked read serializes the cache-miss path.

    Under 10 concurrent threads, only ONE performs the simulated registration;
    the other 9 see the populated cache on the double-checked read.
    """
    import threading

    cache = TokenCache()
    registration_count = 0
    registration_lock = threading.Lock()
    barrier = threading.Barrier(10)  # ensure all threads race together

    def race_get_token() -> None:
        nonlocal registration_count
        barrier.wait()
        # 1. Fast-path cache check (lock-free)
        if cache.get("shared", ["read:*"], task_id="T") is not None:
            return
        # 2. Acquire per-key lock to serialize the miss path
        with cache.acquire_key_lock("shared", ["read:*"], task_id="T"):
            # 3. Double-checked read -- another thread may have populated it
            if cache.get("shared", ["read:*"], task_id="T") is not None:
                return
            # 4. Simulate registration work + cache population
            with registration_lock:
                registration_count += 1
            cache.put(
                "shared", ["read:*"], "jwt-from-broker",
                expires_in=300, task_id="T",
            )

    threads = [threading.Thread(target=race_get_token) for _ in range(10)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert registration_count == 1
    assert cache.get("shared", ["read:*"], task_id="T") == "jwt-from-broker"


def test_acquire_key_lock_returns_same_lock_for_same_key() -> None:
    """G15: acquire_key_lock is idempotent -- same key -> same lock object."""
    cache = TokenCache()
    lock_a = cache.acquire_key_lock("agent", ["read:*"], task_id="T")
    lock_b = cache.acquire_key_lock("agent", ["read:*"], task_id="T")
    assert lock_a is lock_b


def test_acquire_key_lock_distinguishes_keys() -> None:
    """G15: distinct keys yield distinct lock objects (parallel miss paths unblocked)."""
    cache = TokenCache()
    lock_t1 = cache.acquire_key_lock("agent", ["read:*"], task_id="t1")
    lock_t2 = cache.acquire_key_lock("agent", ["read:*"], task_id="t2")
    assert lock_t1 is not lock_t2
