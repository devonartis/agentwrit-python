# Test Guide -- AgentAuth Python SDK

This is the step-by-step guide for how tests are written and executed in this project. Every feature must produce tests following this process. The broker must be running in Docker -- tests against mocks are NOT acceptance tests.

Read this entire document before writing or running any test.

---

## What Is a Test in This SDK?

An acceptance test runs the SDK against a real AgentAuth broker in Docker. It exercises the actual HTTP flow: app auth, launch token creation, Ed25519 challenge-response, and token issuance. The test proves the SDK works end-to-end, not that individual functions return expected values (that's what unit tests are for).

**Two kinds of tests:**

| Type | What It Tests | Broker Required? | Framework |
|------|-------------- |-------------------|-----------|
| **Unit tests** | Individual functions, error handling, parsing, key generation | No | pytest |
| **Integration tests** | Full SDK flow against running broker | Yes (Docker) | pytest + live broker |

---

## Directory Structure

```
tests/
  unit/                   -- unit tests (no broker needed)
    test_crypto.py        -- Ed25519 keygen, nonce signing
    test_errors.py        -- exception hierarchy, error parsing
    test_token_cache.py   -- token caching and renewal logic
  integration/            -- integration tests (broker required)
    test_app_auth.py      -- app authentication flow
    test_get_token.py     -- full token acquisition flow
    test_hitl.py          -- HITL approval flow
    test_delegation.py    -- delegation flow
    test_errors.py        -- error scenarios against real broker
  <feature>/
    user-stories.md       -- acceptance criteria (written before code)
    evidence/
      README.md           -- summary table with verdicts
      story-N-<name>.md   -- one file per story with banner + output + verdict
  conftest.py             -- shared fixtures (broker URL, app credentials)
```

---

## Step 1: Write User Stories First

Before writing any code or test, write the user stories. Each story says who is doing what and why, in plain language.

```markdown
### SDK-S1: Developer Gets a Token in Three Lines

The developer initializes the SDK with their broker URL and app credentials,
then calls get_token with an agent name and scope. The SDK handles the entire
8-step flow (app auth, launch token, keygen, challenge, sign, register) and
returns a valid JWT.

**Setup:** Broker running in Docker. App registered with `read:data:*` scope ceiling.
**Code:**
```python
from agentauth import AgentAuthClient
client = AgentAuthClient(broker_url, client_id, client_secret)
token = client.get_token("my-agent", ["read:data:*"])
```
**Expected:** `token` is a valid JWT string. Decoding it shows `scope: ["read:data:*"]` and a SPIFFE-format `sub`.
```

**Personas and what they test:**
- **Developer** -- uses the SDK's public API. Tests what developers experience.
- **Security reviewer** -- verifies security properties (key ephemeral, secret not logged, scope enforced).
- **Operator** -- verifies the broker sees correct audit events from SDK operations.

---

## Step 2: Set Up the Test Environment

Before running integration tests:

1. Start the broker from the broker repo:
   ```bash
   cd /path/to/authAgent2
   export AA_ADMIN_SECRET=$(openssl rand -hex 32)
   ./scripts/stack_up.sh
   ```

2. Register a test app:
   ```bash
   ./bin/aactl app register --name sdk-test \
     --scopes "read:data:*,write:data:*" \
     --hitl-scopes "write:data:*"
   ```
   Save the `client_id` and `client_secret`.

3. Set environment variables for the SDK tests:
   ```bash
   export AGENTAUTH_BROKER_URL=http://127.0.0.1:8080
   export AGENTAUTH_CLIENT_ID=<from step 2>
   export AGENTAUTH_CLIENT_SECRET=<from step 2>
   export AGENTAUTH_ADMIN_SECRET=$AA_ADMIN_SECRET
   ```

4. Run tests:
   ```bash
   uv run pytest tests/integration/ -v
   ```

---

## Step 3: Writing Test Code

### Unit Tests (no broker)

Unit tests use pytest and test individual SDK components in isolation:

```python
# tests/unit/test_crypto.py
from agentauth.crypto import generate_keypair, sign_nonce

def test_generate_keypair_returns_32_byte_public_key():
    private_key, public_key_b64 = generate_keypair()
    import base64
    raw = base64.b64decode(public_key_b64)
    assert len(raw) == 32

def test_sign_nonce_produces_valid_signature():
    private_key, public_key_b64 = generate_keypair()
    nonce_hex = "deadbeef" * 4
    signature_b64 = sign_nonce(private_key, nonce_hex)
    assert isinstance(signature_b64, str)
    assert len(signature_b64) > 0
```

### Integration Tests (broker required)

Integration tests use a live broker and exercise the full SDK flow:

```python
# tests/integration/test_get_token.py
import os
import pytest
from agentauth import AgentAuthClient

@pytest.fixture
def client():
    return AgentAuthClient(
        broker_url=os.environ["AGENTAUTH_BROKER_URL"],
        client_id=os.environ["AGENTAUTH_CLIENT_ID"],
        client_secret=os.environ["AGENTAUTH_CLIENT_SECRET"],
    )

def test_get_token_returns_valid_jwt(client):
    token = client.get_token("test-agent", ["read:data:*"])
    assert isinstance(token, str)
    # JWT has 3 parts separated by dots
    assert len(token.split(".")) == 3

def test_scope_ceiling_exceeded_raises(client):
    with pytest.raises(ScopeCeilingError, match="exceeds.*ceiling"):
        client.get_token("test-agent", ["admin:everything:*"])
```

---

## Step 4: Recording Evidence for Acceptance Tests

For each user story, record evidence the same way as the broker repo. The banner tells the story; the output proves it.

```markdown
# SDK-S1 -- Developer Gets a Token in Three Lines

Who: The developer.

What: The developer just installed the agentauth SDK and wants to get their
first agent token. They have app credentials from their operator. They write
three lines of Python and expect a working JWT back.

Why: This is the entire value proposition of the SDK. If this doesn't work
in three lines, the SDK has failed its primary purpose. The developer would
have to write 40+ lines of Ed25519 challenge-response code manually.

How to run: Start the broker in Docker. Register a test app. Set environment
variables. Run the test script.

Expected: The SDK returns a valid JWT. The JWT contains scope, sub (SPIFFE
format), and standard claims (iss, exp, iat).

## Test Output

[paste actual pytest output or script output here]

## Verdict

PASS -- Token returned in 3 lines. JWT decodes to correct scope and SPIFFE sub.
```

---

## The Banner -- What It Must Contain

Same format as the broker repo. Every evidence file starts with a plain language banner.

| Part | What it says | Example |
|------|-------------|---------|
| **Who** | Which persona is doing this | "The developer." |
| **What** | What they're doing, in plain English | "The developer initializes the SDK and requests a token. The SDK handles 8 steps invisibly." |
| **Why** | Why this test matters -- what breaks if it fails | "If this doesn't work, the developer must write 40+ lines of crypto code manually." |
| **How to run** | Setup + commands a QA person can follow | "Start broker in Docker. Register test app. Run: uv run pytest tests/integration/test_get_token.py" |
| **Expected** | What the output should be, in plain language | "The SDK returns a valid JWT with the requested scope." |

### Banner Language Rules

**Write it like you're explaining to a manager, not an engineer.**

GOOD: "The developer tries to get a token for a scope their app isn't allowed to use. The SDK should give them a clear error message telling them exactly what their app's scope limit is."

BAD: "Test ScopeCeilingError is raised when requested_scope is not a subset of the app's scope_ceiling as returned by the broker's 403 response."

---

## Rules

1. **Broker required for integration tests.** `docker compose up` from the broker repo first. Mocks are NOT acceptance tests.
2. **Stories first.** Write user stories before writing any test code.
3. **Personas matter.** Developer tests the SDK API. Security tests security properties. Operator tests audit visibility.
4. **Banner is mandatory.** Every evidence file starts with who/what/why/how/expected in plain language.
5. **Plain language.** An executive should be able to read the evidence and understand what happened.
6. **One story at a time.** Run one, record output, write verdict, then next.
7. **Output goes in the file.** Don't copy-paste later.
8. **One file per story.** Named `story-N-<slug>.md`.
9. **Verdict is earned.** Don't write PASS before you see the output.
10. **Use `uv run pytest`.** Not `pip`, not `python -m pytest`.
