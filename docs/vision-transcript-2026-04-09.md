# Vision Transcript — 2026-04-09

Raw thinking from the session where the agent cryptographic identity vision emerged. These are Devon's insights as they happened, preserved verbatim with context. This document captures the full arc of the conversation — from docs cleanup through competitor analysis to the PKI vision.

---

## Session start: docs and scope examples

The session began on branch `docs/readme-license-cleanup`. While reviewing `docs/concepts.md`, Devon noticed a hardcoded scope example:

> "review this `action_scope = ["read:data:customer-artis"]` — is this a good example because it should be dynamic or not — how is scope handled in the demo please review and tell me"

After reviewing the demo's dynamic scope pattern (`scope_template = "read:records:{patient_id}"` resolved at runtime), Devon pushed further:

> "so why do we give bad example in the concepts.md with the hardcoded `["read:data:customer-artis"]`"

This led to rewriting the concepts.md scope examples with dynamic f-string patterns. Devon then asked for multiple scope examples:

> "i did not want you to change — wanted multiple examples"

And asked about scope mutability:

> "can a scope be added to an already created agent"

When told no (by design, authority only narrows), Devon challenged:

> "why not — no not if you add_scope and it calls the broker — if the broker can renew it should be able to add — please look at the broker API and see if it is possible and add a TECH_DEBT so that we can add the feature later"

Then corrected the framing:

> "No it's not a debt it is a request — but let's add it as a possible feature request but you need to keep it here not in the broker because if we update the broker the broker directory here will be deleted"

This is important — Devon thinks about where artifacts survive. The feature request went to `broker/BACKLOG.md` in the SDK repo, not the broker repo, because the vendored broker directory gets replaced on re-vendor.

## Competitor discovery

Devon asked to compare against `substrates-ai/agentauth`:

> "review our agentauth vs this agentauth — find out what does it do comparable vs mine"

After the comparison revealed a fundamentally different product (UUID identity vs full credential broker), Devon's immediate reaction was about security:

> "what is the real benefit of it — who cares about identity if the agent goes rogue — what is the security implication of not having a UUID"

And then the practical concern:

> "easy everyone solving just identity now — so since it is not competitive should I be trying to trademark because the name is a problem since people are trying to use it — I built a strong infra"

## The name decision

Devon explored trademark options but quickly moved to practical action:

> "should I change the name — let's think of new names that is catchy and I will buy the domain — I would still release agentauth as is but change the name later"

Requirements evolved through the conversation:
- "it really should have agent in it"
- "or it can have .io — is that what AI companies are using"
- "would rather have .com"
- "we can come up with one word like Okta but I wanted agent in the name though"
- "let's try both ways — maybe without agent in the name — maybe knowing what it does you can try multiple ideas"
- "let's try authagent"
- "authagent.com is registered — where are you checking" (caught unreliable whois)
- "who are you telling to check — you should be checking first before I go check"

After DNS-based checks revealed `agentwrit.com` available across .com, .io, and .ai:

> Devon purchased `agentwrit.com` on Cloudflare Registrar.

Then asked to verify WHOIS privacy was enabled.

Devon explicitly defined the rename path:

> "or can I still leave the code in place until later"

Leading to the 3-step plan: brand now, package rename at PyPI publish, protocol never.

## Demo2: support ticket app

Devon provided a screenshot of the target UI and specified the use case:

> "Identity Resolution: The system extracts the user's name from the ticket to verify their identity and locks the AI agent into accessing only that specific customer's data... Triage... Routing... Knowledge Retrieval... Response & Resolution: A response agent drafts a reply and dynamically requests specific tool permissions from a broker"

When brainstorming skill was invoked for design:

> "why is this a new feature" — it's not a new feature, it's a second demo using the existing SDK.

On stack choice:

> "I was thinking one of these two: Flask + HTMX or Pure static HTML + HTMX — the quickest one with the best SSE streaming"

> "why the same one" — when FastAPI + Jinja2 was proposed (same as demo1), Devon pushed for Flask to differentiate.

On environment:

> "let's use the same environment we have from demo so we can test it"

On app registration:

> "because the app needs to be unique" — confirming demo2 needs its own `client_id`/`client_secret` with its own scope ceiling.

On branching:

> "why you checkout main when we have not merged to main"
> "we never do anything on main — do it from this branch"

On broker startup:

> "yes let's try orbstack instead" — when Docker wasn't initially available.

> "Remember the pipeline would use a LLM" — making sure all three agents call the LLM, not just process data deterministically.

## The cryptographic identity breakthrough

Devon asked to review the broker's key model:

> "review the broker code and docs to figure out the private key challenge — is it the app private key or each agent gets its own when it registers"

> "I said read the broker code and docs" — when the answer was given from SDK code instead of broker source.

> "you could have easily reviewed what is registered by the SDK" — pointing out the answer was already in the orchestrator code read earlier. Overcomplicated with a subagent.

Then the pivotal question:

> "so this is cool but why does the agent need to prove himself when the agent never touches the broker — it's always the app — is the app sending the agent private key to the broker"

This question cracked open the entire vision. The agent's private key never leaves the SDK. The app acts as proxy. But the ceremony was designed for agents to authenticate themselves directly.

Then:

> "so this is cool so the reality is if we wanted to we can have the agent to talk to a broker or some other thing if we wanted to create a long term agent and it needed to prove who it is — kind of like SSH machines proving who they are"

Devon connected:
- Long-lived agents (not just ephemeral per-task)
- Keypair persistence (save the key, reuse it)
- SSH trust model (known_hosts)
- Agent identity independent of the broker

Then the implementation insight:

> "right now it works in memory but we can easily add a setting/parameter to choose what type of agent you need"

Ephemeral vs persistent is a parameter, not an architecture change.

Then the full vision:

> "it's like everyone talking about identity but why not give an agent a public key with SPIFFE ID — now if an agent needs to access your machine it will present the same way as SSH and you would have known_hosts file on Linux — just think of how many places — and we can store an agent public key public so anyone can actually determine is this really that agent"

This is the PKI-for-agents insight. Not tokens. Not UUIDs. Public keys — discoverable, verifiable, universal.

Scale realization:

> "WOW I THINK THIS IS BIGGER THAN I THOUGHT"

> "Well this is so big it scares me..."

Then the long-term identity extension:

> "this would be at agent registration — we can use this for long term and save the private key with the app or to some private-public key — and then the agent would have long term identity for people who want long term — and now the agent can prove who it is like we always have proven — that can actually remove the broker or we can add other things that supports the private-public key presentation"

Devon saw that:
1. The keypair can be saved at registration time
2. The agent gains long-term identity
3. The agent can prove itself without the broker being involved
4. The broker becomes a registry/CA, not a gatekeeper
5. Other modules/services can be built that consume the public key

And finally, making sure nothing is lost:

> "Please write all of this up because I will forget"

> "this should be a separate doc transcript"

> "as much as you can get"

## Key decisions made this session

1. **Scope examples fixed** — `docs/concepts.md` rewritten with dynamic scopes + multi-scope examples
2. **Scope update feature request** — added to `broker/BACKLOG.md` (survives re-vendor)
3. **Rebrand to AgentWrit** — `agentwrit.com` purchased, 3-step rename plan documented
4. **Demo2 built** — Flask + HTMX + SSE support ticket demo, registered with broker, running on port 5001
5. **Agent cryptographic identity doc** — `docs/concepts-agent-cryptographic-identity.md` — the full PKI vision
6. **This transcript** — preserving the thinking that led to the vision

## Artifacts produced

| File | What |
|------|------|
| `docs/concepts.md` | Fixed scope examples (dynamic, multi-scope) |
| `broker/BACKLOG.md` | Scope update feature request |
| `MEMORY.md` | AgentWrit rebrand plan |
| `demo2/` | Full Flask + HTMX support ticket demo (9 files) |
| `docs/concepts-agent-cryptographic-identity.md` | Agent PKI vision doc |
| `docs/vision-transcript-2026-04-09.md` | This file |
| `pyproject.toml` | Added Flask dependency |


While reviewing how the SDK's `create_agent()` works, Devon asked:

> "review the broker code and docs to figure out the private key challenge — is it the app private key or each agent gets its own when it registers"

After confirming each agent generates its own Ed25519 keypair at registration:

> "so this is cool but why does the agent need to prove himself when the agent never touches the broker — it's always the app. Is the app sending the agent private key to the broker?"

This question exposed the key realization: the app acts as proxy for the agent today (Path B), but the broker's ceremony was designed to support agents authenticating themselves directly (Path A). The protocol is identity-agnostic about who holds the private key.

## The SSH connection

> "so this is cool so the reality is if we wanted to we can have the agent to talk to a broker or some other thing if we wanted to create a long term agent and it needed to prove who it is — kind of like SSH machines proving who they are"

Devon connected three things in one thought:
1. Long-lived agents (not just ephemeral per-task)
2. Keypair persistence (store the key, reuse it)
3. The SSH trust model (machine proves identity via keypair, server checks known_hosts)

This is the foundation of the entire vision — AI agents proving identity the same way machines have since the 1990s.

## The parameter insight

> "right now it works in memory but we can easily add a setting/parameter to choose what type of agent you need"

Devon immediately saw that ephemeral vs persistent isn't an architecture change — it's a parameter on `create_agent()`. The orchestrator already accepts `private_key` as an optional argument. The plumbing exists. You just need a loader.

## The public key insight

> "it's like everyone talking about identity but why not give an agent a public key with SPIFFE ID — now if an agent needs to access your machine it will present the same way as SSH and you would have known_hosts file on Linux — just think of how many places — and we can store an agent public key public so anyone can actually determine is this really that agent"

This is the full vision in one paragraph:

1. **Give agents real public keys** — not UUIDs, not tokens, not OAuth scopes. Ed25519 public keys, the same primitive the entire internet uses for machine identity.

2. **SPIFFE ID + public key = portable identity** — the SPIFFE ID is the name, the public key is the proof. Together they work anywhere.

3. **known_hosts for agents** — any server can maintain a list of trusted agent public keys. Agent shows up, signs a challenge, server checks the list. No broker call. No token exchange. No network dependency.

4. **Public key as public record** — store agent public keys where anyone can query them. Now any third party can verify "is this really that agent?" Same concept as SSL certificate transparency, DNS public keys, or SSH host key fingerprints.

5. **"Just think of how many places"** — this works everywhere: servers, databases, APIs, message queues, other agents, other brokers, other organizations. Anywhere that can verify an Ed25519 signature can verify an agent's identity.

## The competitive insight

Earlier in the session, Devon reviewed `substrates-ai/agentauth` — a competing project with the same name that does UUID-based agent identity. Devon's reaction:

> "what is the real benefit of it — who cares about identity if the agent goes rogue — what is the security implication of not having [scope/lifecycle/revocation]"

And after seeing the full PKI vision:

> "it's like everyone talking about identity but why not give an agent a public key"

The critique of the entire AI agent identity space: everyone is solving identity with tokens and UUIDs (proving "I am the same agent as last time") but nobody is giving agents **cryptographic identity** (proving "I am this specific entity, challenge me and verify"). The difference is the same as the difference between a name badge and an SSH key.

## The scale realization

> "WOW I THINK THIS IS BIGGER THAN I THOUGHT"

> "Well this is so big it scares me..."

Devon recognized that what started as a credential broker for AI agents is actually the foundation for a **public key infrastructure for the agentic web**. The broker is the certificate authority. The agent's keypair is the identity. The SPIFFE ID is the name. And any system in the world can verify an agent — the same way any SSH server can verify a machine.

## What already exists in the code

- `crypto.py` — `generate_keypair()` creates Ed25519 keypairs per agent
- `orchestrator.py:53` — `private_key` parameter already accepted (can pass an existing key)
- `orchestrator.py:113-114` — generates fresh key if none provided
- `orchestrator.py:117` — only public key sent to broker
- Broker `internal/store/sql_store.go` — stores agent public key in `AgentRecord`
- Broker `internal/mutauth/` — mutual agent-to-agent auth using stored public keys (Go API, not HTTP-exposed)
- Broker `internal/identity/id_svc.go:162-172` — verifies agent's Ed25519 signature at registration
- Broker `internal/keystore/keystore.go` — broker's own persistent keypair (separate from agent keys)

The infrastructure is already built. The keypair generation, the challenge-response ceremony, the public key storage, the mutual auth code. What's missing is persistence (save the key), discovery (publish the key), and verification stories (how third parties use the key).

## Key decisions made this session

1. **Rebrand to AgentWrit** — `agentwrit.com` purchased. Name collision with substrates-ai/agentauth resolved.
2. **Agent cryptographic identity is the core differentiator** — not tokens, not scopes, not audit. The keypair is the foundation everything else is built on.
3. **Concept doc written** — `docs/concepts-agent-cryptographic-identity.md` captures the technical vision with diagrams, code examples, and implementation priority.
4. **Demo2 built** — Support ticket demo (Flask + HTMX + SSE) on branch `feature/demo2-support-ticket`.
