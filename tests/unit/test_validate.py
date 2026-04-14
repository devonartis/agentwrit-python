"""Unit tests for agentwrit.scope.validate — module-level token validation.

Tests the standalone validate(broker_url, token) function that any
resource server can use without constructing an AgentWritApp.

Spec: Section 6.4, ADR SDK-007 (module-level functions)
"""
from __future__ import annotations

from pytest_httpx import HTTPXMock

from agentwrit.models import ValidateResult
from agentwrit.scope import validate


class TestValidateValid:
    def test_returns_valid_result_with_claims(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={
                "valid": True,
                "claims": {
                    "iss": "agentwrit",
                    "sub": "spiffe://agentwrit.local/agent/o/t/i",
                    "aud": ["agentwrit"],
                    "exp": 9999999999,
                    "nbf": 1000000000,
                    "iat": 1000000000,
                    "jti": "jti-abc",
                    "scope": ["read:data:*"],
                    "task_id": "t",
                    "orch_id": "o",
                },
            },
        )
        result = validate("http://broker.test", "eyJ.test.token")
        assert isinstance(result, ValidateResult)
        assert result.valid is True
        assert result.claims is not None
        assert result.claims.iss == "agentwrit"
        assert result.claims.scope == ["read:data:*"]
        assert result.claims.task_id == "t"
        assert result.claims.orch_id == "o"

    def test_parses_delegation_chain(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={
                "valid": True,
                "claims": {
                    "iss": "agentwrit",
                    "sub": "spiffe://x",
                    "aud": [],
                    "exp": 0,
                    "nbf": 0,
                    "iat": 0,
                    "jti": "j",
                    "scope": ["s"],
                    "task_id": "t",
                    "orch_id": "o",
                    "delegation_chain": [
                        {
                            "agent": "spiffe://agentwrit.local/agent/o/t/abc",
                            "scope": ["read:data:*"],
                            "delegated_at": "2026-04-07T00:00:00Z",
                        }
                    ],
                    "chain_hash": "hash123",
                },
            },
        )
        result = validate("http://broker.test", "eyJ.delegated")
        assert result.claims is not None
        assert result.claims.delegation_chain is not None
        assert len(result.claims.delegation_chain) == 1
        assert result.claims.chain_hash == "hash123"

    def test_optional_sid_field(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={
                "valid": True,
                "claims": {
                    "iss": "agentwrit",
                    "sub": "spiffe://x",
                    "aud": [],
                    "exp": 0,
                    "nbf": 0,
                    "iat": 0,
                    "jti": "j",
                    "scope": [],
                    "task_id": "t",
                    "orch_id": "o",
                    "sid": "session-123",
                },
            },
        )
        result = validate("http://broker.test", "eyJ.token")
        assert result.claims is not None
        assert result.claims.sid == "session-123"


class TestValidateInvalid:
    def test_returns_invalid_result(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={"valid": False, "error": "token is invalid or expired"},
        )
        result = validate("http://broker.test", "eyJ.bad")
        assert result.valid is False
        assert result.claims is None
        assert result.error == "token is invalid or expired"

    def test_revoked_token_returns_invalid(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={"valid": False, "error": "token is invalid or expired"},
        )
        result = validate("http://broker.test", "eyJ.revoked")
        assert result.valid is False


class TestValidateEdgeCases:
    def test_strips_trailing_slash_from_broker_url(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={"valid": False, "error": "bad"},
        )
        result = validate("http://broker.test/", "eyJ.token")
        assert result.valid is False

    def test_sends_token_in_request_body(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={"valid": False, "error": "bad"},
        )
        validate("http://broker.test", "eyJ.the.token")
        request = httpx_mock.get_request()
        assert request is not None
        import json
        body = json.loads(request.read())
        assert body["token"] == "eyJ.the.token"


class TestValidateBrokerRealShape:
    """Bug: validate() crashed with KeyError on missing 'aud' field.

    Root cause: parser used data["aud"] instead of data.get("aud", []).
    The live broker does not return aud, sid, delegation_chain, or
    chain_hash for standard agent tokens. See spec Section 8.1.
    """

    def test_handles_broker_response_without_aud(self, httpx_mock: HTTPXMock):
        httpx_mock.add_response(
            url="http://broker.test/v1/token/validate",
            json={
                "valid": True,
                "claims": {
                    "iss": "agentwrit",
                    "sub": "spiffe://agentwrit.local/agent/o/t/abc",
                    "exp": 9999999999,
                    "nbf": 1000000000,
                    "iat": 1000000000,
                    "jti": "jti-abc",
                    "scope": ["read:data:user-42"],
                    "task_id": "t",
                    "orch_id": "o",
                },
            },
        )
        result = validate("http://broker.test", "eyJ.token")
        assert result.valid is True
        assert result.claims is not None
        assert result.claims.scope == ["read:data:user-42"]
        assert result.claims.aud == []
        assert result.claims.sid is None
        assert result.claims.delegation_chain is None
        assert result.claims.chain_hash is None
