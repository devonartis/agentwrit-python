# Agent Cryptographic Identity

## The Key Insight

Every AgentAuth agent holds an Ed25519 private key. Today, that key is used once — to sign a nonce during registration, proving the agent controls the keypair. The broker stores the public key and issues a JWT.

But that private key is more than a registration artifact. It's a **cryptographic identity** — the same primitive that SSH uses for machine authentication, that TLS uses for mutual auth, and that SPIFFE/SPIRE uses for workload identity. The agent can prove "I am this specific entity" to anyone who holds its public key, without passwords, without tokens, without the broker being online.

This document explores what becomes possible when the agent's keypair is treated as a first-class identity, not just a registration ceremony.

## How It Works Today

```
App (client_id/secret)          Agent (Ed25519 keypair)          Broker (Ed25519 keypair)
        |                               |                               |
        |-- POST /v1/app/auth --------->|                               |
        |<-- app JWT -------------------|                               |
        |                               |                               |
        |-- POST /v1/app/launch-tokens ->                               |
        |<-- launch_token --------------|                               |
        |                               |                               |
        |       generate_keypair() ---->|                               |
        |                               |-- GET /v1/challenge --------->|
        |                               |<-- nonce --------------------|
        |                               |                               |
        |       sign(nonce, private_key)|                               |
        |                               |-- POST /v1/register -------->|
        |                               |   (public_key, signature,    |
        |                               |    launch_token, nonce)      |
        |                               |                               |
        |                               |   verify(signature, pubkey)  |
        |                               |   store(pubkey)              |
        |                               |   issue JWT (signed by       |
        |                               |     BROKER's private key)    |
        |                               |<-- agent JWT + SPIFFE ID ----|
```

Three separate key systems:

| Entity | Key | Purpose |
|--------|-----|---------|
| **App** | `client_id` + `client_secret` (bcrypt) | Authenticate to broker, create launch tokens |
| **Agent** | Ed25519 keypair (per agent, ephemeral) | Prove identity at registration. Public key stored by broker. |
| **Broker** | Ed25519 keypair (persistent, one per broker) | Sign ALL JWTs and delegation records |

The agent's private key never leaves the SDK. Only the public key is transmitted during registration.

## The SSH Analogy

SSH machines prove identity the same way:

| SSH | AgentAuth |
|-----|-----------|
| `ssh-keygen` generates keypair | `generate_keypair()` at agent creation |
| Public key added to `authorized_keys` | Public key stored in broker's `AgentRecord` |
| Private key stays on the machine | Private key stays in SDK memory |
| Machine proves identity by signing challenge | Agent proves identity by signing nonce |
| `known_hosts` tracks which key belongs to which host | Broker tracks which key belongs to which SPIFFE ID |

The difference: SSH keys are long-lived (persist on disk). AgentAuth keys are ephemeral (live in memory, die with the agent). But the cryptographic primitive is identical — and there's no reason agent keys can't be persisted too.

## What the Agent's Private Key Could Do

### 1. Agent-to-Agent Mutual Authentication

**Status:** Already implemented in broker Go code (`internal/mutauth/`), not HTTP-exposed yet.

Two agents verify each other's identity without involving the app:

```
Agent A                          Broker                         Agent B
   |                               |                               |
   |-- initiate(target=B) -------->|                               |
   |                               |-- nonce to B --------------->|
   |                               |<-- B signs nonce with B's key |
   |                               |                               |
   |   verify B's signature        |                               |
   |   against B's stored pubkey   |                               |
   |<-- mutual auth complete ------|                               |
```

Agent A knows it's talking to the real Agent B — not an impersonator — because only B holds the private key that matches the public key the broker stored at B's registration.

**Use case:** Multi-agent pipelines where agents hand off work directly. The receiving agent can verify the sender is who it claims to be before accepting delegated authority.

### 2. Agent-to-Service Authentication

Agent proves identity to an external service without involving the broker at runtime:

```
Agent                           External Service
   |                               |
   |-- "I am spiffe://agent/X" --->|
   |<-- challenge nonce ------------|
   |-- sign(nonce, private_key) --->|
   |                               |
   |   service calls broker:       |
   |   GET /v1/agents/X/pubkey     |
   |   verify(signature, pubkey)   |
   |                               |
   |<-- authenticated --------------|
```

The service verifies the agent's identity by checking the signature against the broker's stored public key. This works even if the agent's JWT has expired — the keypair outlives the token.

**Use case:** Agent connects to a database, message queue, or third-party API. The service trusts the agent based on its cryptographic identity, not just a Bearer token that could be stolen.

### 3. Signed Actions (Non-Repudiable Audit)

Agent signs every significant action with its private key:

```python
# Agent signs the action payload
action = {"tool": "issue_refund", "customer": "lewis-smith", "amount": 247.50}
signature = agent.sign(json.dumps(action))

# The audit record includes the signature
audit_entry = {
    "agent_id": agent.agent_id,
    "action": action,
    "signature": signature,  # Provably from THIS agent
    "timestamp": "2026-04-09T10:00:00Z",
}
```

Today's audit trail says "agent X did Y" — but the broker wrote that record. With signed actions, the **agent itself** cryptographically attests to what it did. Even if the broker's audit database is compromised, the signatures remain verifiable.

**Use case:** Regulated environments (healthcare, finance) where audit evidence must be non-repudiable. The agent's signature proves it performed the action — not just that it had a token at the time.

### 4. Key Persistence for Long-Lived Agents

Store the agent's keypair on disk, like SSH:

```python
# First run — generate and persist
agent = app.create_agent(
    orch_id="monitor",
    task_id="watchdog",
    requested_scope=["read:metrics:*"],
    key_path="/var/agentauth/watchdog.key",  # Persisted
)

# Later — agent restarts, re-registers with same key
agent = app.create_agent(
    orch_id="monitor",
    task_id="watchdog",
    requested_scope=["read:metrics:*"],
    key_path="/var/agentauth/watchdog.key",  # Same key loaded
)
# Broker sees same public key → recognizes as same entity
```

The broker could recognize the public key and link it to the previous SPIFFE identity, enabling:
- **Identity continuity** across restarts
- **Key rotation** (register with new key, broker updates the stored record)
- **Revocation by key** (revoke all tokens ever issued to this public key)

**Use case:** Long-running agents (monitoring, scheduled jobs, always-on services) that need persistent identity across process restarts.

### 5. Request Signing (Token Theft Protection)

Agent signs every HTTP request with its private key. Even if the JWT is stolen, the attacker can't make signed requests:

```
Agent                           Target Service
   |                               |
   |-- request + JWT + signature -->|
   |                               |
   |   1. Verify JWT (standard)    |
   |   2. Verify request signature |
   |      against stored pubkey    |
   |                               |
   |   Both must pass.             |
   |   Stolen JWT without private  |
   |   key → signature fails.      |
```

This is **proof-of-possession** — the agent proves it holds the key that was registered, not just a token that could have been intercepted. Same concept as mTLS client certificates, but at the application layer.

**Use case:** High-security environments where JWT theft is a concern. Defense-in-depth: even if an attacker captures the token from memory, logs, or network traffic, they can't use it without the private key.

### 6. Cross-Broker Federation

Agent registered with Broker A proves identity to Broker B:

```
Agent                    Broker A                Broker B
   |                        |                        |
   | (registered with A)    |                        |
   |                        |                        |
   |-- "I am spiffe://A/agent/X" ------------------->|
   |<-- challenge nonce -----------------------------|
   |-- sign(nonce, private_key) --------------------->|
   |                        |                        |
   |                        |<-- fetch pubkey for X --|
   |                        |-- pubkey ------------->|
   |                        |                        |
   |                        |   verify(sig, pubkey)  |
   |<-- federated token -----------------------------|
```

No shared secrets between brokers. Broker B trusts Agent X because Broker A vouches for the public key. The agent's keypair is the bridge.

**Use case:** Multi-tenant, multi-region deployments. An agent working across organizational boundaries can prove its identity to each broker independently.

### 7. Delegated Proof (Cryptographic Authority Chain)

When Agent A delegates to Agent B, the delegation record is signed by A's private key — not just the broker's:

```python
delegation_record = {
    "delegator": agent_a.agent_id,
    "delegate": agent_b.agent_id,
    "scope": ["read:data:partition-7"],
    "timestamp": "2026-04-09T10:00:00Z",
    "delegator_signature": agent_a.sign(record),  # A's private key
    "broker_signature": "...",                      # Broker's key (existing)
}
```

Today, only the broker signs delegation records. With agent signatures, the chain is **doubly attested** — the broker confirms it happened, and the delegator confirms it intended to delegate. Agent B can verify both signatures independently.

**Use case:** High-assurance delegation where you need proof that Agent A voluntarily authorized Agent B — not just that the broker processed a request. Important for compliance and forensic analysis.

## Implementation Priority

| Feature | Broker Change | SDK Change | Value |
|---------|--------------|------------|-------|
| Agent-to-Agent Mutual Auth | HTTP expose existing Go code | Add `agent.verify_peer()` | High — enables secure multi-agent pipelines |
| Signed Actions | New audit field for agent signatures | Add `agent.sign()` method | High — non-repudiable audit for regulated industries |
| Key Persistence | Recognize returning public keys | Add `key_path` parameter | Medium — enables long-lived agents |
| Request Signing | Verify request signatures in middleware | Sign outgoing requests | Medium — defense-in-depth against token theft |
| Agent-to-Service Auth | New endpoint: GET /v1/agents/{id}/pubkey | Client-side challenge-response | Medium — extends trust beyond the broker |
| Cross-Broker Federation | New federation endpoint | Cross-broker registration | Low (future) — multi-tenant deployments |
| Delegated Proof | Add agent signature field to DelegRecord | Sign delegation requests | Low (future) — high-assurance compliance |

## Long-Term Agent Identity

Today, agent keys are ephemeral — generated in memory, lost when the process ends. But the registration ceremony already supports a persistent model. If the app saves the agent's private key at registration time, that agent gains a **long-term cryptographic identity**.

### How It Works

```python
# First registration — app persists the keypair
agent = app.create_agent(
    orch_id="data-pipeline",
    task_id="ingestion-worker",
    requested_scope=["read:data:*"],
    key_store="vault://agents/ingestion-worker",  # or file path, KMS, etc.
)
# Private key saved to key_store. Public key stored by broker.

# Days later — agent re-registers with the SAME key
agent = app.create_agent(
    orch_id="data-pipeline",
    task_id="ingestion-worker",
    requested_scope=["read:data:*"],
    key_store="vault://agents/ingestion-worker",  # Loads existing key
)
# Broker sees same public key → same SPIFFE identity → continuity
```

### What This Enables

**1. Identity without the broker.**
The agent's identity is its keypair, not its JWT or SPIFFE ID. Those are derived from the key. If a service has the agent's public key (fetched from the broker once, or distributed out-of-band), it can verify the agent's identity **without the broker being online**. The broker is the registry, not the gatekeeper.

**2. Any system that supports Ed25519 verification can authenticate the agent.**
Not just the broker. Not just other agents. Any service, any protocol, any infrastructure that can verify an Ed25519 signature. The agent presents its public key, signs a challenge, and the verifier checks. This is the same primitive as:
- SSH host key verification
- mTLS client certificates
- SPIFFE SVIDs (X.509 or JWT)
- WebAuthn/FIDO2 passkeys

The agent's keypair is a universal identity credential. The broker is one consumer of that credential — not the only one.

**3. Key storage is pluggable.**
The app decides where to store the private key:
- **In memory** (current behavior) — ephemeral agents, single-use tasks
- **On disk** (like `~/.ssh/id_ed25519`) — long-lived agents on a single machine
- **In a secrets manager** (Vault, AWS KMS, GCP KMS) — managed agents in cloud deployments
- **In a hardware security module** (HSM, YubiKey) — highest-assurance agents where the key never leaves hardware

The broker doesn't care where the key lives. It only ever sees the public key.

**4. The agent can remove the broker from the authentication path.**
For peer-to-peer scenarios, the agent's public key is the trust anchor:

```
Agent A                                     Agent B
   |                                           |
   |-- "I am spiffe://...worker-1, here's     |
   |    my pubkey, challenge me" ------------->|
   |                                           |
   |<-- nonce --------------------------------|
   |-- sign(nonce, private_key) -------------->|
   |                                           |
   |   B already has A's pubkey               |
   |   (fetched from broker at setup,          |
   |    or distributed via config)             |
   |                                           |
   |   verify(signature, stored_pubkey)        |
   |<-- authenticated -------------------------|
```

No broker call at authentication time. The broker was involved once — at registration — to bind the public key to the SPIFFE identity. After that, the key speaks for itself.

### Ephemeral vs Long-Term: Developer's Choice

| Mode | Key Lifecycle | Use Case |
|------|--------------|----------|
| **Ephemeral** (default) | Generated per `create_agent()`, lives in memory, dies on release | Single-use tasks, LLM tool calls, batch jobs |
| **Persistent** (opt-in) | Generated once, saved to key_store, reused across registrations | Monitoring agents, scheduled workers, always-on services |
| **Hardware-bound** (future) | Key generated in HSM, never exportable | High-security agents in regulated environments |

The same registration ceremony supports all three. The only difference is where the private key lives and how long it lives there.

## Design Principle

The agent's Ed25519 keypair is the **root of agent identity**. The JWT is a time-bounded authorization derived from that identity. The SPIFFE ID is a human-readable name for that identity. But the keypair is the cryptographic truth.

Everything else — tokens, scopes, delegation chains, audit records — is built on top of that keypair. The more we use it, the stronger the security story becomes. The key is already there. We just need to use it.

The broker is the **registry and authority** — it binds public keys to identities, issues scoped tokens, and enforces policy. But the agent's identity exists independently of the broker, in the same way that an SSH key exists independently of the `authorized_keys` file. The broker tells the world *what the agent can do*. The keypair tells the world *who the agent is*.

## The Bigger Picture: PKI for the Agentic Web

Everything above describes what a single agent can do with its keypair. But the real power emerges when agent public keys become **discoverable and verifiable by anyone**.

### The known_agents File

SSH has `~/.ssh/known_hosts`. Servers have `~/.ssh/authorized_keys`. The agent equivalent:

```
# ~/.agentwrit/known_agents
# SPIFFE ID                                                          Algorithm  Public Key
spiffe://agentwrit.local/agent/pipeline/ingestion/abc123             ed25519    AAAAC3NzaC1lZDI1NTE5AAAAI...
spiffe://agentwrit.local/agent/monitor/watchdog/def456               ed25519    AAAAC3NzaC1lZDI1NTE5AAAAI...
spiffe://acme-corp.agentwrit.io/agent/billing/processor/ghi789      ed25519    AAAAC3NzaC1lZDI1NTE5AAAAI...
```

Any server, service, or infrastructure component that keeps a `known_agents` file can verify an agent's identity without calling a broker. The agent shows up, presents its SPIFFE ID, signs a challenge — the server checks the signature against the stored public key. Trusted or not, instantly.

This is the same trust model as SSH, just applied to AI agents instead of machines.

### Public Key Discovery

Today the broker stores agent public keys in its internal database. To make them discoverable:

**Option 1: Broker API endpoint**
```
GET /v1/agents/{spiffe_id}/pubkey
→ {"spiffe_id": "spiffe://...", "public_key": "base64...", "registered_at": "..."}
```

Any service can fetch an agent's public key from the broker that registered it. Fetch once, cache locally, verify forever — same as fetching an SSL certificate.

**Option 2: Well-known URL (like OIDC discovery)**
```
GET https://agentwrit.acme-corp.com/.well-known/agent-keys
→ {
    "issuer": "https://agentwrit.acme-corp.com",
    "agents": [
        {"spiffe_id": "spiffe://...", "public_key": "base64...", "scope_ceiling": [...], "status": "active"},
        ...
    ]
  }
```

Organizations publish their agents' public keys at a well-known URL. Partners, vendors, and services can discover and trust those agents automatically. Same pattern as OIDC `/.well-known/openid-configuration` or JWKS endpoints.

**Option 3: Distributed key registry**
Publish agent public keys to a shared, auditable registry — like Certificate Transparency logs for SSL certs. Anyone can verify that an agent's key was legitimately registered and hasn't been tampered with.

### What This Looks Like in Practice

**Scenario: Company A's agent accesses Company B's API**

```
Company A                     Public Registry              Company B
(broker + agents)             (or B's broker)              (API server)
     |                              |                           |
     | 1. Register agent            |                           |
     |    with keypair              |                           |
     |                              |                           |
     | 2. Publish pubkey ---------> |                           |
     |                              |                           |
     |                              | <-- 3. B fetches A's      |
     |                              |       agent pubkeys       |
     |                              |                           |
     | 4. Agent calls B's API ---------------------------->     |
     |    "I am spiffe://a/agent/X"                             |
     |    + signed request                                      |
     |                              |                           |
     |                              |    5. B verifies sig      |
     |                              |       against cached key  |
     |                              |                           |
     | <----------------------------------------- 6. Authorized |
```

No shared secrets between companies. No OAuth dance. No API key exchange. Company B trusts Company A's agent because:
- The agent's public key was published by Company A's broker
- The agent proved it holds the corresponding private key
- The SPIFFE ID tells B exactly which agent it's talking to and what organization it belongs to

**Scenario: Agent accesses a Linux server (like SSH)**

```bash
# On the server — agent's public key in authorized format
$ cat /etc/agentwrit/authorized_agents
spiffe://acme.agentwrit.io/agent/deploy/releaser/x1  ed25519  AAAAC3Nz...

# Agent connects, presents SPIFFE ID, signs challenge
# Server verifies against authorized_agents file
# Agent gets a shell / runs a command / accesses a resource
```

Same flow as `ssh deploy@server` — but the identity is an AI agent, not a human. The server doesn't need to know about the broker. It just needs the public key.

**Scenario: Agent proves identity to another agent (peer-to-peer)**

```
Agent A (data-collector)              Agent B (data-processor)
     |                                      |
     |-- "Process this batch,               |
     |    here's my SPIFFE ID,              |
     |    verify me" ---------------------->|
     |                                      |
     |<-- challenge nonce -----------------|
     |-- sign(nonce, A's private key) ----->|
     |                                      |
     |   B checks A's pubkey from           |
     |   known_agents or broker cache       |
     |   verify(sig, A's pubkey) ✓          |
     |                                      |
     |<-- "Verified. Processing batch." ----|
```

No broker involved at verification time. B already has A's public key (fetched once from the broker, or from a shared `known_agents` file, or from a well-known URL). The agents authenticate peer-to-peer.

### The Trust Hierarchy with Public Keys

```
Broker (Certificate Authority)
  │  registers apps, mints agent identities, stores public keys
  │  publishes keys via API / well-known URL / registry
  │
  ├── App A
  │     ├── Agent 1 (keypair) ──── proves identity to services, other agents, servers
  │     ├── Agent 2 (keypair) ──── proves identity to services, other agents, servers
  │     └── Agent 3 (keypair) ──── proves identity to services, other agents, servers
  │
  ├── App B
  │     ├── Agent 4 (keypair)
  │     └── Agent 5 (keypair)
  │
  └── Public Key Registry
        ├── known_agents files (SSH-style, on servers)
        ├── well-known URL (OIDC-style, for web services)
        └── distributed log (CT-style, for audit)
```

The broker is the root of trust. But once a public key is published, the agent's identity is **portable**. Any system that holds the public key can verify the agent. The broker mints identities. The keys carry them everywhere.

### Why This Matters for AI

Every AI security framework — NIST IR 8596, OWASP Agentic AI, IETF WIMSE, the draft `aiagent-auth` RFC — identifies the same gap: **AI agents lack verifiable identity**. They inherit user tokens, share API keys, or get no identity at all.

The current solutions:
- **API keys** — static, shared, no identity, no expiry, no audit
- **OAuth tokens** — designed for humans, no agent-specific claims, no delegation chains
- **UUID-based identity** (like substrates-ai/agentauth) — proves "I'm the same agent as before" but nothing else. No scope, no lifecycle, no revocation, no cryptographic proof.

What a keypair-based identity provides:
- **Cryptographic proof** — the agent can prove who it is to anything, anywhere
- **Independence from the issuer** — identity works without the broker being online
- **Universal verification** — any system that speaks Ed25519 can verify the agent
- **Non-repudiation** — the agent's signature on an action is proof it performed that action
- **Composability** — the same keypair works for broker auth, service auth, peer auth, request signing, and audit signing
- **Standards alignment** — Ed25519 + SPIFFE IDs + challenge-response is exactly what IETF WIMSE and SPIFFE specify for workload identity

### The Vision

Today: agents get ephemeral keypairs, used once for registration, then forgotten.

Tomorrow: agents get **persistent cryptographic identities** that they carry across sessions, services, organizations, and brokers. The broker is the certificate authority. The public key is the identity. The SPIFFE ID is the name. And any system in the world can verify "this is really that agent" — the same way any SSH server can verify "this is really that machine."

This is the **PKI for the agentic web**. Not a token service. Not an identity UUID. A full public key infrastructure purpose-built for AI agents — where every agent can prove who it is, what it's allowed to do, and who authorized it to do it.

The hard part — the registration ceremony, the keypair generation, the public key storage, the SPIFFE identities, the scope system, the delegation chains, the audit trail — is already built. What remains is making the public keys discoverable and the verification story obvious.

## Summary: What We Have vs What's Next

### Already Built (v0.3.0)
- Per-agent Ed25519 keypair generation
- Challenge-response registration ceremony
- Public key storage in broker
- SPIFFE identity binding
- Scoped JWTs signed by broker
- Delegation with chain tracking
- 4-level revocation
- Hash-chained audit trail
- Mutual auth Go code (not HTTP-exposed)

### Next: SDK Features (no broker changes)
- `key_path` / `key_store` parameter on `create_agent()` for persistent keys
- `agent.sign(payload)` method for signed actions
- `agent.verify_peer(other_agent)` for peer verification against cached keys

### Next: Broker Features
- `GET /v1/agents/{id}/pubkey` — public key discovery endpoint
- HTTP-expose mutual auth (`internal/mutauth/`)
- `/.well-known/agent-keys` — organizational key publication
- Request signature verification in middleware

### Future: Ecosystem
- `known_agents` file format specification
- Cross-broker federation protocol
- Agent key transparency log
- HSM / KMS key storage adapters
- Integration with SPIFFE/SPIRE trust domains
