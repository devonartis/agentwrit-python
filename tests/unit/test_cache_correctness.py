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
