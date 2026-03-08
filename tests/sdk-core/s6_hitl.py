#!/usr/bin/env python3
"""SDK-S6: HITL Approval Flow -- live acceptance test."""

from __future__ import annotations

import os
import sys

import requests

print("""
======================================================================
SDK-S6 -- HITL Approval Flow
======================================================================

Who: The developer.

What: The developer requests write:data:* which is HITL-gated on the
test app. The SDK raises HITLApprovalRequired with approval_id and
expires_at. The developer's app surfaces this to the end-user. After
the human approves, retry get_token with the approval_token.

Why: HITL is the core security feature. Some scopes require human
authorization before the broker issues a credential. The SDK must make
this flow ergonomic -- raise a specific exception, provide the approval
data, accept the approval token on retry.

How to run:
    export AGENTAUTH_ADMIN_SECRET=<admin-secret>
    python tests/sdk-core/s6_hitl.py

Expected: First call raises HITLApprovalRequired. After approval, second
call with approval_token returns a valid JWT.
======================================================================
""")

from agentauth import AgentAuthClient, HITLApprovalRequired

BROKER: str = os.environ.get("AGENTAUTH_BROKER_URL", "http://127.0.0.1:8080")
client = AgentAuthClient(
    broker_url=BROKER,
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)

passed: int = 0
failed: int = 0

# Get the app token for approval calls (requires app:launch-tokens:* scope)
app_token: str = client._ensure_app_token()  # noqa: SLF001

print("--- Test 1: HITL scope raises HITLApprovalRequired ---")
approval_id: str = ""
try:
    client.get_token("s6-agent", ["write:data:transfers"])
    print("  FAILED: No exception raised\n")
    failed += 1
except HITLApprovalRequired as e:
    approval_id = e.approval_id
    print(f"  HITLApprovalRequired raised!")
    print(f"  approval_id: {e.approval_id}")
    print(f"  expires_at:  {e.expires_at}")
    assert e.approval_id.startswith("apr-")
    print("  Result: PASS\n")
    passed += 1
except Exception as e:
    print(f"  FAILED: {type(e).__name__}: {e}\n")
    failed += 1

print("--- Test 2: Approve and retry -> get valid JWT ---")
if approval_id:
    try:
        # Approve using the app JWT (app:launch-tokens:* scope)
        print(f"  Approving {approval_id} as user:qa-tester@example.com ...")
        approve_resp = requests.post(
            f"{BROKER}/v1/app/approvals/{approval_id}/approve",
            headers={"Authorization": f"Bearer {app_token}"},
            json={"principal": "user:qa-tester@example.com"},
            timeout=10,
        )
        assert approve_resp.status_code == 200, f"Approval failed: {approve_resp.text}"
        approval_token: str = approve_resp.json()["approval_token"]
        print(f"  Approval token received: {approval_token[:40]}...")

        # Retry with approval token
        token: str = client.get_token(
            "s6-agent", ["write:data:transfers"], approval_token=approval_token
        )
        print(f"  Token received: {token[:60]}...")
        assert len(token.split(".")) == 3

        # Validate -- check original_principal
        result: dict[str, object] = requests.post(
            f"{BROKER}/v1/token/validate", json={"token": token}, timeout=10
        ).json()
        claims: dict[str, object] = result["claims"]  # type: ignore[assignment]
        print(f"  original_principal: {claims.get('original_principal')}")
        assert claims.get("original_principal") == "user:qa-tester@example.com"
        print("  Result: PASS\n")
        passed += 1
    except Exception as e:
        print(f"  FAILED: {e}\n")
        failed += 1
else:
    print("  SKIPPED: No approval_id from test 1\n")

print("======================================================================")
if failed == 0:
    print(f"VERDICT: PASS -- {passed}/{passed + failed} tests passed.")
    print("  HITL flow works: raise -> approve -> retry -> JWT with principal.")
else:
    print(f"VERDICT: FAIL -- {passed}/{passed + failed} tests passed.")
    sys.exit(1)
print("======================================================================")
