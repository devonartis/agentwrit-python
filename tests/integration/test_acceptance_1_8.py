"""Acceptance tests for AgentAuth SDK v0.3.0 — Stories 1-9.

These tests verify the SDK against a live broker. Each story exercises
one distinct SDK behavior with no overlap.

All tests use the session-scoped `client` fixture (one authenticated
AgentAuthApp) to avoid rate limiting.

Usage:
    export AGENTAUTH_BROKER_URL=http://127.0.0.1:8080
    export AGENTAUTH_CLIENT_ID=<id>
    export AGENTAUTH_CLIENT_SECRET=<secret>
    uv run pytest tests/integration/test_acceptance_1_8.py -v -s -m integration
"""
from __future__ import annotations

import os
import time
from collections.abc import Generator
from pathlib import Path

import httpx
import pytest

from agentauth import AgentAuthApp, scope_is_subset, validate
from agentauth.errors import AgentAuthError, AuthorizationError

pytestmark = pytest.mark.integration

EVIDENCE_DIR = Path(__file__).parent.parent / "sdk-core" / "evidence"


@pytest.fixture(scope="session", autouse=True)
def check_broker_running() -> None:
    """Verify broker is running before any test executes."""
    broker_url = os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")
    try:
        resp = httpx.get(f"{broker_url}/v1/health", timeout=5)
        if resp.status_code != 200:
            pytest.skip(f"Broker health check failed: {resp.status_code}")
    except httpx.ConnectError:
        pytest.skip(f"Cannot connect to broker at {broker_url}")


@pytest.fixture(autouse=True)
def delay_between_tests() -> Generator[None, None, None]:
    """Avoid broker rate limits (10 req/min per client_id)."""
    yield
    time.sleep(2)


def save_evidence(name: str, banner: list[str], output: list[str]) -> None:
    """Save banner + test output for audit trail."""
    EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    full = "\n".join(banner) + "\n" + "\n".join(output)
    (EVIDENCE_DIR / f"{name}.txt").write_text(full)


def print_banner(lines: list[str]) -> None:
    """Print the banner block immediately, then pause before test runs."""
    print("\n".join(lines), flush=True)
    time.sleep(4)


# ─────────────────────────────────────────────────────────────
# STORY 1: Create Agent
# ─────────────────────────────────────────────────────────────


class TestStory1:
    """STORY 1: App creates an agent with specific scope."""

    def test_create_agent(self, client: AgentAuthApp) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 1 — CREATE AGENT",
            "-" * 65,
            "WHO:      App creating an agent for a specific task",
            "WHAT:     App calls create_agent() with a scope",
            "WHY:      Every agent must have a verifiable identity and scope",
            "EXPECTED: Agent has a SPIFFE ID containing the orch_id,",
            "          and scope matches exactly what was requested",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        requested = ["read:data:customer-artis"]
        agent = client.create_agent(
            orch_id="data-service",
            task_id="lookup-artis",
            requested_scope=requested,
        )
        output.append(f"  agent_id:   {agent.agent_id}")
        output.append(f"  scope:      {agent.scope}")
        output.append(f"  token:      {agent.access_token[:30]}...")
        output.append(f"  expires_in: {agent.expires_in}s")
        output.append(f"  orch_id:    {agent.orch_id}")
        output.append(f"  task_id:    {agent.task_id}")
        output.append("")

        if "data-service" in agent.agent_id:
            output.append("  PASS: SPIFFE ID contains orch_id 'data-service'")
        else:
            output.append(f"  FAIL: orch_id not in agent_id: {agent.agent_id}")
            passed = False

        if agent.scope == requested:
            output.append(f"  PASS: Scope matches requested {requested}")
        else:
            output.append(f"  FAIL: Scope {agent.scope} != requested {requested}")
            passed = False

        agent.release()

        output.append("")
        output.append("═══ STORY 1: PASS ═══" if passed else "═══ STORY 1: FAIL ═══")
        print("\n".join(output))
        save_evidence("story1_create_agent", banner, output)
        assert passed, "Story 1 failed"


# ─────────────────────────────────────────────────────────────
# STORY 2: Renew Token
# ─────────────────────────────────────────────────────────────


class TestStory2:
    """STORY 2: Agent renews its token mid-task."""

    def test_renew_token(
        self, client: AgentAuthApp, broker_url: str
    ) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 2 — RENEW TOKEN",
            "-" * 65,
            "WHO:      Agent in the middle of a long-running task",
            "WHAT:     Agent calls renew() to get a fresh token",
            "WHY:      Tokens expire — renewal keeps the agent alive",
            "EXPECTED: New token issued, old token revoked,",
            "          agent identity (SPIFFE ID) unchanged",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        agent = client.create_agent(
            orch_id="export-service",
            task_id="export-job-001",
            requested_scope=["read:data:export-batch-001"],
        )
        old_token = agent.access_token
        old_id = agent.agent_id
        output.append(f"  agent_id:      {old_id}")
        output.append(f"  old token:     {old_token[:30]}...")
        output.append(f"  old expires_in: {agent.expires_in}s")
        output.append("")

        agent.renew()
        output.append(f"  new token:      {agent.access_token[:30]}...")
        output.append(f"  new expires_in: {agent.expires_in}s")
        output.append("")

        if agent.access_token != old_token:
            output.append("  PASS: Token changed after renew()")
        else:
            output.append("  FAIL: Token is the same after renew()")
            passed = False

        if agent.agent_id == old_id:
            output.append("  PASS: SPIFFE ID unchanged after renew()")
        else:
            output.append(f"  FAIL: SPIFFE ID changed: {old_id} -> {agent.agent_id}")
            passed = False

        old_result = validate(broker_url, old_token)
        output.append(f"  validate(old_token): valid={old_result.valid}, error={old_result.error}")
        if not old_result.valid:
            output.append("  PASS: Old token revoked by broker")
        else:
            output.append("  FAIL: Old token still valid after renew()")
            passed = False

        agent.release()

        output.append("")
        output.append("═══ STORY 2: PASS ═══" if passed else "═══ STORY 2: FAIL ═══")
        print("\n".join(output))
        save_evidence("story2_renew_token", banner, output)
        assert passed, "Story 2 failed"


# ─────────────────────────────────────────────────────────────
# STORY 3: Release Token
# ─────────────────────────────────────────────────────────────


class TestStory3:
    """STORY 3: Agent releases its token after task completes."""

    def test_release_token(
        self, client: AgentAuthApp, broker_url: str
    ) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 3 — RELEASE TOKEN",
            "-" * 65,
            "WHO:      Agent that has finished its task",
            "WHAT:     Agent calls release() to revoke its own token",
            "WHY:      Dead tokens cannot be misused if leaked",
            "EXPECTED: Token revoked at broker, second release() is safe",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        agent = client.create_agent(
            orch_id="cleanup-service",
            task_id="cleanup-job-001",
            requested_scope=["write:data:cleanup-result-001"],
        )
        token_snapshot = agent.access_token
        output.append(f"  agent_id:   {agent.agent_id}")
        output.append(f"  token:      {token_snapshot[:30]}...")
        output.append(f"  expires_in: {agent.expires_in}s")
        output.append("")

        agent.release()
        output.append("  release() called")

        result = validate(broker_url, token_snapshot)
        output.append(f"  validate(released_token): valid={result.valid}, error={result.error}")
        if not result.valid:
            output.append("  PASS: Broker confirms token revoked")
        else:
            output.append("  FAIL: Token still valid after release()")
            passed = False

        try:
            agent.release()
            output.append("  PASS: Second release() did not raise")
        except Exception as e:
            output.append(f"  FAIL: Second release() raised: {e}")
            passed = False

        output.append("")
        output.append("═══ STORY 3: PASS ═══" if passed else "═══ STORY 3: FAIL ═══")
        print("\n".join(output))
        save_evidence("story3_release_token", banner, output)
        assert passed, "Story 3 failed"


# ─────────────────────────────────────────────────────────────
# STORY 4: Validate Live Token
# ─────────────────────────────────────────────────────────────


class TestStory4:
    """STORY 4: App validates a live agent token."""

    def test_validate_live_token(
        self, client: AgentAuthApp, broker_url: str
    ) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 4 — VALIDATE LIVE TOKEN",
            "-" * 65,
            "WHO:      App checking if an agent's token is still good",
            "WHAT:     App calls validate() with the agent's token",
            "WHY:      Zero-trust — never assume a token is valid",
            "EXPECTED: Broker returns valid=true with claims that",
            "          match the agent's scope, identity, and task",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        requested = ["read:data:report-q3", "write:data:summary-q3"]
        agent = client.create_agent(
            orch_id="reporting-service",
            task_id="quarterly-report",
            requested_scope=requested,
        )
        output.append(f"  agent_id: {agent.agent_id}")
        output.append(f"  scope:    {agent.scope}")
        output.append("")

        result = validate(broker_url, agent.access_token)
        output.append(f"  validate() returned: valid={result.valid}")

        if not result.valid or not result.claims:
            output.append(f"  error: {result.error}")
            output.append("  FAIL: Broker says token is invalid")
            passed = False
        else:
            output.append(f"    iss:     {result.claims.iss}")
            output.append(f"    sub:     {result.claims.sub}")
            output.append(f"    scope:   {result.claims.scope}")
            output.append(f"    orch_id: {result.claims.orch_id}")
            output.append(f"    task_id: {result.claims.task_id}")
            output.append(f"    jti:     {result.claims.jti}")
            output.append(f"    exp:     {result.claims.exp}")
            output.append(f"    iat:     {result.claims.iat}")
            output.append("")

            if result.claims.scope == requested:
                output.append(f"  PASS: Claims scope matches requested {requested}")
            else:
                output.append(f"  FAIL: Claims scope {result.claims.scope} != {requested}")
                passed = False

            if result.claims.sub == agent.agent_id:
                output.append("  PASS: Claims sub matches agent_id")
            else:
                output.append(f"  FAIL: sub={result.claims.sub} != agent_id={agent.agent_id}")
                passed = False

            if result.claims.orch_id == "reporting-service":
                output.append("  PASS: Claims orch_id matches")
            else:
                output.append(f"  FAIL: orch_id={result.claims.orch_id}")
                passed = False

            if result.claims.task_id == "quarterly-report":
                output.append("  PASS: Claims task_id matches")
            else:
                output.append(f"  FAIL: task_id={result.claims.task_id}")
                passed = False

        agent.release()

        output.append("")
        output.append("═══ STORY 4: PASS ═══" if passed else "═══ STORY 4: FAIL ═══")
        print("\n".join(output))
        save_evidence("story4_validate_token", banner, output)
        assert passed, "Story 4 failed"


# ─────────────────────────────────────────────────────────────
# STORY 5: Delegate Narrow Scope
# ─────────────────────────────────────────────────────────────


class TestStory5:
    """STORY 5: Agent delegates narrow scope to another agent."""

    def test_delegate_narrow_scope(
        self, client: AgentAuthApp, broker_url: str
    ) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 5 — DELEGATE NARROW SCOPE",
            "-" * 65,
            "WHO:      Agent A delegating one of its scopes to Agent B",
            "WHAT:     A has two scopes, delegates only one to B",
            "WHY:      Delegation must narrow authority, never expand it",
            "EXPECTED: Delegated token has ONLY the narrow scope,",
            "          not A's full scope. Broker validates this.",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        agent_a = client.create_agent(
            orch_id="pipeline",
            task_id="orchestrator-001",
            requested_scope=["read:data:partition-7", "read:data:partition-8"],
        )
        agent_b = client.create_agent(
            orch_id="pipeline",
            task_id="worker-partition-7",
            requested_scope=["read:data:partition-7"],
        )
        output.append(f"  Agent A: {agent_a.agent_id}")
        output.append(f"  Agent A scope: {agent_a.scope}")
        output.append(f"  Agent B: {agent_b.agent_id}")
        output.append(f"  Agent B scope: {agent_b.scope}")
        output.append("")

        output.append("  A delegates [read:data:partition-7] to B...")
        delegated = agent_a.delegate(
            delegate_to=agent_b.agent_id,
            scope=["read:data:partition-7"],
        )
        output.append("  delegate() returned:")
        output.append(f"    access_token: {delegated.access_token[:30]}...")
        output.append(f"    expires_in:   {delegated.expires_in}s")
        output.append(f"    chain_length: {len(delegated.delegation_chain)}")
        for i, rec in enumerate(delegated.delegation_chain):
            output.append(f"    chain[{i}]: agent={rec.agent[-25:]} scope={rec.scope} at={rec.delegated_at}")
        output.append("")

        output.append("  Validating delegated token with broker...")
        result = validate(broker_url, delegated.access_token)
        output.append(f"  validate() returned: valid={result.valid}")
        if not result.valid or not result.claims:
            output.append(f"  error: {result.error}")
            output.append("  FAIL: Delegated token is invalid at broker")
            passed = False
        else:
            output.append(f"    sub:     {result.claims.sub}")
            output.append(f"    scope:   {result.claims.scope}")
            output.append(f"    orch_id: {result.claims.orch_id}")
            output.append(f"    task_id: {result.claims.task_id}")
            output.append("")

            if scope_is_subset(["read:data:partition-7"], result.claims.scope):
                output.append("  PASS: Delegated token covers partition-7")
            else:
                output.append("  FAIL: Delegated token missing partition-7")
                passed = False

            if not scope_is_subset(["read:data:partition-8"], result.claims.scope):
                output.append("  PASS: Delegated token does NOT cover partition-8")
            else:
                output.append("  FAIL: Delegated token leaked partition-8")
                passed = False

        agent_a.release()
        agent_b.release()

        output.append("")
        output.append("═══ STORY 5: PASS ═══" if passed else "═══ STORY 5: FAIL ═══")
        print("\n".join(output))
        save_evidence("story5_delegate_narrow", banner, output)
        assert passed, "Story 5 failed"


# ─────────────────────────────────────────────────────────────
# STORY 6: Delegate Scope Agent Doesn't Have
# ─────────────────────────────────────────────────────────────


class TestStory6:
    """STORY 6: Agent tries to delegate scope it doesn't have."""

    def test_delegate_scope_not_held(self, client: AgentAuthApp) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 6 — DELEGATE SCOPE NOT HELD",
            "-" * 65,
            "WHO:      Agent trying to delegate scope it doesn't have",
            "WHAT:     Agent A has partition-7, tries to delegate partition-8",
            "WHY:      Agents cannot grant authority they don't possess",
            "EXPECTED: Broker rejects with 403, SDK raises AuthorizationError",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        agent_a = client.create_agent(
            orch_id="pipeline",
            task_id="worker-only-p7",
            requested_scope=["read:data:partition-7"],
        )
        agent_b = client.create_agent(
            orch_id="pipeline",
            task_id="target-agent",
            requested_scope=["read:data:partition-7"],
        )
        output.append(f"  Agent A: {agent_a.agent_id}")
        output.append(f"  Agent A scope: {agent_a.scope}")
        output.append(f"  Agent B: {agent_b.agent_id}")
        output.append(f"  Agent B scope: {agent_b.scope}")
        output.append("")

        output.append("  A tries to delegate [read:data:partition-8] to B...")
        try:
            agent_a.delegate(
                delegate_to=agent_b.agent_id,
                scope=["read:data:partition-8"],
            )
            output.append("  FAIL: Delegation accepted — should have been rejected")
            passed = False
        except AuthorizationError as e:
            output.append(f"  Caught: {type(e).__name__}")
            output.append(f"  Status: {e.status_code}")
            output.append(f"  Error:  {e.problem.error_code}")
            output.append(f"  Detail: {e.problem.detail}")
            output.append("")

            if e.status_code == 403:
                output.append("  PASS: Broker rejected with 403")
            else:
                output.append(f"  FAIL: Expected 403, got {e.status_code}")
                passed = False

        agent_a.release()
        agent_b.release()

        output.append("")
        output.append("═══ STORY 6: PASS ═══" if passed else "═══ STORY 6: FAIL ═══")
        print("\n".join(output))
        save_evidence("story6_delegate_rejected", banner, output)
        assert passed, "Story 6 failed"


# ─────────────────────────────────────────────────────────────
# STORY 7: Delegation Chain A → B → C
# ─────────────────────────────────────────────────────────────


class TestStory7:
    """STORY 7: Delegation chain A → B → C with narrowing at each hop.

    A is the manager with 3 scopes. A delegates 2 to B (the analyst).
    B re-delegates 1 to C (the reader) using the delegated token via
    raw HTTP, so the broker builds a real chain. Each hop narrows.
    """

    def test_delegation_chain(
        self, client: AgentAuthApp, broker_url: str
    ) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 7 — DELEGATION CHAIN A → B → C",
            "-" * 65,
            "WHO:      Manager (A), Analyst (B), Reader (C)",
            "WHAT:     A delegates 2 of 3 scopes to B, B delegates 1 to C",
            "WHY:      Each hop narrows authority — auditors trace the chain",
            "EXPECTED: C's token has only 1 scope, chain records both hops",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        # A: manager with broad access
        agent_a = client.create_agent(
            orch_id="data-pipeline",
            task_id="manager",
            requested_scope=[
                "read:data:partition-7",
                "read:data:partition-8",
                "write:data:pipeline-results",
            ],
        )
        # B: analyst — will receive 2 read scopes from A
        agent_b = client.create_agent(
            orch_id="data-pipeline",
            task_id="analyst",
            requested_scope=["read:data:partition-7", "read:data:partition-8"],
        )
        # C: reader — will receive 1 read scope from B
        agent_c = client.create_agent(
            orch_id="data-pipeline",
            task_id="reader",
            requested_scope=["read:data:partition-7"],
        )
        output.append(f"  Agent A (manager):  {agent_a.agent_id}")
        output.append(f"  Agent A scope:      {agent_a.scope}")
        output.append(f"  Agent B (analyst):  {agent_b.agent_id}")
        output.append(f"  Agent B scope:      {agent_b.scope}")
        output.append(f"  Agent C (reader):   {agent_c.agent_id}")
        output.append(f"  Agent C scope:      {agent_c.scope}")
        output.append("")

        # Hop 1: A delegates 2 read scopes to B (drops write)
        output.append("  Hop 1: A delegates [partition-7, partition-8] to B (drops write)...")
        delegated_ab = agent_a.delegate(
            delegate_to=agent_b.agent_id,
            scope=["read:data:partition-7", "read:data:partition-8"],
        )
        output.append("  delegate() A→B returned:")
        output.append(f"    access_token: {delegated_ab.access_token[:30]}...")
        output.append(f"    expires_in:   {delegated_ab.expires_in}s")
        output.append(f"    chain_length: {len(delegated_ab.delegation_chain)}")
        for i, rec in enumerate(delegated_ab.delegation_chain):
            output.append(f"    chain[{i}]: agent={rec.agent} scope={rec.scope} at={rec.delegated_at}")
        output.append("")

        # Hop 2: B re-delegates using the delegated token (raw HTTP)
        # This is the only way to build a real chain — the SDK's
        # agent_b.delegate() uses B's registration token, not the
        # delegated token from A. We call the broker directly.
        output.append("  Hop 2: B delegates [partition-7] to C using delegated token (raw HTTP)...")
        hop2_resp = httpx.post(
            f"{broker_url}/v1/delegate",
            json={
                "delegate_to": agent_c.agent_id,
                "scope": ["read:data:partition-7"],
            },
            headers={"Authorization": f"Bearer {delegated_ab.access_token}"},
            timeout=10,
        )
        output.append(f"  HTTP status: {hop2_resp.status_code}")

        if hop2_resp.status_code != 200:
            output.append(f"  FAIL: Hop 2 rejected: {hop2_resp.text}")
            passed = False
            delegated_bc_token = None
            delegated_bc_chain = []
        else:
            hop2_data = hop2_resp.json()
            delegated_bc_token = hop2_data["access_token"]
            delegated_bc_chain = hop2_data.get("delegation_chain", [])
            output.append("  Hop 2 returned:")
            output.append(f"    access_token: {delegated_bc_token[:30]}...")
            output.append(f"    expires_in:   {hop2_data['expires_in']}s")
            output.append(f"    chain_length: {len(delegated_bc_chain)}")
            for i, rec in enumerate(delegated_bc_chain):
                output.append(f"    chain[{i}]: agent={rec['agent']} scope={rec['scope']} at={rec['delegated_at']}")
        output.append("")

        # Validate C's final token
        if delegated_bc_token:
            output.append("  Validating C's final delegated token...")
            result = validate(broker_url, delegated_bc_token)
            output.append(f"  validate() returned: valid={result.valid}")

            if not result.valid or not result.claims:
                output.append(f"  error: {result.error}")
                output.append("  FAIL: C's token is invalid")
                passed = False
            else:
                output.append(f"    sub:     {result.claims.sub}")
                output.append(f"    scope:   {result.claims.scope}")
                output.append(f"    orch_id: {result.claims.orch_id}")
                output.append(f"    task_id: {result.claims.task_id}")
                output.append("")

                # Check 1: C only has partition-7
                if result.claims.scope == ["read:data:partition-7"]:
                    output.append("  PASS: C has only partition-7 (narrowed twice)")
                else:
                    output.append(f"  FAIL: C scope is {result.claims.scope}, expected ['read:data:partition-7']")
                    passed = False

                # Check 2: C does NOT have partition-8
                if not scope_is_subset(["read:data:partition-8"], result.claims.scope):
                    output.append("  PASS: C does NOT have partition-8")
                else:
                    output.append("  FAIL: C leaked partition-8")
                    passed = False

                # Check 3: C does NOT have write
                if not scope_is_subset(["write:data:pipeline-results"], result.claims.scope):
                    output.append("  PASS: C does NOT have write access")
                else:
                    output.append("  FAIL: C leaked write access")
                    passed = False

            # Check 4: Chain has 2 entries (A→B, B→C)
            if len(delegated_bc_chain) >= 2:
                output.append(f"  PASS: Chain has {len(delegated_bc_chain)} entries (both hops recorded)")
            else:
                output.append(f"  FAIL: Chain has {len(delegated_bc_chain)} entries, expected 2")
                passed = False

        agent_a.release()
        agent_b.release()
        agent_c.release()

        output.append("")
        output.append("═══ STORY 7: PASS ═══" if passed else "═══ STORY 7: FAIL ═══")
        print("\n".join(output))
        save_evidence("story7_delegation_chain", banner, output)
        assert passed, "Story 7 failed"


# ─────────────────────────────────────────────────────────────
# STORY 8: Delegate All Scope (No Narrowing)
# ─────────────────────────────────────────────────────────────


class TestStory8:
    """STORY 8: Agent delegates ALL its scope without narrowing.

    A has 3 scopes. B has 1 scope. A delegates all 3 scopes to B.
    This is NOT narrowing — A is handing over everything it has.
    Does the broker accept or reject this?
    """

    def test_delegate_all_scope(
        self, client: AgentAuthApp, broker_url: str
    ) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 8 — DELEGATE ALL SCOPE (NO NARROWING)",
            "-" * 65,
            "WHO:      Agent A with 3 scopes, Agent B with 1 scope",
            "WHAT:     A delegates ALL 3 of its scopes to B — no narrowing",
            "WHY:      Delegation is supposed to narrow authority. Does the",
            "          broker require strict narrowing, or accept equal scope?",
            "EXPECTED: This test discovers and documents the broker's behavior",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        a_scope = [
            "read:data:partition-7",
            "read:data:partition-8",
            "write:data:pipeline-results",
        ]

        agent_a = client.create_agent(
            orch_id="no-narrow-test",
            task_id="delegator",
            requested_scope=a_scope,
        )
        agent_b = client.create_agent(
            orch_id="no-narrow-test",
            task_id="receiver",
            requested_scope=["read:data:partition-7"],
        )
        output.append(f"  Agent A: {agent_a.agent_id}")
        output.append(f"  Agent A scope: {agent_a.scope}")
        output.append(f"  Agent B: {agent_b.agent_id}")
        output.append(f"  Agent B scope: {agent_b.scope}")
        output.append("")

        output.append(f"  A delegates ALL 3 scopes to B: {a_scope}")
        broker_accepts = False
        try:
            delegated = agent_a.delegate(
                delegate_to=agent_b.agent_id,
                scope=a_scope,
            )
            broker_accepts = True
            output.append("  RESULT: Broker ACCEPTED full-scope delegation")
            output.append("  delegate() returned:")
            output.append(f"    access_token: {delegated.access_token[:30]}...")
            output.append(f"    expires_in:   {delegated.expires_in}s")
            output.append(f"    chain_length: {len(delegated.delegation_chain)}")
            for i, rec in enumerate(delegated.delegation_chain):
                output.append(f"    chain[{i}]: agent={rec.agent} scope={rec.scope} at={rec.delegated_at}")
            output.append("")

            output.append("  Validating delegated token with broker...")
            result = validate(broker_url, delegated.access_token)
            output.append(f"  validate() returned: valid={result.valid}")
            if result.valid and result.claims:
                output.append(f"    sub:   {result.claims.sub}")
                output.append(f"    scope: {result.claims.scope}")
                output.append("")

                # Did B get all 3 scopes?
                got_all = result.claims.scope == a_scope
                if got_all:
                    output.append("  PASS: B received all 3 scopes (no narrowing accepted)")
                else:
                    output.append(f"  INFO: B received {result.claims.scope}")
                    output.append(f"  INFO: A had {a_scope}")
            else:
                output.append(f"  error: {result.error}")
                output.append("  FAIL: Delegated token invalid at broker")
                passed = False

        except AuthorizationError as e:
            output.append("  RESULT: Broker REJECTED full-scope delegation")
            output.append(f"  Status: {e.status_code}")
            output.append(f"  Error:  {e.problem.error_code}")
            output.append(f"  Detail: {e.problem.detail}")
            output.append("")
            output.append("  PASS: Broker requires strict narrowing (documented)")

        output.append("")
        output.append(f"  DOCUMENTED: broker_accepts_full_delegation = {broker_accepts}")

        agent_a.release()
        agent_b.release()

        output.append("")
        output.append("═══ STORY 8: PASS ═══" if passed else "═══ STORY 8: FAIL ═══")
        print("\n".join(output))
        save_evidence("story8_delegate_all_scope", banner, output)
        assert passed, "Story 8 failed"


# ─────────────────────────────────────────────────────────────
# STORY 9: Agent Attempts Action Outside Its Scope
# ─────────────────────────────────────────────────────────────


class TestStory9:
    """STORY 9: Agent attempts action outside its granted scope."""

    def test_scope_gating(self, client: AgentAuthApp) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 9 — AGENT BLOCKED BY SCOPE CHECK",
            "-" * 65,
            "WHO:      Agent with access to one customer's data",
            "WHAT:     Agent tries to read ALL customers — app blocks it",
            "WHY:      The app is the gatekeeper. scope_is_subset() is the lock.",
            "EXPECTED: Authorized action passes scope check,",
            "          unauthorized action is blocked before it happens",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        agent = client.create_agent(
            orch_id="customer-service",
            task_id="lookup-artis",
            requested_scope=["read:data:customer-artis"],
        )
        output.append(f"  Agent scope: {agent.scope}")
        output.append("")

        # Action 1: Read customer-artis (authorized)
        action_1 = ["read:data:customer-artis"]
        allowed_1 = scope_is_subset(action_1, agent.scope)
        output.append("  Action: read customer-artis")
        output.append(f"  Scope check: {allowed_1}")
        if allowed_1:
            output.append("  PASS: Authorized action allowed")
        else:
            output.append("  FAIL: Authorized action blocked")
            passed = False

        output.append("")

        # Action 2: Read ALL customers (NOT authorized)
        action_2 = ["read:data:all-customers"]
        allowed_2 = scope_is_subset(action_2, agent.scope)
        output.append("  Action: read all-customers")
        output.append(f"  Scope check: {allowed_2}")
        if not allowed_2:
            output.append("  PASS: Unauthorized action blocked by scope check")
        else:
            output.append("  FAIL: Unauthorized action was allowed")
            passed = False

        output.append("")

        # Action 3: Write to customer-artis (NOT authorized — agent has read only)
        action_3 = ["write:data:customer-artis"]
        allowed_3 = scope_is_subset(action_3, agent.scope)
        output.append("  Action: write customer-artis")
        output.append(f"  Scope check: {allowed_3}")
        if not allowed_3:
            output.append("  PASS: Write blocked — agent has read-only scope")
        else:
            output.append("  FAIL: Write was allowed on read-only agent")
            passed = False

        agent.release()

        output.append("")
        output.append("═══ STORY 9: PASS ═══" if passed else "═══ STORY 9: FAIL ═══")
        print("\n".join(output))
        save_evidence("story9_scope_gating", banner, output)
        assert passed, "Story 9 failed"


# ─────────────────────────────────────────────────────────────
# STORY 10: Token Expires Naturally
# ─────────────────────────────────────────────────────────────


class TestStory10:
    """STORY 10: Agent token expires on its own without release().

    The app creates an agent with a very short TTL (5 seconds).
    Instead of calling release(), the test waits for the token to
    expire naturally, then validates it to confirm the broker
    rejects it. This proves the broker enforces TTL without the
    SDK needing to do anything.
    """

    def test_token_natural_expiry(
        self, client: AgentAuthApp, broker_url: str
    ) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 10 — TOKEN EXPIRES NATURALLY",
            "-" * 65,
            "WHO:      Agent with a 5-second TTL",
            "WHAT:     No release() called — token expires on its own",
            "WHY:      Broker must enforce TTL even if the agent disappears",
            "EXPECTED: Token valid immediately, invalid after expiry,",
            "          broker returns 'token is invalid or expired'",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        short_ttl = 5
        agent = client.create_agent(
            orch_id="short-lived-service",
            task_id="quick-task-001",
            requested_scope=["read:data:temp-resource"],
            max_ttl=short_ttl,
        )
        output.append(f"  agent_id:   {agent.agent_id}")
        output.append(f"  scope:      {agent.scope}")
        output.append(f"  token:      {agent.access_token[:30]}...")
        output.append(f"  expires_in: {agent.expires_in}s (requested {short_ttl}s)")
        output.append("")

        # Check 1: Token is valid right now
        result_before = validate(broker_url, agent.access_token)
        output.append(f"  validate() immediately: valid={result_before.valid}")
        if result_before.valid:
            output.append("  PASS: Token is valid right after creation")
        else:
            output.append(f"  FAIL: Token invalid immediately — error={result_before.error}")
            passed = False

        output.append("")

        # Wait for expiry
        wait_time = agent.expires_in + 2
        output.append(f"  Waiting {wait_time}s for token to expire...")
        time.sleep(wait_time)

        # Check 2: Token should be dead now
        result_after = validate(broker_url, agent.access_token)
        output.append(f"  validate() after {wait_time}s: valid={result_after.valid}, error={result_after.error}")
        if not result_after.valid:
            output.append("  PASS: Token expired naturally — broker rejected it")
        else:
            output.append("  FAIL: Token still valid after TTL expired")
            passed = False

        output.append("")
        output.append("═══ STORY 10: PASS ═══" if passed else "═══ STORY 10: FAIL ═══")
        print("\n".join(output))
        save_evidence("story10_natural_expiry", banner, output)
        assert passed, "Story 10 failed"


# ─────────────────────────────────────────────────────────────
# STORY 11: RFC 7807 Error Structure
# ─────────────────────────────────────────────────────────────


class TestStory11:
    """STORY 11: Broker error returns a structured RFC 7807 ProblemDetail.

    When the broker rejects a request, the SDK must surface the full
    error structure — not just a status code. Developers need type,
    title, status, detail, and error_code to debug what went wrong.
    """

    def test_rfc7807_error_structure(self, client: AgentAuthApp) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 11 — RFC 7807 ERROR STRUCTURE",
            "-" * 65,
            "WHO:      App receiving a rejection from the broker",
            "WHAT:     SDK parses the error into a structured ProblemDetail",
            "WHY:      Developers need actionable error info, not raw HTTP",
            "EXPECTED: AuthorizationError contains ProblemDetail with",
            "          type, title, status, detail, and error_code",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        # Trigger a 403 by delegating scope the agent doesn't have
        agent_a = client.create_agent(
            orch_id="error-test",
            task_id="trigger-403",
            requested_scope=["read:data:only-this"],
        )
        agent_b = client.create_agent(
            orch_id="error-test",
            task_id="target",
            requested_scope=["read:data:only-this"],
        )
        output.append(f"  Agent A: {agent_a.agent_id}")
        output.append(f"  Agent A scope: {agent_a.scope}")
        output.append("")

        output.append("  Triggering 403 by delegating scope agent doesn't have...")
        try:
            agent_a.delegate(
                delegate_to=agent_b.agent_id,
                scope=["read:data:something-else"],
            )
            output.append("  FAIL: No error raised — expected AuthorizationError")
            passed = False
        except AuthorizationError as e:
            output.append(f"  Caught: {type(e).__name__}")
            output.append(f"  exception.status_code: {e.status_code}")
            output.append("")
            output.append("  ProblemDetail fields:")
            output.append(f"    type:       {e.problem.type}")
            output.append(f"    title:      {e.problem.title}")
            output.append(f"    status:     {e.problem.status}")
            output.append(f"    detail:     {e.problem.detail}")
            output.append(f"    instance:   {e.problem.instance}")
            output.append(f"    error_code: {e.problem.error_code}")
            output.append(f"    request_id: {e.problem.request_id}")
            output.append(f"    hint:       {e.problem.hint}")
            output.append("")

            # Check 1: status_code is 403
            if e.status_code == 403:
                output.append("  PASS: status_code is 403")
            else:
                output.append(f"  FAIL: status_code is {e.status_code}, expected 403")
                passed = False

            # Check 2: type is present
            if e.problem.type:
                output.append(f"  PASS: type is present: {e.problem.type}")
            else:
                output.append("  FAIL: type is missing")
                passed = False

            # Check 3: title is present
            if e.problem.title:
                output.append(f"  PASS: title is present: {e.problem.title}")
            else:
                output.append("  FAIL: title is missing")
                passed = False

            # Check 4: detail is present
            if e.problem.detail:
                output.append(f"  PASS: detail is present: {e.problem.detail}")
            else:
                output.append("  FAIL: detail is missing")
                passed = False

            # Check 5: error_code is present
            if e.problem.error_code:
                output.append(f"  PASS: error_code is present: {e.problem.error_code}")
            else:
                output.append("  FAIL: error_code is missing")
                passed = False

        except Exception as e:
            output.append(f"  FAIL: Wrong exception type: {type(e).__name__}: {e}")
            passed = False

        agent_a.release()
        agent_b.release()

        output.append("")
        output.append("═══ STORY 11: PASS ═══" if passed else "═══ STORY 11: FAIL ═══")
        print("\n".join(output))
        save_evidence("story11_rfc7807_error", banner, output)
        assert passed, "Story 11 failed"


# ─────────────────────────────────────────────────────────────
# STORY 12: Multiple Agents with Isolated Scopes
# ─────────────────────────────────────────────────────────────


class TestStory12:
    """STORY 12: App creates multiple agents with different scopes.

    The app creates 3 agents for 3 different tasks. Each agent has
    a unique identity and scope. No agent can access another agent's
    data — scope_is_subset proves the isolation.
    """

    def test_multiple_agents_isolated(
        self, client: AgentAuthApp, broker_url: str
    ) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 12 — MULTIPLE AGENTS, ISOLATED SCOPES",
            "-" * 65,
            "WHO:      App creating 3 agents for 3 different tasks",
            "WHAT:     Each agent gets unique identity and task-specific scope",
            "WHY:      Compromised agent A cannot access agent B's data",
            "EXPECTED: 3 unique SPIFFE IDs, 3 non-overlapping scopes,",
            "          scope_is_subset confirms no cross-access",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        tasks = [
            ("read-customers", "read:data:customers-west"),
            ("read-inventory", "read:data:inventory-warehouse-3"),
            ("write-reports", "write:data:quarterly-report-q3"),
        ]

        agents = []
        for task_id, scope in tasks:
            agent = client.create_agent(
                orch_id="multi-agent-service",
                task_id=task_id,
                requested_scope=[scope],
            )
            agents.append(agent)
            output.append(f"  Agent: {agent.agent_id}")
            output.append(f"    task_id: {agent.task_id}")
            output.append(f"    scope:   {agent.scope}")
            output.append(f"    token:   {agent.access_token[:30]}...")
        output.append("")

        # Check 1: All 3 have unique SPIFFE IDs
        ids = [a.agent_id for a in agents]
        if len(set(ids)) == 3:
            output.append("  PASS: All 3 agents have unique SPIFFE IDs")
        else:
            output.append(f"  FAIL: Duplicate IDs found: {ids}")
            passed = False

        # Check 2: No agent can access another's scope
        output.append("")
        output.append("  Cross-access checks:")
        for i, agent_i in enumerate(agents):
            for j, agent_j in enumerate(agents):
                if i == j:
                    continue
                can_access = scope_is_subset(agent_j.scope, agent_i.scope)
                label = f"    agent[{i}] ({agent_i.task_id}) → agent[{j}] ({agent_j.task_id}) scope: {can_access}"
                output.append(label)
                if can_access:
                    output.append(f"    FAIL: agent[{i}] can access agent[{j}]'s scope")
                    passed = False

        if passed:
            output.append("  PASS: No cross-access between agents")

        # Check 3: Each agent's token validates with correct claims
        output.append("")
        output.append("  Validating each agent's token:")
        for i, agent in enumerate(agents):
            result = validate(broker_url, agent.access_token)
            output.append(f"    agent[{i}] ({agent.task_id}): valid={result.valid}")
            if result.valid and result.claims:
                output.append(f"      sub:   {result.claims.sub}")
                output.append(f"      scope: {result.claims.scope}")
                if result.claims.scope != agent.scope:
                    output.append("      FAIL: Claims scope doesn't match agent scope")
                    passed = False
            else:
                output.append(f"      FAIL: Token invalid — error={result.error}")
                passed = False

        for agent in agents:
            agent.release()

        output.append("")
        output.append("═══ STORY 12: PASS ═══" if passed else "═══ STORY 12: FAIL ═══")
        print("\n".join(output))
        save_evidence("story12_multi_agent_isolation", banner, output)
        assert passed, "Story 12 failed"


# ─────────────────────────────────────────────────────────────
# STORY 13: Renew a Released Agent
# ─────────────────────────────────────────────────────────────


class TestStory13:
    """STORY 13: Renew a released agent fails with a clear error.

    Developer bug: agent finished its task and was released, but
    another part of the code tries to renew it. The SDK must catch
    this locally and raise AgentAuthError — not send a dead token
    to the broker.
    """

    def test_renew_released_agent(self, client: AgentAuthApp) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 13 — RENEW A RELEASED AGENT",
            "-" * 65,
            "WHO:      Developer code that tries to renew a dead agent",
            "WHAT:     Agent was released, then renew() is called",
            "WHY:      SDK must fail fast with a clear error, not hit broker",
            "EXPECTED: AgentAuthError raised with message about release",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        agent = client.create_agent(
            orch_id="lifecycle-test",
            task_id="renew-after-release",
            requested_scope=["read:data:test-resource"],
        )
        output.append(f"  agent_id:   {agent.agent_id}")
        output.append(f"  scope:      {agent.scope}")
        output.append(f"  expires_in: {agent.expires_in}s")
        output.append("")

        agent.release()
        output.append("  release() called — agent is now dead")
        output.append("")

        output.append("  Attempting renew() on released agent...")
        try:
            agent.renew()
            output.append("  FAIL: renew() succeeded on released agent")
            passed = False
        except AgentAuthError as e:
            output.append(f"  Caught: {type(e).__name__}")
            output.append(f"  Message: {e}")
            output.append("")
            if "released" in str(e).lower():
                output.append("  PASS: Error message mentions 'released'")
            else:
                output.append(f"  FAIL: Error message unclear: {e}")
                passed = False

        output.append("")

        output.append("  Attempting delegate() on released agent...")
        try:
            agent.delegate(
                delegate_to="spiffe://fake/agent",
                scope=["read:data:test-resource"],
            )
            output.append("  FAIL: delegate() succeeded on released agent")
            passed = False
        except AgentAuthError as e:
            output.append(f"  Caught: {type(e).__name__}")
            output.append(f"  Message: {e}")
            output.append("")
            if "released" in str(e).lower():
                output.append("  PASS: Error message mentions 'released'")
            else:
                output.append(f"  FAIL: Error message unclear: {e}")
                passed = False

        output.append("")
        output.append("═══ STORY 13: PASS ═══" if passed else "═══ STORY 13: FAIL ═══")
        print("\n".join(output))
        save_evidence("story13_renew_released", banner, output)
        assert passed, "Story 13 failed"


# ─────────────────────────────────────────────────────────────
# STORY 14: Validate a Garbage Token
# ─────────────────────────────────────────────────────────────


class TestStory14:
    """STORY 14: Validate a fake/garbage token.

    Someone sends a token that was never issued by the broker.
    The app calls validate() — broker returns valid=false with an
    error message. The SDK must handle this gracefully without
    crashing.
    """

    def test_validate_garbage_token(self, broker_url: str) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 14 — VALIDATE A GARBAGE TOKEN",
            "-" * 65,
            "WHO:      App receiving a fake token from an unknown source",
            "WHAT:     App calls validate() with a token that was never real",
            "WHY:      Apps must handle bad tokens without crashing",
            "EXPECTED: Broker returns valid=false, SDK returns ValidateResult",
            "          with error message, no exception thrown",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        garbage_tokens = [
            ("completely-fake-not-a-jwt", "random string"),
            ("eyJ.fake.token", "fake JWT structure"),
            ("aaa.bbb.ccc.ddd.eee", "too many segments"),
        ]

        for token, description in garbage_tokens:
            output.append(f"  Testing: {description}")
            output.append(f"  Token:   '{token[:40]}{'...' if len(token) > 40 else ''}'")

            try:
                result = validate(broker_url, token)
                output.append(f"  validate() returned: valid={result.valid}, error={result.error}")

                if not result.valid:
                    output.append(f"  PASS: Broker rejected — {result.error}")
                else:
                    output.append("  FAIL: Broker accepted a garbage token")
                    passed = False
            except Exception as e:
                output.append("  FAIL: SDK threw exception instead of returning ValidateResult")
                output.append(f"  Exception: {type(e).__name__}: {e}")
                passed = False

            output.append("")

        output.append("═══ STORY 14: PASS ═══" if passed else "═══ STORY 14: FAIL ═══")
        print("\n".join(output))
        save_evidence("story14_garbage_token", banner, output)
        assert passed, "Story 14 failed"


# ─────────────────────────────────────────────────────────────
# STORY 15: Health Check
# ─────────────────────────────────────────────────────────────


class TestStory15:
    """STORY 15: App checks broker health before doing work.

    Before creating any agents, the app calls health() to verify
    the broker is operational. The response includes status, version,
    uptime, and database connectivity.
    """

    def test_health_check(self, client: AgentAuthApp) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY 15 — HEALTH CHECK",
            "-" * 65,
            "WHO:      App checking if the broker is ready",
            "WHAT:     App calls health() before creating any agents",
            "WHY:      Don't attempt work if the broker is down",
            "EXPECTED: HealthStatus with status='ok', version, uptime,",
            "          and db_connected=true",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        health = client.health()
        output.append("  health() returned:")
        output.append(f"    status:              {health.status}")
        output.append(f"    version:             {health.version}")
        output.append(f"    uptime:              {health.uptime}s")
        output.append(f"    db_connected:        {health.db_connected}")
        output.append(f"    audit_events_count:  {health.audit_events_count}")
        output.append("")

        if health.status == "ok":
            output.append("  PASS: Broker status is 'ok'")
        else:
            output.append(f"  FAIL: Broker status is '{health.status}', expected 'ok'")
            passed = False

        if health.version:
            output.append(f"  PASS: Version reported: {health.version}")
        else:
            output.append("  FAIL: No version in health response")
            passed = False

        if health.uptime > 0:
            output.append(f"  PASS: Uptime is {health.uptime}s (broker is running)")
        else:
            output.append(f"  FAIL: Uptime is {health.uptime} — unexpected")
            passed = False

        if health.db_connected:
            output.append("  PASS: Database is connected")
        else:
            output.append("  FAIL: Database is not connected")
            passed = False

        output.append("")
        output.append("═══ STORY 15: PASS ═══" if passed else "═══ STORY 15: FAIL ═══")
        print("\n".join(output))
        save_evidence("story15_health_check", banner, output)
        assert passed, "Story 15 failed"
