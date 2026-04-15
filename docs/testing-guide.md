# Testing Guide

How to run the AgentWrit SDK test suite. There are two levels: unit tests (no broker) and acceptance tests (live broker required).

This guide assumes you've completed [Prerequisites](../README.md#prerequisites) — broker reachable, app credentials provisioned.

---

## Unit Tests

Unit tests run without a broker. They mock all HTTP calls.

```bash
uv run pytest tests/unit/ -v
```

These test the SDK internals: models, crypto, scope logic, transport, agent lifecycle, and app orchestration. Run them after every code change.

---

## Acceptance Tests

Acceptance tests run against a live broker. They exercise every SDK operation end-to-end and produce evidence files for audit.

### Prerequisites

1. **A running broker.** Start it with:
   ```bash
   docker compose up -d
   ```

2. **A registered test app** with scope ceiling `["read:data:*", "write:data:*"]`. Register one against your local broker using `demo/setup.py` or the broker admin API, and capture the printed `client_id` and `client_secret`.

3. **Environment variables** — set these from *your* broker before running the suite. Do not rely on any values hardcoded in the run script (they are from a prior local broker run and will not authenticate against a fresh broker):
   ```bash
   export AGENTWRIT_BROKER_URL=http://127.0.0.1:8080
   export AGENTWRIT_CLIENT_ID=<client_id from step 2>
   export AGENTWRIT_CLIENT_SECRET=<client_secret from step 2>
   ```

### Running

With env vars set from the Prerequisites step, run the suite directly with pytest:

```bash
uv run pytest tests/integration/test_acceptance_1_8.py -v -s -m integration
```

The `-s` flag is important — it shows the banners in the console.

> **Note on the file name:** `test_acceptance_1_8.py` contains all 15 stories. The name is historical — the suite grew past eight without a rename. A follow-up PR will rename it; until then, `grep "STORY 9"` finds it in the same file.

You can also use the wrapper script, which starts the broker if needed:

```bash
./tests/sdk-core/run_acceptance.sh          # broker must already be running
./tests/sdk-core/run_acceptance.sh --up     # starts the broker first
```

> **Heads-up:** the run script currently hardcodes sample `AGENTWRIT_CLIENT_ID` / `AGENTWRIT_CLIENT_SECRET` values from a prior local broker run. They will not authenticate against a fresh broker. Either export your own values before invoking the script (they take precedence) or use the direct pytest command above.

### What the Tests Cover

| Story | What it tests | SDK calls |
|-------|---------------|-----------|
| 1 | Create agent — correct identity and scope | `create_agent()` |
| 2 | Renew token — new token, same identity, old token dead | `renew()`, `validate()` |
| 3 | Release token — revoked at broker, double-release safe | `release()`, `validate()` |
| 4 | Validate live token — claims match scope, identity, task | `validate()` |
| 5 | Delegate narrow scope — attenuated token validated at broker | `delegate()`, `validate()` |
| 6 | Delegate scope not held — broker rejects with 403 | `delegate()`, `AuthorizationError` |
| 7 | Delegation chain A→B→C — scope narrows each hop, chain tracked | `delegate()`, raw HTTP hop 2 |
| 8 | Delegate all scope (no narrowing) — discovers broker behavior | `delegate()`, `validate()` |
| 9 | Scope gating — app blocks unauthorized actions | `scope_is_subset()` |
| 10 | Natural token expiry — 5s TTL, no release, broker rejects after | `create_agent(max_ttl=5)`, `validate()` |
| 11 | RFC 7807 error structure — ProblemDetail fields verified | `delegate()`, `AuthorizationError` |
| 12 | Multiple agents — isolated scopes, unique identities | `create_agent()` x3, `scope_is_subset()` |
| 13 | Renew released agent — SDK guard prevents dead agent usage | `release()`, `renew()`, `AgentWritError` |
| 14 | Garbage token — broker handles gracefully, no crash | `validate()` with fake tokens |
| 15 | Health check — broker status, version, uptime, db_connected | `health()` |

### Evidence Files

Each test saves its full output to `tests/sdk-core/evidence/storyN_name.txt`. These files contain:
- The banner (WHO/WHAT/WHY/EXPECTED)
- Every SDK response (agent_id, scope, token prefix, expires_in, claims, chain entries)
- PASS/FAIL for each check

Evidence files are committed to git as audit trail.

### Rate Limits

The broker rate limits `POST /v1/app/auth` to 10 requests per minute per client_id. The test suite handles this by:
- Using a session-scoped `client` fixture (one auth for the whole run)
- Adding a 2-second delay between tests

Story 10 (natural expiry) adds 7 seconds of wait time. Full suite runs in ~70 seconds.

> **If you hit a 429 while developing manually** (outside the test fixtures), wait 60 seconds and retry — the broker resets the limit per minute, per `client_id`.

### Adding New Stories

Follow this pattern:

```python
class TestStoryN:
    """STORY N: One sentence describing what this proves."""

    def test_descriptive_name(self, client: AgentWritApp, broker_url: str) -> None:
        banner = [
            "",
            "=" * 65,
            "ACCEPTANCE TEST: STORY N — SHORT TITLE",
            "-" * 65,
            "WHO:      Who is doing this",
            "WHAT:     What SDK operation is being tested",
            "WHY:      Why this matters",
            "EXPECTED: What the outcome should be",
            "=" * 65,
        ]
        print_banner(banner)

        output: list[str] = []
        passed = True

        # SDK calls here...
        # Capture every SDK response in output
        # Every check has both PASS and FAIL branches that set passed

        output.append("")
        output.append("═══ STORY N: PASS ═══" if passed else "═══ STORY N: FAIL ═══")
        print("\n".join(output))
        save_evidence("storyN_name", banner, output)
        assert passed, "Story N failed"
```

Rules:
- Every SDK return value goes into `output` (agent_id, scope, token prefix, expires_in, claims)
- Every `if` check has an `else: passed = False` branch — no silent skips
- No wildcard `*` scopes on agents unless testing wildcard behavior specifically
- Delegation tests must validate the `DelegatedToken` via broker, not check registration scope
- Banner prints before the test runs (4-second pause for readability)

### Running the Full Check Suite

After making changes, run everything:

```bash
uv run ruff check .                    # lint
uv run mypy --strict src/              # type check
uv run pytest tests/unit/              # unit tests
./tests/sdk-core/run_acceptance.sh     # acceptance tests (broker must be running)
```

---

## Next Steps

| Guide | What You'll Learn |
|-------|-------------------|
| [Getting Started](getting-started.md) | Install, connect, create your first agent |
| [Developer Guide](developer-guide.md) | Real patterns: delegation, scope gating, error handling |
| [API Reference](api-reference.md) | Every class, method, parameter, and exception |
| [Concepts](concepts.md) | Trust model, roles, scopes, and standards |
| [MedAssist Demo](../demo/) | See every capability in a working healthcare app |
