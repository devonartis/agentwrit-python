"""Unit tests for agentwrit.models — frozen dataclasses.

Verifies construction, field access, immutability, and optional fields
for all public response models defined in spec Section 7.
"""
from __future__ import annotations

import pytest

from agentwrit.models import (
    AgentClaims,
    DelegatedToken,
    DelegationRecord,
    HealthStatus,
    ProblemDetail,
    RegisterResult,
    ValidateResult,
)


class TestDelegationRecord:
    def test_construction(self):
        rec = DelegationRecord(
            agent="spiffe://agentwrit.local/agent/orch/task/abc123",
            scope=["read:data:*"],
            delegated_at="2026-04-06T12:00:00Z",
        )
        assert rec.agent == "spiffe://agentwrit.local/agent/orch/task/abc123"
        assert rec.scope == ["read:data:*"]
        assert rec.delegated_at == "2026-04-06T12:00:00Z"

    def test_frozen(self):
        rec = DelegationRecord(agent="a", scope=[], delegated_at="t")
        with pytest.raises(AttributeError):
            rec.agent = "b"  # type: ignore[misc]


class TestAgentClaims:
    def test_all_required_fields(self):
        claims = AgentClaims(
            iss="agentwrit",
            sub="spiffe://agentwrit.local/agent/orch/task/abc",
            aud=["agentwrit"],
            exp=1700000000,
            nbf=1699999700,
            iat=1699999700,
            jti="jti-123",
            scope=["read:data:*"],
            task_id="task-1",
            orch_id="orch-1",
        )
        assert claims.iss == "agentwrit"
        assert claims.sub.startswith("spiffe://")
        assert claims.sid is None
        assert claims.delegation_chain is None
        assert claims.chain_hash is None

    def test_optional_fields(self):
        chain = [DelegationRecord(agent="a", scope=["s"], delegated_at="t")]
        claims = AgentClaims(
            iss="agentwrit",
            sub="spiffe://x",
            aud=[],
            exp=0,
            nbf=0,
            iat=0,
            jti="j",
            scope=[],
            task_id="t",
            orch_id="o",
            sid="session-1",
            delegation_chain=chain,
            chain_hash="abc",
        )
        assert claims.sid == "session-1"
        assert len(claims.delegation_chain) == 1
        assert claims.chain_hash == "abc"

    def test_frozen(self):
        claims = AgentClaims(
            iss="a", sub="b", aud=[], exp=0, nbf=0, iat=0,
            jti="j", scope=[], task_id="t", orch_id="o",
        )
        with pytest.raises(AttributeError):
            claims.iss = "x"  # type: ignore[misc]


class TestValidateResult:
    def test_valid_result(self):
        claims = AgentClaims(
            iss="agentwrit", sub="s", aud=[], exp=0, nbf=0, iat=0,
            jti="j", scope=[], task_id="t", orch_id="o",
        )
        result = ValidateResult(valid=True, claims=claims)
        assert result.valid is True
        assert result.claims is not None
        assert result.error is None

    def test_invalid_result(self):
        result = ValidateResult(valid=False, error="token is invalid or expired")
        assert result.valid is False
        assert result.claims is None
        assert result.error == "token is invalid or expired"


class TestDelegatedToken:
    def test_construction(self):
        chain = [DelegationRecord(agent="a", scope=["s"], delegated_at="t")]
        dt = DelegatedToken(
            access_token="eyJ...",
            expires_in=60,
            delegation_chain=chain,
        )
        assert dt.access_token == "eyJ..."
        assert dt.expires_in == 60
        assert len(dt.delegation_chain) == 1


class TestRegisterResult:
    def test_construction(self):
        rr = RegisterResult(
            agent_id="spiffe://agentwrit.local/agent/o/t/i",
            access_token="eyJ...",
            expires_in=300,
        )
        assert rr.agent_id.startswith("spiffe://")
        assert rr.expires_in == 300


class TestHealthStatus:
    def test_construction(self):
        hs = HealthStatus(
            status="ok",
            version="2.0.0",
            uptime=42,
            db_connected=True,
            audit_events_count=56,
        )
        assert hs.status == "ok"
        assert hs.db_connected is True


class TestProblemDetail:
    def test_required_fields(self):
        pd = ProblemDetail(
            type="urn:agentwrit:error:scope_violation",
            title="Forbidden",
            detail="scope exceeds ceiling",
            instance="/v1/app/launch-tokens",
        )
        assert pd.type == "urn:agentwrit:error:scope_violation"
        assert pd.status is None
        assert pd.error_code is None
        assert pd.request_id is None
        assert pd.hint is None

    def test_all_fields(self):
        pd = ProblemDetail(
            type="t",
            title="T",
            detail="d",
            instance="/v1/register",
            status=403,
            error_code="scope_violation",
            request_id="abc123",
            hint="check your scope",
        )
        assert pd.status == 403
        assert pd.hint == "check your scope"
