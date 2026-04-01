<p align="center">
  <img src="docs/assets/agentauth-logo.png" alt="AgentAuth" width="300">
</p>

<h1 align="center">AgentAuth Python SDK</h1>

<p align="center">
  <a href="https://opensource.org/licenses/MIT"><img src="https://img.shields.io/badge/license-MIT-blue.svg" alt="License: MIT"></a>
  <a href="https://www.python.org/downloads/"><img src="https://img.shields.io/badge/python-3.10+-blue.svg" alt="Python 3.10+"></a>
  <a href="https://github.com/devonartis/agentauth-python-sdk/actions"><img src="https://img.shields.io/badge/tests-122%20passing-brightgreen.svg" alt="Tests: 122 passing"></a>
  <a href="https://mypy-lang.org/"><img src="https://img.shields.io/badge/type%20checked-mypy%20strict-blue.svg" alt="Type checked: mypy strict"></a>
</p>

<p align="center">
  Ephemeral, task-scoped credentials for AI agents.<br>
  Built on Ed25519 challenge-response and the <a href="https://github.com/devonartis/AI-Security-Blueprints/blob/main/patterns/ephemeral-agent-credentialing/versions/v1.2.md">Ephemeral Agent Credentialing</a> pattern.
</p>

---

## Why AgentAuth?

AI agents need credentials to access databases, APIs, and file systems. Most teams give agents shared API keys or inherit user permissions — both create over-privileged, long-lived, unauditable access. AgentAuth takes a different approach:

- **Ephemeral identities** — every agent instance gets a unique Ed25519 keypair, generated in memory and never persisted to disk
- **Task-scoped tokens** — credentials are limited to exactly what the agent needs (`read:data:customers`, not `read:*:*`)
- **Short-lived by default** — tokens expire in minutes, not hours or days
- **Delegation chains** — agents can delegate narrower permissions to other agents, with scope attenuation enforced at every hop

The SDK wraps the [AgentAuth broker](https://github.com/devonartis/agentAuth) API into simple Python calls. What takes 40+ lines of manual Ed25519 key management, nonce signing, and token caching becomes three lines:

```python
from agentauth import AgentAuthClient

client = AgentAuthClient(broker_url, client_id, client_secret)
token = client.get_token("data-analyst", ["read:data:customers"])
```

## Installation

```bash
uv add git+https://github.com/devonartis/agentauth-python-sdk
```

Or with pip:

```bash
pip install git+https://github.com/devonartis/agentauth-python-sdk
```

**Requirements:** Python 3.10+ and a running [AgentAuth broker](https://github.com/devonartis/agentAuth) instance.

## Quick Start

```python
import os
from agentauth import AgentAuthClient

# 1. Connect — authenticates your app with the broker on creation
client = AgentAuthClient(
    broker_url=os.environ["AGENTAUTH_BROKER_URL"],
    client_id=os.environ["AGENTAUTH_CLIENT_ID"],
    client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
)

# 2. Get a scoped credential for an agent
token = client.get_token("data-analyst", scope=["read:data:*"])

# 3. Use the token as a standard Bearer credential
import requests
resp = requests.get(
    "https://your-api/data/customers",
    headers={"Authorization": f"Bearer {token}"},
)

# 4. Delegate a narrower scope to another agent
delegated = client.delegate(
    token, to_agent_id="spiffe://agentauth/agent/summarizer",
    scope=["read:data:reports"], ttl=120,
)

# 5. Validate and revoke
result = client.validate_token(token)  # {"valid": True, "claims": {...}}
client.revoke_token(token)             # Immediate invalidation
```

## Architecture

```mermaid
graph TB
    subgraph App["🔧 Your Application"]
        direction TB
        Client["<b>AgentAuthClient</b><br/>get_token() · delegate()<br/>revoke_token() · validate_token()"]
        Cache["Token Cache<br/><i>Thread-safe · Auto-renewal at 80% TTL</i>"]
        Client --- Cache
    end

    subgraph Broker["🔐 AgentAuth Broker"]
        direction LR
        AuthGroup["App Auth<br/>/v1/app/auth<br/>/v1/app/launch-tokens"]
        CredGroup["Credentials<br/>/v1/challenge<br/>/v1/register"]
        MgmtGroup["Management<br/>/v1/delegate<br/>/v1/token/validate<br/>/v1/token/release"]
    end

    Agents["🤖 Your AI Agents"]
    APIs["🌐 Protected APIs"]

    Client ==>|"HTTPS · Ed25519"| Broker
    Client -.->|"Issue JWT"| Agents
    Agents ==>|"Bearer auth"| APIs

    style App fill:#dbeafe,stroke:#3b82f6,stroke-width:2px,color:#1e3a5f
    style Broker fill:#fef3c7,stroke:#f59e0b,stroke-width:2px,color:#78350f
    style Agents fill:#d1fae5,stroke:#10b981,stroke-width:2px
    style APIs fill:#ede9fe,stroke:#8b5cf6,stroke-width:2px
    style AuthGroup fill:#fef9c3,stroke:#eab308
    style CredGroup fill:#fef9c3,stroke:#eab308
    style MgmtGroup fill:#fef9c3,stroke:#eab308
```

## Deployment Topology

```mermaid
graph LR
    subgraph AppHost["🖥️ Your Infrastructure"]
        direction TB
        App["Python App<br/><i>FastAPI · Flask · Celery</i>"]
        SDK["AgentAuthClient<br/><i>pip install agentauth</i>"]
        A1["🤖 Agent: reader"]
        A2["🤖 Agent: writer"]
        A3["🤖 Agent: analyst"]
        App --- SDK
        SDK -.-> A1
        SDK -.-> A2
        SDK -.-> A3
    end

    subgraph BrokerHost["🔐 Broker (Docker / K8s)"]
        direction TB
        BrokerAPI["AgentAuth Broker<br/><i>Go · REST API</i>"]
        Store["Token Store<br/><i>JTI registry · Revocation list</i>"]
        Audit["Audit Log<br/><i>All credential operations</i>"]
        BrokerAPI --- Store
        BrokerAPI --- Audit
    end

    subgraph Downstream["🌐 Protected Services"]
        direction TB
        DB["Database API"]
        Files["File Storage"]
        Ext["External SaaS"]
    end

    SDK ==>|"TLS · mTLS optional"| BrokerAPI
    A1 ==>|"Bearer JWT"| DB
    A2 ==>|"Bearer JWT"| Files
    A3 ==>|"Bearer JWT"| Ext
    style AppHost fill:#dbeafe,stroke:#3b82f6,stroke-width:2px
    style BrokerHost fill:#fef3c7,stroke:#f59e0b,stroke-width:2px
    style Downstream fill:#ede9fe,stroke:#8b5cf6,stroke-width:2px
```

## The Credential Flow

Every call to `get_token()` executes an 8-step protocol internally:

```mermaid
sequenceDiagram
    participant App as 🔧 Your App
    participant SDK as 📦 AgentAuth SDK
    participant Broker as 🔐 Broker

    App->>SDK: client.get_token("analyst", ["read:data:*"])

    rect rgb(219, 234, 254)
        Note over SDK: Step 1 — Cache Check
        SDK->>SDK: Cache miss (first call)
        Note over SDK: Step 2 — App Auth
        SDK->>SDK: Ensure app JWT valid
    end

    rect rgb(254, 243, 199)
        Note over SDK,Broker: Step 3 — Launch Token
        SDK->>Broker: POST /v1/app/launch-tokens
        Broker-->>SDK: launch_token
    end

    rect rgb(209, 250, 229)
        Note over SDK: Step 4 — Key Generation
        SDK->>SDK: Generate Ed25519 keypair (in memory)
    end

    rect rgb(254, 243, 199)
        Note over SDK,Broker: Step 5 — Challenge
        SDK->>Broker: GET /v1/challenge
        Broker-->>SDK: nonce (hex, 30s TTL)
    end

    rect rgb(219, 234, 254)
        Note over SDK: Step 6 — Sign Nonce
        SDK->>SDK: Sign nonce with ephemeral private key
    end

    rect rgb(254, 243, 199)
        Note over SDK,Broker: Step 7 — Register
        SDK->>Broker: POST /v1/register
        Broker-->>SDK: Agent JWT + SPIFFE ID
    end

    rect rgb(209, 250, 229)
        Note over SDK: Step 8 — Cache
        SDK->>SDK: Store token in cache
    end

    SDK-->>App: JWT string
```

## Delegation Chain

Agents can delegate narrower permissions to other agents:

```mermaid
graph TD
    O["<b>Orchestrator</b><br/>read:data:*"]

    O -->|"✅ subset"| WA["<b>Worker A</b><br/>read:data:results"]
    O -->|"✅ subset"| WB["<b>Worker B</b><br/>read:data:logs"]
    O -.->|"❌ not in scope"| WC["<b>Worker C</b><br/>write:data:records"]

    WA -->|"✅ subset"| SW["<b>Sub-worker</b><br/>read:data:results"]
    WA -.->|"❌ wider than A"| SW2["<b>Sub-worker</b><br/>read:data:*"]

    style O fill:#3b82f6,color:#fff,stroke:#1d4ed8,stroke-width:2px
    style WA fill:#22c55e,color:#fff,stroke:#16a34a,stroke-width:2px
    style WB fill:#22c55e,color:#fff,stroke:#16a34a,stroke-width:2px
    style WC fill:#ef4444,color:#fff,stroke:#dc2626,stroke-width:2px
    style SW fill:#f59e0b,color:#fff,stroke:#d97706,stroke-width:2px
    style SW2 fill:#ef4444,color:#fff,stroke:#dc2626,stroke-width:2px
```

> Scope can only **narrow** at each hop. Revoking the orchestrator's token invalidates all downstream delegations.

## Error Hierarchy

```mermaid
graph TD
    Base["<b>AgentAuthError</b><br/><i>Base exception</i>"]

    Base --> Auth["<b>AuthenticationError</b><br/>HTTP 401 · Bad credentials"]
    Base --> Scope["<b>ScopeCeilingError</b><br/>HTTP 403 · Scope exceeds ceiling"]
    Base --> Rate["<b>RateLimitError</b><br/>HTTP 429 · Too many requests"]
    Base --> Unavail["<b>BrokerUnavailableError</b><br/>5xx · Connection failure"]
    Base --> Expired["<b>TokenExpiredError</b><br/>Token TTL exceeded"]

    style Base fill:#dc2626,color:#fff,stroke:#991b1b,stroke-width:2px
    style Auth fill:#ef4444,color:#fff,stroke:#dc2626
    style Scope fill:#ef4444,color:#fff,stroke:#dc2626
    style Rate fill:#ef4444,color:#fff,stroke:#dc2626
    style Unavail fill:#ef4444,color:#fff,stroke:#dc2626
    style Expired fill:#ef4444,color:#fff,stroke:#dc2626
```

## Security Properties

| Property | Implementation |
|----------|----------------|
| **Ephemeral keys** | Ed25519 keypairs generated in memory per `get_token()` call. Private keys never touch disk. |
| **Task-scoped tokens** | `action:resource:identifier` scope format enforced by the broker. |
| **Short TTLs** | Default 5-minute token lifetime. Stolen tokens expire quickly. |
| **Scope attenuation** | Delegation can only narrow permissions. Enforced at every hop in the chain. |
| **Thread safety** | Token cache and app auth state protected by `threading.Lock`. |
| **TLS by default** | Certificate verification enabled. No silent `verify=False`. |
| **No secret leakage** | `client_secret` never appears in error messages, `repr()`, or logs. |

## Standards Alignment

The SDK implements the [Ephemeral Agent Credentialing](https://github.com/devonartis/AI-Security-Blueprints/blob/main/patterns/ephemeral-agent-credentialing/versions/v1.2.md) pattern (v1.2), which aligns with:

- **NIST IR 8596** — Unique AI agent identities via SPIFFE IDs
- **NIST SP 800-207** — Zero-trust per-request validation
- **OWASP Top 10 for Agentic AI (2026)** — ASI03 (Identity/Privilege Abuse), ASI07 (Insecure Inter-Agent Communication)
- **IETF WIMSE** (draft-ietf-wimse-arch-06) — Delegation chain re-binding
- **IETF draft-klrc-aiagent-auth-00** — OAuth/WIMSE/SPIFFE framework for AI agents

## Documentation

| Guide | Description |
|-------|-------------|
| [Concepts](docs/concepts.md) | Architecture, security model, scopes, and delegation |
| [Getting Started](docs/getting-started.md) | Install, connect, and issue your first credential in 5 minutes |
| [Developer Guide](docs/developer-guide.md) | Multi-agent delegation, error handling, and framework integration |
| [API Reference](docs/api-reference.md) | Complete method signatures, exception hierarchy, and behavior reference |

For broker setup and administration, see the [AgentAuth broker documentation](https://github.com/devonartis/agentAuth/tree/develop/docs).

## Contributing

Contributions are welcome. Please open an issue to discuss proposed changes before submitting a pull request.

```bash
# Development setup
git clone https://github.com/devonartis/agentauth-python-sdk
cd agentauth-python-sdk
uv sync

# Run the full check suite
uv run mypy src/agentauth/       # Type checking (strict mode)
uv run ruff check src/ tests/    # Linting
uv run pytest tests/unit/        # Unit tests (no broker required)
```

## License

[MIT](LICENSE)
