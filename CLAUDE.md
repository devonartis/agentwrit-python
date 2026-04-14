# AgentWrit Python SDK

## Rules

**At session start, ALWAYS read these files before doing anything else:**
- `~/proj/devflow/agentwrit-python/MEMORY.md` — current state, standing rules, known issues
- `~/proj/devflow/agentwrit-python/FLOW.md` — decision log + **welcome note on first visit** (delete after reading)
- Use `devflow-client` skill for all development work

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

- **Read `~/proj/devflow/agentwrit-python/MEMORY.md` first** every session — it has current state and lessons.
- **Read `~/proj/devflow/agentwrit-python/FLOW.md`** for decision history and what's next.
- **Use `devflow-client`** skill for all development work.
- **API source of truth:** [https://github.com/devonartis/agentwrit/blob/main/docs/api.md](https://github.com/devonartis/agentwrit/blob/main/docs/api.md) — always verify SDK calls against it.
- **Live broker for verification:** Stand up broker via `docker compose up -d` (pulls `devonartis/agentwrit` from Docker Hub).
