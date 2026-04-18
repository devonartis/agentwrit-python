# Getting Started

Create your first agent credential. Roughly 5 minutes once [Prerequisites](#prerequisites) are met — longer if you also need to stand up a broker.

## Prerequisites

You need three things before any code below will work. The SDK is a client — it does **not** run the broker, and it does **not** mint its own credentials.

**1. Python 3.10+** in your environment.

**2. A reachable AgentWrit broker.** The broker is a separate service that issues and validates tokens.

- *Have a platform team running one?* Ask them for the broker URL.
- *Running it yourself?* Stand one up locally — the [broker repo](https://github.com/devonartis/agentwrit) ships a `docker compose` setup. From the agentwrit-python repo:
  ```bash
  docker compose up -d   # pulls devonartis/agentwrit from Docker Hub
  ```

**3. App credentials (`client_id` + `client_secret`).** These are issued by the **broker operator/admin** when they register your app and set its scope ceiling. The SDK cannot create them for you.

- *Have a broker admin?* Ask them to register your app and send you the `client_id` and `client_secret`.
- *You are the admin?* Use the included setup script (it registers an app and prints both values):
  ```bash
  export AGENTWRIT_ADMIN_SECRET="<your-broker-admin-secret>"
  uv run python demo/setup.py
  ```

If you already have a broker URL and a `client_id`/`client_secret`, skip to [Step 2](#step-2-connect-to-the-broker).

## Installation

Using [uv](https://docs.astral.sh/uv/) (recommended — install from GitHub, not yet on PyPI):

```bash
uv add git+https://github.com/devonartis/agentwrit-python.git
```

Or with pip:

```bash
pip install git+https://github.com/devonartis/agentwrit-python.git
```

The SDK depends on `httpx` (HTTP) and `cryptography` (Ed25519 operations). Both are installed automatically.

> **Heads-up: the SDK is synchronous.** v0.3.0 uses `httpx`'s sync client. If you're inside an async framework (FastAPI, Starlette, Sanic), wrap the SDK calls in `asyncio.to_thread()` so they don't block the event loop. The [Developer Guide](developer-guide.md#async--await-support) shows the pattern.

---

## Step 1: Set Up Your Credentials

Your broker operator provides two values when they register your application:

| Value | Purpose |
|-------|---------|
| `client_id` | Identifies your application to the broker |
| `client_secret` | Authenticates your application (never logged by the SDK) |

Store these as environment variables — never hardcode them:

```bash
export AGENTWRIT_BROKER_URL="https://broker.yourcompany.com"
export AGENTWRIT_CLIENT_ID="your-client-id"
export AGENTWRIT_CLIENT_SECRET="your-client-secret"
```

---

## Step 2: Connect to the Broker

```python
import os
from agentwrit import AgentWritApp

app = AgentWritApp(
    broker_url=os.environ["AGENTWRIT_BROKER_URL"],
    client_id=os.environ["AGENTWRIT_CLIENT_ID"],
    client_secret=os.environ["AGENTWRIT_CLIENT_SECRET"],
)
```

This creates your app instance. No broker call happens yet — the SDK authenticates lazily on the first `create_agent()` call. Once the app token has been issued, the SDK caches it and automatically re-authenticates when it drops below 60 seconds of remaining life, so you don't have to manage the session yourself.

> **If your first `create_agent()` call raises:** `AuthenticationError` means the `client_id` or `client_secret` is wrong (or rotated). `TransportError` means the broker URL is unreachable.

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
3. Got a challenge nonce from the broker (`GET /v1/challenge`)
4. Generated a fresh Ed25519 keypair in memory (unless you passed `private_key=`)
5. Signed the nonce with the private key
6. Registered the agent (`POST /v1/register`)

Steps 3–5 are a standard challenge-response handshake. The broker hands the SDK a random nonce, the SDK signs the nonce with the new private key, and the SDK ships the signature *plus* the matching public key to `/v1/register`. The broker verifies the signature against the public key — if that check passes, the broker has proof that whoever posted the registration holds the private key, without the private key ever leaving the calling process. The launch token ties that proof to your app and the scope ceiling you're allowed to mint inside.

You get back an `Agent` object with:

```python
print(agent.agent_id)    # spiffe://agentwrit.local/agent/my-service/read-customer-data/a1b2c3d4
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
    headers=agent.bearer_header,
)
print(resp.json())
```

`agent.bearer_header` is a convenience property that returns `{"Authorization": "Bearer <token>"}`. If you need to set additional headers, merge it into your own dict.

---

## Step 5: Validate the Token

Before trusting a token, ask the broker if it's still valid:

```python
from agentwrit import validate

result = validate(app.broker_url, agent.access_token)

if result.valid:
    print(f"Subject: {result.claims.sub}")     # SPIFFE ID
    print(f"Scope: {result.claims.scope}")      # Granted scope
    print(f"Task: {result.claims.task_id}")     # Task identifier
else:
    print(f"Invalid: {result.error}")
```

`validate()` is a module-level function — any service can call it without having an `AgentWritApp`. It just needs the broker URL and the token.

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
  └─ AgentWritApp (authenticated with broker)
       └─ Agent (SPIFFE identity + scoped JWT)
            ├─ Used as Bearer credential
            ├─ Validated by broker
            └─ Released when done
```

Exactly the scope needed, a unique cryptographic identity, and a token revoked the moment the task finished.

---

## Next Steps

| Guide | What You'll Learn |
|-------|-------------------|
| [Concepts](concepts.md) | Why AgentWrit exists, the trust model, and how scopes work |
| [Developer Guide](developer-guide.md) | Delegation, scope gating, error handling, and real patterns |
| [API Reference](api-reference.md) | Every class, method, parameter, and exception |
| [Testing Guide](testing-guide.md) | Unit tests, integration tests, running the test suite |
| [MedAssist demo](../demo/README.md) | See every capability in a working healthcare app |
| [Support-ticket demo](../demo2/README.md) | A three-agent pipeline — identity gating, cross-customer denial, natural TTL expiry |
