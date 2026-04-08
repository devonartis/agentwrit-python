# Getting Started

Create your first agent credential in 5 minutes.

## Prerequisites

- **Python 3.10+**
- A running [AgentAuth broker](https://github.com/devonartis/agentAuth) instance
- App credentials (`client_id` and `client_secret`) from your broker operator

## Installation

Using [uv](https://docs.astral.sh/uv/) (recommended):

```bash
uv add agentauth
```

Or with pip:

```bash
pip install agentauth
```

The SDK depends on `httpx` (HTTP) and `cryptography` (Ed25519 operations). Both are installed automatically.

---

## Step 1: Set Up Your Credentials

Your broker operator provides two values when they register your application:

| Value | Purpose |
|-------|---------|
| `client_id` | Identifies your application to the broker |
| `client_secret` | Authenticates your application (never logged by the SDK) |

Store these as environment variables — never hardcode them:

```bash
export AGENTAUTH_BROKER_URL="https://broker.yourcompany.com"
export AGENTAUTH_CLIENT_ID="your-client-id"
export AGENTAUTH_CLIENT_SECRET="your-client-secret"
```

---

## Step 2: Connect to the Broker

```python
import os
from agentauth import AgentAuthApp

app = AgentAuthApp(
    broker_url=os.environ["AGENTAUTH_BROKER_URL"],
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)
```

This creates your app instance. No broker call happens yet — the SDK authenticates lazily on the first `create_agent()` call.

---

## Step 3: Create an Agent

```python
agent = app.create_agent(
    orch_id="my-service",
    task_id="read-customer-data",
    requested_scope=["read:data:customers"],
)
```

The SDK just did a lot of work behind the scenes:

1. Authenticated your app with the broker (`POST /v1/app/auth`)
2. Created a launch token with your requested scope (`POST /v1/app/launch-tokens`)
3. Generated a fresh Ed25519 keypair in memory
4. Got a challenge nonce from the broker (`GET /v1/challenge`)
5. Signed the nonce with the private key
6. Registered the agent (`POST /v1/register`)

You get back an `Agent` object with:

```python
print(agent.agent_id)    # spiffe://agentauth.local/agent/my-service/read-customer-data/a1b2c3d4
print(agent.scope)       # ['read:data:customers']
print(agent.access_token) # eyJhbGciOiJFZERTQS... (JWT)
print(agent.expires_in)  # 300 (seconds)
```

---

## Step 4: Use the Token

The agent's `access_token` is a standard JWT. Use it as a Bearer credential with any API that validates against the broker:

```python
import httpx

resp = httpx.get(
    "https://your-api/data/customers",
    headers={"Authorization": f"Bearer {agent.access_token}"},
)
print(resp.json())
```

---

## Step 5: Validate the Token

Before trusting a token, ask the broker if it's still valid:

```python
from agentauth import validate

result = validate(broker_url, agent.access_token)

if result.valid:
    print(f"Subject: {result.claims.sub}")     # SPIFFE ID
    print(f"Scope: {result.claims.scope}")      # Granted scope
    print(f"Task: {result.claims.task_id}")     # Task identifier
else:
    print(f"Invalid: {result.error}")
```

`validate()` is a module-level function — any service can call it without having an `AgentAuthApp`. It just needs the broker URL and the token.

---

## Step 6: Release When Done

When your agent finishes its task, release the token:

```python
agent.release()
```

After release, the broker rejects the token on all future requests. This shrinks the attack window — even if the token was leaked, it's already dead.

Calling `release()` twice is safe. The second call is a no-op.

---

## What You Just Built

```
Your App
  └─ AgentAuthApp (authenticated with broker)
       └─ Agent (SPIFFE identity + scoped JWT)
            ├─ Used as Bearer credential
            ├─ Validated by broker
            └─ Released when done
```

The agent had exactly the scope it needed (`read:data:customers`), a unique cryptographic identity, and a short-lived token that was revoked the moment the task finished.

---

## Next Steps

| Guide | What You'll Learn |
|-------|-------------------|
| [Concepts](concepts.md) | Why AgentAuth exists, the trust model, and how scopes work |
| [Developer Guide](developer-guide.md) | Delegation, scope gating, error handling, and real patterns |
| [API Reference](api-reference.md) | Every class, method, parameter, and exception |
