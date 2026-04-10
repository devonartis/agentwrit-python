# App 8: Compliance Audit Scanner

## The Scenario

You're a compliance auditor. Your job is to verify that every agent token in the system is still valid, check what scope each agent holds, and flag any anomalies — expired tokens, scope mismatches, or agents that were never released. You don't create agents or modify anything. You only **validate** and **inspect**.

This app is a read-only scanner that demonstrates the validation API as an independent service. It doesn't need an `AgentAuthApp` for most operations — `validate()` is a module-level function that only needs the broker URL and a token. It also demonstrates the full error model by intentionally triggering every error type and showing how to catch each one.

---

## What You'll Learn

| Concept | Why It Matters |
|---------|---------------|
| **`validate()` as a module-level function** | Any service can validate tokens without being an AgentAuthApp |
| **`ValidateResult` and `AgentClaims`** | What you get back from validation — every field explained |
| **The full error hierarchy** | `AgentAuthError` → `ProblemResponseError` → `AuthenticationError` / `AuthorizationError` / `RateLimitError` |
| **`ProblemDetail` (RFC 7807)** | Structured error info from the broker — type, title, detail, error_code, request_id |
| **Garbage token handling** | `validate()` never throws — it returns `valid=False` for bad tokens |
| **`app.health()` as a pre-flight check** | Verify the broker is up before scanning |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Compliance Audit Scanner Script                          │
│                                                           │
│  1. Pre-flight: check broker health                       │
│                                                           │
│  2. Create test agents (simulating a live system)         │
│     - Active agent (valid token)                          │
│     - Released agent (revoked token)                      │
│     - Expired agent (5s TTL, waited out)                  │
│                                                           │
│  3. Scan: validate each token and report                  │
│     - Token state (valid/expired/revoked)                 │
│     - Claims inspection (scope, identity, timestamps)     │
│     - Scope compliance check                              │
│                                                           │
│  4. Error model walkthrough                               │
│     - Trigger AuthenticationError (bad credentials)       │
│     - Trigger AuthorizationError (scope exceeds ceiling)  │
│     - Trigger AgentAuthError on released agent            │
│     - Show ProblemDetail fields for each                  │
│                                                           │
│  5. Garbage token test                                    │
│     - Validate fake/malformed tokens → all return False   │
└──────────────────────────────────────────────────────────┘
```

---

## The Code

```python
# audit_scanner.py
# Run: python audit_scanner.py

from __future__ import annotations

import os
import sys
import time

from agentauth import (
    AgentAuthApp,
    scope_is_subset,
    validate,
)
from agentauth.errors import (
    AgentAuthError,
    AuthenticationError,
    AuthorizationError,
    ProblemResponseError,
    RateLimitError,
    TransportError,
)
from agentauth.models import ValidateResult


def banner(text: str) -> None:
    print()
    print(f"── {text} ──")
    print()


def inspect_claims(result: ValidateResult, label: str) -> None:
    """Print detailed claims for a valid token."""
    if not result.valid or result.claims is None:
        print(f"  {label}: INVALID — {result.error}")
        return

    c = result.claims
    print(f"  {label}: VALID")
    print(f"    Subject:    {c.sub}")
    print(f"    Issuer:     {c.iss}")
    print(f"    Scope:      {c.scope}")
    print(f"    Task:       {c.task_id}")
    print(f"    Orch:       {c.orch_id}")
    print(f"    JTI:        {c.jti}")
    print(f"    Issued at:  {c.iat}")
    print(f"    Expires:    {c.exp}")
    if c.delegation_chain:
        print(f"    Chain:      {len(c.delegation_chain)} entries")
    else:
        print(f"    Chain:      none (direct token)")


def main() -> None:
    broker_url = os.environ["AGENTAUTH_BROKER_URL"]

    app = AgentAuthApp(
        broker_url=broker_url,
        client_id=os.environ["AGENTAUTH_CLIENT_ID"],
        client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
    )

    print("Compliance Audit Scanner")
    print("=" * 55)

    # ═══════════════════════════════════════════════════════════
    # Phase 1: Pre-flight health check
    # ═══════════════════════════════════════════════════════════
    banner("Phase 1: Broker Health Check")

    health = app.health()
    print(f"  Status:       {health.status}")
    print(f"  Version:      {health.version}")
    print(f"  Uptime:       {health.uptime}s")
    print(f"  DB connected: {health.db_connected}")
    print(f"  Audit events: {health.audit_events_count}")

    if health.status != "ok":
        print("  ⚠ Broker not healthy — aborting scan")
        sys.exit(1)

    print("  ✓ Broker healthy — proceeding with scan")

    # ═══════════════════════════════════════════════════════════
    # Phase 2: Create test agents
    # ═══════════════════════════════════════════════════════════
    banner("Phase 2: Creating Test Agents")

    # Active agent — token is valid right now
    active = app.create_agent(
        orch_id="audit-scan",
        task_id="active-agent-test",
        requested_scope=["read:data:resource-alpha", "write:data:resource-alpha"],
    )
    print(f"  Active agent: {active.agent_id}")
    print(f"    Scope: {active.scope}")

    # Released agent — token was explicitly revoked
    released = app.create_agent(
        orch_id="audit-scan",
        task_id="released-agent-test",
        requested_scope=["read:data:resource-beta"],
    )
    released.release()
    print(f"  Released agent: {released.agent_id} (already released)")

    # Short-lived agent — will expire naturally
    expiring = app.create_agent(
        orch_id="audit-scan",
        task_id="expiring-agent-test",
        requested_scope=["read:data:resource-gamma"],
        max_ttl=5,
    )
    print(f"  Expiring agent: {expiring.agent_id} (5s TTL)")
    print()
    print(f"  Waiting 7s for expiring agent to die...")
    time.sleep(7)

    # ═══════════════════════════════════════════════════════════
    # Phase 3: Scan — validate all tokens
    # ═══════════════════════════════════════════════════════════
    banner("Phase 3: Token Scan")

    tokens = [
        ("active", active.access_token),
        ("released", released.access_token),
        ("expired", expiring.access_token),
    ]

    valid_count = 0
    for label, token in tokens:
        result = validate(broker_url, token)
        if result.valid:
            inspect_claims(result, label)
            valid_count += 1
        else:
            print(f"  {label}: INVALID — \"{result.error}\"")
        print()

    print(f"  Summary: {valid_count}/{len(tokens)} tokens still valid")

    # Scope compliance check on the active agent
    if valid_count > 0:
        result = validate(broker_url, active.access_token)
        if result.valid and result.claims:
            print()
            print("  Scope compliance for active agent:")
            granted = result.claims.scope
            allowed_policies = ["read:data:*", "write:data:*"]

            compliant = scope_is_subset(granted, allowed_policies)
            print(f"    Granted:  {granted}")
            print(f"    Ceiling:  {allowed_policies}")
            print(f"    Compliant: {'YES' if compliant else 'NO'}")

    active.release()

    # ═══════════════════════════════════════════════════════════
    # Phase 4: Error Model Walkthrough
    # ═══════════════════════════════════════════════════════════
    banner("Phase 4: Error Model — Triggering Each Error Type")

    # Error 1: AuthenticationError (bad credentials)
    print("  Test: Bad credentials → AuthenticationError")
    try:
        bad_app = AgentAuthApp(
            broker_url=broker_url,
            client_id="fake-client-id",
            client_secret="fake-client-secret",
        )
        bad_app.create_agent(
            orch_id="audit-scan",
            task_id="auth-error-test",
            requested_scope=["read:data:test"],
        )
        print("    ERROR: Should have thrown AuthenticationError!")
    except AuthenticationError as e:
        print(f"    Caught: AuthenticationError")
        print(f"    Status: {e.status_code}")
        print(f"    Type:   {e.problem.type}")
        print(f"    Title:  {e.problem.title}")
        print(f"    Detail: {e.problem.detail}")
        print(f"    Code:   {e.problem.error_code}")
    except Exception as e:
        print(f"    Unexpected: {type(e).__name__}: {e}")
    print()

    # Error 2: AuthorizationError (scope exceeds ceiling)
    print("  Test: Scope exceeds ceiling → AuthorizationError")
    try:
        app.create_agent(
            orch_id="audit-scan",
            task_id="scope-error-test",
            requested_scope=["admin:revoke:everything"],  # Not in ceiling
        )
        print("    ERROR: Should have thrown AuthorizationError!")
    except AuthorizationError as e:
        print(f"    Caught: AuthorizationError")
        print(f"    Status: {e.status_code}")
        print(f"    Type:   {e.problem.type}")
        print(f"    Detail: {e.problem.detail}")
        print(f"    Code:   {e.problem.error_code}")
        if e.problem.request_id:
            print(f"    Req ID: {e.problem.request_id}")
    except Exception as e:
        print(f"    Unexpected: {type(e).__name__}: {e}")
    print()

    # Error 3: AgentAuthError on released agent operations
    print("  Test: Renew on released agent → AgentAuthError")
    try:
        released.renew()
        print("    ERROR: Should have thrown AgentAuthError!")
    except AgentAuthError as e:
        print(f"    Caught: AgentAuthError")
        print(f"    Message: {e}")
    print()

    # Error 4: Delegate on released agent
    print("  Test: Delegate on released agent → AgentAuthError")
    try:
        released.delegate(
            delegate_to="spiffe://agentauth.local/agent/fake/agent/test",
            scope=["read:data:test"],
        )
        print("    ERROR: Should have thrown AgentAuthError!")
    except AgentAuthError as e:
        print(f"    Caught: AgentAuthError")
        print(f"    Message: {e}")
    print()

    # ═══════════════════════════════════════════════════════════
    # Phase 5: Garbage Token Test
    # ═══════════════════════════════════════════════════════════
    banner("Phase 5: Garbage Token Validation")

    garbage_tokens = [
        ("empty string", ""),
        ("random text", "not-a-jwt-token"),
        ("partial jwt", "eyJhbGciOiJFZERTQSIsInR5cCI6IkpXVCJ9.abc.def"),
        ("sql injection", "' OR 1=1 --"),
        ("very long", "x" * 1000),
    ]

    print("  validate() never throws — it always returns valid=False:")
    print()
    for label, token in garbage_tokens:
        result = validate(broker_url, token)
        state = f"valid=False, error=\"{result.error}\"" if not result.valid else "VALID (unexpected!)"
        print(f"    {label:15s} → {state}")

    print()
    print("  ✓ All garbage tokens handled gracefully. No crashes.")

    # ═══════════════════════════════════════════════════════════
    # Summary
    # ═══════════════════════════════════════════════════════════
    banner("Scan Complete")
    print("  ✓ Broker health verified")
    print("  ✓ Token states validated (active, released, expired)")
    print("  ✓ Scope compliance checked")
    print("  ✓ Error model demonstrated (4 error types)")
    print("  ✓ Garbage tokens handled gracefully")
    print()
    print("  Exception hierarchy reference:")
    print("    AgentAuthError (catch-all)")
    print("    ├── ProblemResponseError (broker returned RFC 7807 error)")
    print("    │   ├── AuthenticationError (401)")
    print("    │   ├── AuthorizationError (403)")
    print("    │   └── RateLimitError (429)")
    print("    ├── TransportError (network failure)")
    print("    └── CryptoError (Ed25519 failure)")


if __name__ == "__main__":
    main()
```

---

## Setup Requirements

This app uses the **universal sample app** registered in the [README setup](README.md#one-time-setup-for-all-sample-apps). If you've already registered it, skip to Running It.

### Which Ceiling Scopes This App Uses

| Ceiling Scope | What This App Requests | Why |
|--------------|----------------------|-----|
| `read:data:*` | Various test agents | `read:data:resource-alpha`, `read:data:resource-beta`, `read:data:resource-gamma` |
| `write:data:*` | Active agent scope compliance test | `write:data:resource-alpha` |

> **Note:** This app intentionally tries to create an agent with `admin:revoke:everything` to trigger an `AuthorizationError`. That scope is NOT in the ceiling, so the broker rejects it — which is exactly what the demo expects.

## Running It

```bash
export AGENTAUTH_BROKER_URL="http://127.0.0.1:8080"
export AGENTAUTH_CLIENT_ID="<from registration>"
export AGENTAUTH_CLIENT_SECRET="<from registration>"

uv run python audit_scanner.py
```

> **Note:** This app waits 7 seconds for the expiring agent test. Full runtime is ~15 seconds.

---

## Expected Output

```
Compliance Audit Scanner
=======================================================

── Phase 1: Broker Health Check ──

  Status:       ok
  Version:      2.0.0
  Uptime:       142s
  DB connected: True
  Audit events: 47
  ✓ Broker healthy — proceeding with scan

── Phase 2: Creating Test Agents ──

  Active agent: spiffe://agentauth.local/agent/audit-scan/active-agent-test/a1b2...
    Scope: ['read:data:resource-alpha', 'write:data:resource-alpha']
  Released agent: spiffe://agentauth.local/agent/audit-scan/released-agent-test/c3d4... (already released)
  Expiring agent: spiffe://agentauth.local/agent/audit-scan/expiring-agent-test/e5f6... (5s TTL)

  Waiting 7s for expiring agent to die...

── Phase 3: Token Scan ──

  active: VALID
    Subject:    spiffe://agentauth.local/agent/audit-scan/active-agent-test/a1b2...
    Issuer:     agentauth
    Scope:      ['read:data:resource-alpha', 'write:data:resource-alpha']
    Task:       active-agent-test
    Orch:       audit-scan
    JTI:        8b2c4e7f...
    Issued at:  1744194000
    Expires:    1744194300
    Chain:      none (direct token)

  released: INVALID — "token is invalid or expired"

  expired: INVALID — "token is invalid or expired"

  Summary: 1/3 tokens still valid

  Scope compliance for active agent:
    Granted:  ['read:data:resource-alpha', 'write:data:resource-alpha']
    Ceiling:  ['read:data:*', 'write:data:*']
    Compliant: YES

── Phase 4: Error Model — Triggering Each Error Type ──

  Test: Bad credentials → AuthenticationError
    Caught: AuthenticationError
    Status: 401
    Type:   urn:agentauth:error:unauthorized
    Title:  Unauthorized
    Detail: invalid client credentials
    Code:   unauthorized

  Test: Scope exceeds ceiling → AuthorizationError
    Caught: AuthorizationError
    Status: 403
    Type:   urn:agentauth:error:scope_violation
    Detail: requested scope exceeds app scope ceiling
    Code:   scope_violation
    Req ID: bd4b257e53efe7f2

  Test: Renew on released agent → AgentAuthError
    Caught: AgentAuthError
    Message: agent has been released and cannot be renewed

  Test: Delegate on released agent → AgentAuthError
    Caught: AgentAuthError
    Message: agent has been released and cannot delegate

── Phase 5: Garbage Token Validation ──

  validate() never throws — it always returns valid=False:

    empty string    → valid=False, error="token is invalid or expired"
    random text     → valid=False, error="token is invalid or expired"
    partial jwt     → valid=False, error="token is invalid or expired"
    sql injection   → valid=False, error="token is invalid or expired"
    very long       → valid=False, error="token is invalid or expired"

  ✓ All garbage tokens handled gracefully. No crashes.

── Scan Complete ──

  ✓ Broker health verified
  ✓ Token states validated (active, released, expired)
  ✓ Scope compliance checked
  ✓ Error model demonstrated (4 error types)
  ✓ Garbage tokens handled gracefully

  Exception hierarchy reference:
    AgentAuthError (catch-all)
    ├── ProblemResponseError (broker returned RFC 7807 error)
    │   ├── AuthenticationError (401)
    │   ├── AuthorizationError (403)
    │   └── RateLimitError (429)
    ├── TransportError (network failure)
    └── CryptoError (Ed25519 failure)
```

---

## Key Takeaways

1. **`validate()` is a module-level function — no `AgentAuthApp` needed.** Any service in your architecture can validate tokens by calling `validate(broker_url, token)`. This is how downstream resource servers verify agent credentials without being registered as apps themselves.

2. **`validate()` never throws.** It always returns a `ValidateResult`. If the token is bad, `result.valid` is `False` and `result.error` has a generic message. No `try/except` needed for validation itself — only for network failures.

3. **The error hierarchy lets you catch at the right granularity.** Catch `AgentAuthError` for "anything went wrong." Catch `AuthenticationError` specifically for "bad credentials." Catch `AuthorizationError` specifically for "scope violation." The `ProblemDetail` on each error gives you structured info for logging and alerting.

4. **`ProblemDetail.request_id` links to broker logs.** When you get an `AuthorizationError`, the `request_id` field matches the broker's `X-Request-ID` header. You can cross-reference with broker logs to trace the exact request.

5. **Garbage tokens are handled gracefully.** Empty strings, SQL injection attempts, random text — `validate()` returns `valid=False` for all of them with the same generic error message. The broker doesn't leak information about why a token is invalid.
