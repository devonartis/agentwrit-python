---
name: devflow-client
description: >
  Use when starting any development work on AgentAuth Python SDK — loads the
  Development Flow, checks tracker state, and tells you which step to execute next.
  Trigger on: "start dev", "what's next", "resume work", "continue",
  "where are we", "pick up where we left off", any development request.
  Adapted from agentauth-core's devflow — no council steps, Python-specific gates.
---

# AgentAuth Python SDK — Development Flow

Start here for any development work. This skill loads context and tells you
what to do next.

## Instructions

1. Read these files in order:
   - `MEMORY.md` (repo root)
   - `FLOW.md` (repo root) — if it doesn't exist or has no current step, start at Step 1
   - `.plans/tracker.jsonl` (current state of all stories and tasks) — create if missing

2. From FLOW.md + tracker, identify the current step:

| Step | What | Skill | Model | Done when |
|------|------|-------|-------|-----------|
| 1 | Brainstorm | `superpowers:brainstorming` | **opus** | Design doc in `.plans/designs/` |
| 2 | Write Spec | Follow `.plans/SPEC-TEMPLATE.md` | **opus** | Spec in `.plans/specs/` |
| 3 | Impl Plan | `superpowers:writing-plans` | **opus** | Plan in `.plans/` with tasks |
| 4 | Acceptance Tests | Write stories in `tests/sdk-core/` | **opus** | Stories with Who/What/Why/How/Expected |
| 5 | Register Tracker | Update `.plans/tracker.jsonl` | any | All stories + tasks registered |
| 6 | Code | `superpowers:executing-plans` | **sonnet** | All tasks PASS, gates green |
| 7 | Review | `superpowers:requesting-code-review` + `writing-plans` | **sonnet** / **opus** | Findings documented + fix plan written |
| 7.5 | Fix Findings | `superpowers:executing-plans` | **sonnet** | Fix plan complete, gates green |
| 8 | Live Test | `superpowers:verification-before-completion` | **sonnet** | Integration tests PASS against live broker |
| 9 | Merge | `superpowers:finishing-a-development-branch` | any | Human approved, merged to `main` |

**No council steps.** This is a client SDK — faster iteration, fewer review gates.

**Step 7:** Reviewer produces findings AND a fix plan. No ad-hoc fixes.

**Step 6 + 7.5:** Use `executing-plans` for all coding — even small fixes.

3. Announce: "Dev Flow (Python SDK): Step N — [step name]. [X/Y tasks done]. Next: [action]."

4. Invoke the relevant superpowers skill if one is listed.

## Parent Project Context

The API source of truth lives in the parent project:
- **API contract:** `~/proj/agentauth-core/docs/api.md`
- **Design doc:** `~/proj/agentauth-core/.plans/designs/2026-04-01-python-sdk-repo-design.md`
- **Strategic decisions:** `~/proj/agentauth-core/FLOW.md`

Read the API doc before writing or modifying any HTTP call in the SDK.

## Gates (run after every commit)

```bash
uv run ruff check .                    # G1: lint
uv run mypy --strict src/              # G2: type check
uv run pytest tests/unit/              # G3: unit tests
```

All three must PASS before moving to the next task.

## Contamination Check

After any HITL removal work:
```bash
grep -ri "hitl\|approval\|oidc\|federation\|sidecar" src/ tests/
```
Must return nothing.

## Live Broker Testing

Integration and acceptance tests require a running core broker:
```bash
cd ~/proj/agentauth-core
export AA_ADMIN_SECRET="live-test-secret-32bytes-long-ok"
./scripts/stack_up.sh
```

Then run SDK integration tests:
```bash
uv run pytest -m integration
```

## Rules

- Branch from `main`. Feature branches: `feature/*`, fix branches: `fix/*`.
- Plans save to `.plans/`, specs to `.plans/specs/`, designs to `.plans/designs/`.
- Update tracker when story/task status changes.
- **Run gates after each commit.** Fix failures before moving on.
- **Update `CHANGELOG.md` with every user-facing change** — same commit as the code.
- **Strict types everywhere** — no untyped variables, parameters, or returns.
- **`uv` only** — never pip, poetry, or conda.
