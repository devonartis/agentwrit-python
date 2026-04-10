# App 6: Financial Trading Agent

## The Scenario

You run an automated trading system. The trading agent monitors market data and executes trades when conditions are met. A single trading session might run for 20 minutes — far longer than the default 5-minute token TTL. If the token expires mid-trade, the agent loses its authority and the trade fails partway through.

This app solves that problem with **token renewal**. The agent periodically calls `renew()` to get a fresh token with the same scope and identity. The old token is immediately revoked, and a new one is issued. The trading loop runs continuously, renewing every time it completes a cycle.

Additionally, this app demonstrates **custom short TTLs** for high-frequency trades that complete in seconds — minimizing credential exposure.

---

## What You'll Learn

| Concept | Why It Matters |
|---------|---------------|
| **`agent.renew()`** | How to refresh a token without re-registering the agent |
| **Renewal changes the token, not the identity** | `agent_id` stays the same; `access_token` changes |
| **Old tokens are revoked on renewal** | After `renew()`, the previous token is dead at the broker |
| **Custom `max_ttl`** | Setting shorter token lifetimes for quick tasks |
| **Renewal loops for long-running tasks** | The pattern for agents that run longer than the default TTL |

---

## Architecture

```
┌──────────────────────────────────────────────────────────┐
│  Trading Agent Script                                     │
│                                                           │
│  Session 1: Long-running swing trade (20 minutes)         │
│    create_agent(scope: [read:trades:*, write:trades:*])   │
│    max_ttl: 300 (5 minutes)                               │
│                                                           │
│    loop:                                                  │
│      check_market()     ← uses current token              │
│      if signal: execute_trade()                           │
│      renew()            ← fresh token, same identity      │
│      validate(old_token) → dead (proves rotation)         │
│                                                           │
│    release() when session ends                             │
│                                                           │
│  Session 2: High-frequency scalp trade (5 seconds)        │
│    create_agent(max_ttl: 10) ← very short TTL             │
│    execute_trade()                                        │
│    release() or let expire — either way, dead in 10s      │
└──────────────────────────────────────────────────────────┘
```

---

## The Code

```python
# trading_agent.py
# Run: python trading_agent.py

from __future__ import annotations

import os
import time

from agentauth import AgentAuthApp, scope_is_subset, validate
from agentauth.errors import AgentAuthError


def run_swing_trade_session(app: AgentAuthApp) -> None:
    """Long-running trading session with periodic token renewal.

    Simulates a swing trading strategy that monitors the market
    for 3 cycles (representing ~15 minutes of real time). Each
    cycle renews the token to keep the session alive.
    """

    print("── Session 1: Swing Trade (Long-Running with Renewal) ──")
    print()

    agent = app.create_agent(
        orch_id="trading-engine",
        task_id="swing-trade-20260409",
        requested_scope=[
            "read:trades:AAPL",
            "write:trades:AAPL",
        ],
        max_ttl=300,  # 5 minutes — must renew before this expires
    )

    print(f"Agent created for AAPL swing trade")
    print(f"  ID:    {agent.agent_id}")
    print(f"  Scope: {agent.scope}")
    print(f"  TTL:   {agent.expires_in}s")
    print()

    cycles = 3
    for i in range(cycles):
        print(f"  Cycle {i + 1}/{cycles}:")

        # Simulate market check
        required = [f"read:trades:AAPL"]
        if scope_is_subset(required, agent.scope):
            prices = {"AAPL": 187.42 + i * 0.53, "signal": "HOLD" if i < 2 else "SELL"}
            print(f"    Market: AAPL @ ${prices['AAPL']:.2f} — Signal: {prices['signal']}")
        else:
            print(f"    DENIED: Cannot read market data")
            break

        # Execute trade if signal fires
        if prices["signal"] == "SELL":
            trade_required = [f"write:trades:AAPL"]
            if scope_is_subset(trade_required, agent.scope):
                print(f"    TRADE: Selling 100 shares AAPL @ ${prices['AAPL']:.2f}")
            else:
                print(f"    DENIED: Cannot execute trade")

        # Renew the token to keep the session alive
        old_token = agent.access_token
        agent.renew()

        print(f"    Renewed: new token {agent.access_token[:25]}...")
        print(f"    New TTL: {agent.expires_in}s")

        # Prove the old token is dead
        old_result = validate(app.broker_url, old_token)
        if not old_result.valid:
            print(f"    Old token: dead ✓")
        else:
            print(f"    Old token: STILL VALID (unexpected)")

        # Identity is preserved across renewals
        print(f"    Identity: {agent.agent_id}")
        print()

    # End the session
    agent.release()
    print(f"  Session ended. Agent released.")

    # Confirm dead
    result = validate(app.broker_url, agent.access_token)
    print(f"  Final token state: {'dead' if not result.valid else 'STILL VALID'}")
    print()


def run_scalp_trade_session(app: AgentAuthApp) -> None:
    """High-frequency trade with very short TTL.

    For trades that execute in seconds, use a short TTL. If anything
    goes wrong, the token dies automatically — no cleanup needed.
    """

    print("── Session 2: Scalp Trade (Short TTL, No Renewal) ──")
    print()

    agent = app.create_agent(
        orch_id="trading-engine",
        task_id="scalp-trade-20260409",
        requested_scope=[
            "read:trades:TSLA",
            "write:trades:TSLA",
        ],
        max_ttl=10,  # 10 seconds — scalp trades are fast
    )

    print(f"Agent created for TSLA scalp trade")
    print(f"  ID:    {agent.agent_id}")
    print(f"  Scope: {agent.scope}")
    print(f"  TTL:   {agent.expires_in}s (very short — auto-expires if anything hangs)")
    print()

    # Execute immediately
    trade_scope = [f"write:trades:TSLA"]
    if scope_is_subset(trade_scope, agent.scope):
        print(f"  TRADE: Buying 50 shares TSLA @ $248.30")
        print(f"  Filled at $248.28 — saved $1.00 on execution")
    print()

    # Release immediately — don't wait for expiry
    agent.release()
    print(f"  Released immediately. Token dead.")

    result = validate(app.broker_url, agent.access_token)
    print(f"  Confirmed: {'dead' if not result.valid else 'STILL VALID'}")
    print()


def run_expired_session(app: AgentAuthApp) -> None:
    """Demonstrate natural token expiry.

    Creates an agent with a 5-second TTL, does NOT release it,
    waits for expiry, then validates to show the broker rejects it.
    """

    print("── Session 3: Natural Expiry (No Release) ──")
    print()

    agent = app.create_agent(
        orch_id="trading-engine",
        task_id="expired-test",
        requested_scope=["read:trades:SPY"],
        max_ttl=5,  # 5 seconds
    )

    print(f"Agent created with 5s TTL")
    print(f"  Token: {agent.access_token[:30]}...")

    # Token is valid now
    result = validate(app.broker_url, agent.access_token)
    print(f"  Before expiry: valid={result.valid}")
    print()

    print(f"  Waiting 7 seconds for natural expiry...")
    time.sleep(7)

    # Token should be expired
    result = validate(app.broker_url, agent.access_token)
    print(f"  After expiry:  valid={result.valid}")
    if not result.valid:
        print(f"  Error: \"{result.error}\"")
    print()

    # Release is safe even on expired tokens (no-op)
    agent.release()
    print(f"  Release after expiry: safe (no-op)")


def main() -> None:
    app = AgentAuthApp(
        broker_url=os.environ["AGENTAUTH_BROKER_URL"],
        client_id=os.environ["AGENTAUTH_CLIENT_ID"],
        client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
    )

    print("Financial Trading Agent — Renewal & TTL Demo")
    print("=" * 55)
    print()

    run_swing_trade_session(app)
    run_scalp_trade_session(app)
    run_expired_session(app)

    print()
    print("All sessions complete.")


if __name__ == "__main__":
    main()
```

---

## Setup Requirements

This app uses the **universal sample app** registered in the [README setup](README.md#one-time-setup-for-all-sample-apps). If you've already registered it, skip to Running It.

### Which Ceiling Scopes This App Uses

| Ceiling Scope | What This App Requests | Why |
|--------------|----------------------|-----|
| `read:trades:*` | `read:trades:AAPL`, `read:trades:TSLA`, `read:trades:SPY` | Read market data for specific symbols |
| `write:trades:*` | `write:trades:AAPL`, `write:trades:TSLA` | Execute trades for specific symbols |

The ceiling uses `*` so the trading engine can create agents for any stock symbol. Each agent still gets scope for only one specific symbol.

## Running It

```bash
export AGENTAUTH_BROKER_URL="http://127.0.0.1:8080"
export AGENTAUTH_CLIENT_ID="<from registration>"
export AGENTAUTH_CLIENT_SECRET="<from registration>"

uv run python trading_agent.py
```

> **Note:** Session 3 waits 7 seconds for token expiry. The full script takes ~15 seconds to run.

---

## Expected Output

```
Financial Trading Agent — Renewal & TTL Demo
=======================================================

── Session 1: Swing Trade (Long-Running with Renewal) ──

Agent created for AAPL swing trade
  ID:    spiffe://agentauth.local/agent/trading-engine/swing-trade-20260409/a1b2...
  Scope: ['read:trades:AAPL', 'write:trades:AAPL']
  TTL:   300s

  Cycle 1/3:
    Market: AAPL @ $187.42 — Signal: HOLD
    Renewed: new token eyJhbGciOiJFZERTQSIsInR5cCI6...
    New TTL: 300s
    Old token: dead ✓
    Identity: spiffe://agentauth.local/agent/trading-engine/swing-trade-20260409/a1b2...

  Cycle 2/3:
    Market: AAPL @ $187.95 — Signal: HOLD
    Renewed: new token eyJhbGciOiJFZERTQSIsInR5cCI6...
    New TTL: 300s
    Old token: dead ✓
    Identity: spiffe://agentauth.local/agent/trading-engine/swing-trade-20260409/a1b2...

  Cycle 3/3:
    Market: AAPL @ $188.48 — Signal: SELL
    TRADE: Selling 100 shares AAPL @ $188.48
    Renewed: new token eyJhbGciOiJFZERTQSIsInR5cCI6...
    New TTL: 300s
    Old token: dead ✓
    Identity: spiffe://agentauth.local/agent/trading-engine/swing-trade-20260409/a1b2...

  Session ended. Agent released.
  Final token state: dead

── Session 2: Scalp Trade (Short TTL, No Renewal) ──

Agent created for TSLA scalp trade
  ID:    spiffe://agentauth.local/agent/trading-engine/scalp-trade-20260409/c3d4...
  Scope: ['read:trades:TSLA', 'write:trades:TSLA']
  TTL:   10s (very short — auto-expires if anything hangs)

  TRADE: Buying 50 shares TSLA @ $248.30
  Filled at $248.28 — saved $1.00 on execution

  Released immediately. Token dead.
  Confirmed: dead

── Session 3: Natural Expiry (No Release) ──

Agent created with 5s TTL
  Token: eyJhbGciOiJFZERTQSIsInR5cCI6...
  Before expiry: valid=True

  Waiting 7 seconds for natural expiry...
  After expiry:  valid=False
  Error: "token is invalid or expired"

  Release after expiry: safe (no-op)

All sessions complete.
```

---

## Key Takeaways

1. **`renew()` gives you a new token with the same identity.** The `agent_id` (SPIFFE URI) never changes across renewals. Only the `access_token` and `expires_in` are refreshed. This is critical for audit trails — all renewals are attributed to the same agent identity.

2. **The old token is immediately revoked on renewal.** After `renew()`, the previous `access_token` is dead at the broker. If you cached it somewhere, it won't work. Always read `agent.access_token` after renewal.

3. **Renewal is atomic.** The broker revokes the old JTI before issuing the new one. If issuance fails, the old JTI is already invalidated — but the agent can safely retry because the registration is still valid.

4. **Short TTLs are a safety net.** A 10-second TTL for a scalp trade means that even if the process crashes and nobody calls `release()`, the token dies in 10 seconds. Match your TTL to the expected task duration.

5. **`release()` on an expired token is safe.** It's a no-op. This means your `finally` blocks don't need to check expiry — just always call `release()` and it handles both cases.
