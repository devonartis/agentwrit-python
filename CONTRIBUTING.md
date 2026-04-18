# Contributing to AgentWrit Python

Thank you for helping improve this SDK. This document describes how we work and what we need to review a pull request with confidence.

## License

This project is released under the [MIT License](LICENSE). By contributing, you agree that your contributions are licensed under the same terms unless you clearly state otherwise in the pull request.

## What belongs in this repository

This repo is the **open-source Python SDK** for the AgentWrit broker: challenge-response registration, scoped agents, delegation, validation, and related helpers.

**Do not add** HITL flows, OIDC or cloud identity federation, or enterprise-only sidecar integrations. Those belong in separate products or extensions.

## Development setup

- Install [uv](https://docs.astral.sh/uv/).
- Clone this repository and run:

  ```bash
  uv sync --all-extras
  ```

  (`--all-extras` pulls in `dev` optional dependencies used by tests and tooling.)

- For HTTP behavior, treat [https://github.com/devonartis/agentwrit/blob/main/docs/api.md](https://github.com/devonartis/agentwrit/blob/main/docs/api.md) as the integration contract.

## You need a running AgentWrit broker

Maintainers will not merge broker-facing changes on faith. You must exercise the SDK against a **live** broker.

**Do not assume** a copy of the broker exists inside your clone of this repository. If you have a local checkout that includes a `broker/` tree, that is optional tooling; **contributors should obtain the server from the broker project** or use a deployment they already run.

1. **Run the broker from source** — Clone [github.com/devonartis/agentwrit](https://github.com/devonartis/agentwrit) and follow that repository's instructions to build and run the stack (Docker or otherwise).

2. **Or use an existing broker** you control — Point tests and demos at its base URL and register an application with a scope ceiling appropriate for the tests you run.

3. **Register a test application** — Integration tests expect an app (conventionally named `sdk-integration` in docs) with credentials you export as environment variables. Exact env names and setup hints are in [`tests/conftest.py`](tests/conftest.py).

4. **Export credentials** (example — adjust host and secrets):

   ```bash
   export AGENTWRIT_BROKER_URL=http://127.0.0.1:8080
   export AGENTWRIT_ADMIN_SECRET=<admin-secret>
   export AGENTWRIT_CLIENT_ID=<client_id>
   export AGENTWRIT_CLIENT_SECRET=<client_secret>
   ```

## Checks to run before opening a PR

From the repository root:

```bash
uv run ruff check .
uv run mypy --strict src/
uv run pytest tests/unit/
```

**If your change touches broker HTTP behavior, token lifecycle, or integration assumptions**, also run integration tests against your live broker:

```bash
uv run pytest tests/integration/ -m integration -v
```

Acceptance-style stories under `tests/sdk-core/` may also require a broker and the same env vars; see [`docs/testing-guide.md`](docs/testing-guide.md) for naming and workflow.

## Evidence we expect in your pull request

So reviewers can tell the change was actually verified:

- Paste **redacted** output or a short summary showing **ruff**, **mypy**, **unit tests**, and—when relevant—**integration** (or acceptance) runs **passing**.
- **Never** paste client secrets, admin tokens, or other credentials.
- If you cannot run integration tests (no broker, blocked network), say so **explicitly** in the PR and describe what you did verify. Maintainers may still ask for a re-run or a broker-backed check before merge.

Demo work under [`demo/`](demo/) should follow the same rule: run against a real broker and describe how you tested.

## Pull requests

- Prefer **small, focused** changes with a clear description of **what** changed and **why**.
- Link related issues when applicable.
- Include the **evidence** described above.

## Security issues

Please report security-sensitive problems through [GitHub Security Advisories](https://github.com/devonartis/agentwrit-python/security/advisories) for this repository (or the maintainer's preferred private channel if one is published elsewhere). Do not file exploitable details in public issues before they are addressed.
