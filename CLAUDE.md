# AgentWrit Python SDK

## Rules — Non-Negotiable

### Strict Type Safety
Every variable, parameter, and return type MUST have a type annotation. `mypy --strict` is enforced. No `Any` unless absolutely unavoidable and justified with a comment explaining why.

### `uv` is the Package Manager
`uv` for installs, lockfile (`uv.lock`), venv management, and running tools. No pip. No poetry. No conda.

### No Enterprise Code
Zero HITL, OIDC, cloud federation, or sidecar code in this repo. Ever. This is the open-source core SDK. Enterprise extensions live in separate repos.

### Code Comments
Comments explain what reading the code alone would NOT tell you: who calls it, why it exists, boundaries, design history. Never restate what the code does.

### Testing
- Unit tests: `uv run pytest tests/unit/` — no broker needed
- Integration tests: `uv run pytest -m integration` — requires live broker
- Acceptance tests: `tests/sdk-core/` — stories with evidence files and banners

### Gates (run after every commit)
```bash
uv run ruff check .                    # lint
uv run mypy --strict src/              # type check
uv run pytest tests/unit/              # unit tests
```

## Defaults

- **API source of truth:** [AgentWrit broker API docs](https://github.com/devonartis/agentwrit/blob/main/docs/api.md) — always verify SDK calls against it.
- **Live broker for verification:** Stand up broker via `docker compose up -d` (pulls `devonartis/agentwrit` from Docker Hub).
