# ~~HITL Removal & API Alignment Implementation Plan~~

> **Status:** ~~DONE~~ — shipped in v0.2.0, merged to `main` 2026-04-01. Kept for historical reference.

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Remove all HITL contamination from the Python SDK and align with the broker API contract for v0.2.0 release.

**Architecture:** Surgical removal of one exception class, one error-parsing branch, one client parameter, and all associated tests/docs. No new features — only deletion, cleanup, and verification.

**Tech Stack:** Python 3.10+, uv, pytest, mypy --strict, ruff

**Spec:** `.plans/specs/2026-04-01-hitl-removal-api-alignment-spec.md`

---

### Task 1: Write contamination-absence tests

These tests assert HITL is gone. They fail now (RED), pass after removal (GREEN).

**Files:**
- Create: `tests/unit/test_no_hitl.py`

**Step 1: Write the failing tests**

```python
"""Verify HITL contamination is fully removed from the SDK."""

from __future__ import annotations

import ast
import importlib
import pathlib
from typing import Final

import pytest


SRC_DIR: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent.parent.parent / "src"


class TestNoHITLContamination:
    """HITL code must not exist anywhere in the open-source core SDK."""

    def test_no_hitl_in_public_exports(self) -> None:
        """HITLApprovalRequired must not be importable from agentauth."""
        import agentauth

        assert not hasattr(agentauth, "HITLApprovalRequired")

    def test_no_hitl_in_all(self) -> None:
        """__all__ must not contain HITLApprovalRequired."""
        import agentauth

        assert "HITLApprovalRequired" not in agentauth.__all__

    def test_no_hitl_class_in_errors_module(self) -> None:
        """errors.py must not define HITLApprovalRequired."""
        assert not hasattr(importlib.import_module("agentauth.errors"), "HITLApprovalRequired")

    def test_no_approval_token_parameter(self) -> None:
        """get_token() must not accept an approval_token parameter."""
        from agentauth.app import AgentAuthApp

        import inspect
        sig: inspect.Signature = inspect.signature(AgentAuthApp.get_token)
        assert "approval_token" not in sig.parameters

    def test_no_hitl_strings_in_source(self) -> None:
        """No source file under src/ may contain 'hitl' (case-insensitive)."""
        violations: list[str] = []
        for py_file in SRC_DIR.rglob("*.py"):
            content: str = py_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if "hitl" in line.lower():
                    violations.append(f"{py_file.relative_to(SRC_DIR)}:{i}")
        assert violations == [], f"HITL references found: {violations}"

    def test_no_approval_strings_in_source(self) -> None:
        """No source file under src/ may contain 'approval' (case-insensitive)."""
        violations: list[str] = []
        for py_file in SRC_DIR.rglob("*.py"):
            content: str = py_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if "approval" in line.lower():
                    violations.append(f"{py_file.relative_to(SRC_DIR)}:{i}")
        assert violations == [], f"Approval references found: {violations}"

    def test_version_is_0_2_0(self) -> None:
        """Package version must be 0.2.0 after HITL removal."""
        from agentauth import __version__

        assert __version__ == "0.2.0"
```

**Step 2: Run tests to verify they fail (RED)**

Run: `uv run pytest tests/unit/test_no_hitl.py -v`
Expected: Multiple FAIL (HITLApprovalRequired still exists, version is still 0.1.0)

**Step 3: Commit the RED tests**

```bash
git add tests/unit/test_no_hitl.py
git commit -m "$(cat <<'EOF'
test: add contamination-absence tests for HITL removal

RED phase — these tests assert HITL is fully gone from the SDK.
They fail now and will pass after the removal tasks.
EOF
)"
```

---

### Task 2: Delete HITL-only files

**Files:**
- Delete: `tests/integration/test_hitl.py`
- Delete: `tests/sdk-core/s6_hitl.py`
- Delete: `docs/hitl-implementation-guide.md`
- Delete: `examples/hitl-demo/` (entire directory — HITL demo app)

**Step 1: Delete the files**

```bash
git rm tests/integration/test_hitl.py
git rm tests/sdk-core/s6_hitl.py
git rm docs/hitl-implementation-guide.md
git rm -r examples/hitl-demo/
```

**Step 2: Run gates to confirm no breakage**

Run: `uv run pytest tests/unit/ -v`
Expected: PASS (these files were not imported by unit tests)

**Step 3: Commit**

```bash
git commit -m "$(cat <<'EOF'
chore: delete HITL test and doc files

Remove test_hitl.py (integration), s6_hitl.py (acceptance), and
hitl-implementation-guide.md. These are enterprise-layer code that
does not belong in the open-source core SDK.
EOF
)"
```

---

### Task 3: Remove HITLApprovalRequired from errors.py

**Files:**
- Modify: `src/agentauth/errors.py`

**Step 1: Remove the HITLApprovalRequired class (lines 77-97)**

Delete the entire class definition.

**Step 2: Remove the HITL format detection in parse_error_response (lines 164-168)**

Delete this block:
```python
    # HITL format takes priority -- different from RFC 7807
    if parsed_body.get("error") == "hitl_approval_required":
        approval_id: str = str(parsed_body.get("approval_id", ""))
        expires_at: str = str(parsed_body.get("expires_at", ""))
        return HITLApprovalRequired(approval_id=approval_id, expires_at=expires_at)
```

**Step 3: Clean up the module docstring**

Remove these lines from the docstring:
- `  - HITLApprovalRequired: HITL gate -- human authorization required (NIST NCCoE)`
- `  - HITL format: {"error": "hitl_approval_required", "approval_id": ..., "expires_at": ...}`

Also remove the comment on line 125:
```python
# Broker error body shapes (RFC 7807 and HITL-specific)
```
Replace with:
```python
# Broker error body shapes (RFC 7807)
```

And update the `parse_error_response` docstring to remove the HITL reference on line 139:
```python
    Checks for the HITL format first (body has "error": "hitl_approval_required"),
    then dispatches on status_code and error_code.
```
Replace with:
```python
    Dispatches on status_code and error_code from the RFC 7807 body.
```

**Step 4: Run type check**

Run: `uv run mypy --strict src/agentauth/errors.py`
Expected: PASS (no references to removed class)

**Step 5: Commit**

```bash
git add src/agentauth/errors.py
git commit -m "$(cat <<'EOF'
refactor: remove HITLApprovalRequired from error hierarchy

Delete the class, its parse_error_response branch, and all HITL
references in docstrings. The core SDK broker never sends the HITL
error format.
EOF
)"
```

---

### Task 4: Remove HITL from __init__.py and bump version

**Files:**
- Modify: `src/agentauth/__init__.py`

**Step 1: Update the module docstring**

Change line 6 from:
```python
function calls, handling key generation, token caching, renewal, retry,
and HITL (human-in-the-loop) approval flow control.
```
To:
```python
function calls, handling key generation, token caching, renewal, and retry.
```

Remove line 22:
```python
    HITLApprovalRequired    — 403: human approval needed (flow control, not failure)
```

**Step 2: Remove HITLApprovalRequired from imports**

Remove `HITLApprovalRequired,` from the import block (line 35).

**Step 3: Remove from __all__**

Remove `"HITLApprovalRequired",` from `__all__` (line 47).

**Step 4: Bump version**

Change `__version__ = "0.1.0"` to `__version__ = "0.2.0"`.

**Step 5: Run type check**

Run: `uv run mypy --strict src/agentauth/__init__.py`
Expected: PASS

**Step 6: Commit**

```bash
git add src/agentauth/__init__.py
git commit -m "$(cat <<'EOF'
refactor: remove HITLApprovalRequired export, bump to v0.2.0

Remove HITL from public API surface. Version 0.2.0 reflects the
cleaned open-source core SDK.
EOF
)"
```

---

### Task 5: Remove approval_token from client.py

**Files:**
- Modify: `src/agentauth/app.py`

**Step 1: Remove approval_token parameter from get_token signature (line 230)**

Delete: `        approval_token: str | None = None,`

**Step 2: Remove approval_token from docstring**

Delete these lines from the Args section:
```python
            approval_token: HITL approval token returned after human approval.
                Pass this on retry after catching :exc:`HITLApprovalRequired`.
```

Delete these lines from the Raises section:
```python
            HITLApprovalRequired: Scope requires human approval. Catch this,
                present ``exc.approval_id`` to the user, then retry with
                ``approval_token=<user-approved token>``.
```

**Step 3: Remove approval_token from launch payload (lines 275-276, 283-284)**

Delete the comment lines 275-276:
```python
        # specific registration attempt. If approval_token is provided
        # (from a HITL approval), it is attached here so the broker knows
```
Replace with:
```python
        # specific registration attempt.
```

Delete lines 283-284:
```python
        if approval_token is not None:
            launch_payload["approval_token"] = approval_token
```

**Step 4: Run type check**

Run: `uv run mypy --strict src/agentauth/app.py`
Expected: PASS

**Step 5: Commit**

```bash
git add src/agentauth/app.py
git commit -m "$(cat <<'EOF'
refactor: remove approval_token from get_token()

The core broker has no HITL approval flow. get_token() now takes
only agent_name, scope, task_id, and orch_id.
EOF
)"
```

---

### Task 6: Update unit tests to remove HITL references

**Files:**
- Modify: `tests/unit/test_errors.py`
- Modify: `tests/unit/test_imports.py`
- Modify: `tests/unit/test_client_get_token.py`

**Step 1: Update test_errors.py**

Remove from imports (line 11): `HITLApprovalRequired,`

Delete `test_hitl_approval_required_inherits` from `TestExceptionHierarchy` (lines 33-34).

Delete the entire `TestHITLApprovalRequired` class (lines 126-163).

Delete these test methods from `TestParseErrorResponse`:
- `test_403_hitl_returns_hitl_approval_required` (lines 227-237)
- `test_hitl_takes_priority_over_scope_violation` (lines 239-248)

**Step 2: Update test_imports.py**

Remove `HITLApprovalRequired,` from the import in `test_import_errors` (line 22).

Remove `HITLApprovalRequired,` from the `issubclass` check tuple (line 33).

**Step 3: Update test_client_get_token.py**

Remove from imports (line 20): `HITLApprovalRequired` — change to:
```python
from agentauth.errors import ScopeCeilingError
```

Delete the `HITL_403_BODY` constant (lines 58-63).

Update `TestGetTokenPassthrough` class docstring (line 226) from:
```python
    """task_id, orch_id, and approval_token are passed through correctly."""
```
To:
```python
    """task_id and orch_id are passed through correctly."""
```

Delete `test_approval_token_in_launch_tokens_body` method (lines 254-275).

Delete `test_approval_token_omitted_when_none` method (lines 277-294).

Update `TestGetTokenErrors` class docstring (line 327) from:
```python
    """Error cases: HITL 403 and scope violation 403."""
```
To:
```python
    """Error cases: scope violation 403."""
```

Delete `test_hitl_403_raises_hitl_approval_required` method (lines 329-341).

Delete `test_hitl_403_approval_id_correct` method (lines 343-360).

**Step 4: Run all unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: PASS (all tests pass, no HITL tests remain)

**Step 5: Commit**

```bash
git add tests/unit/test_errors.py tests/unit/test_imports.py tests/unit/test_client_get_token.py
git commit -m "$(cat <<'EOF'
test: remove HITL test cases from unit tests

Delete HITLApprovalRequired tests, approval_token passthrough tests,
and HITL error parsing tests. Update imports and class docstrings.
EOF
)"
```

---

### Task 7: Update conftest.py (remove HITL references from docstrings)

**Files:**
- Modify: `tests/conftest.py`

**Step 1: Clean up conftest.py docstrings**

Update the module docstring (lines 1-61) to remove all HITL references:

- Line 8: Remove `  - write:data:*  -- HITL-gated: requires human approval before token is issued`
- Line 12: Remove `  - HITL flow:   client.get_token("agent", ["write:data:*"]) → HITLApprovalRequired`
- Line 35: Change `Register the test app (read:data:* immediate, write:data:* requires HITL):` to `Register the test app:`
- Lines 43: Remove `       "hitl_scopes": ["write:data:*"]`
- Line 84: Remove `with hitl_scopes=["write:data:*"]` from `app_credentials` docstring
- Line 99: Change `Admin JWT used for audit queries and HITL approval in tests.` to `Admin JWT used for audit queries in tests.`
- Lines 125-126: Change `Used by HITL tests to call POST /v1/app/approvals/{id}/approve,` to `Used by tests that need an app-scoped JWT.`
- Line 146: Change `  - write:data:*  → raises HITLApprovalRequired (HITL-gated)` to `  - write:data:*  → issued immediately`

**Step 2: Run unit tests**

Run: `uv run pytest tests/unit/ -v`
Expected: PASS

**Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "$(cat <<'EOF'
chore: remove HITL references from test fixture docstrings
EOF
)"
```

---

### Task 8: Update user-stories.md and TEST-TEMPLATE.md

**Files:**
- Modify: `tests/sdk-core/user-stories.md`
- Modify: `tests/TEST-TEMPLATE.md` (if it exists)

**Step 1: Remove SDK-S6 HITL story from user-stories.md**

Delete the entire `### SDK-S6: HITL Approval Flow` section (lines 184-229 approximately).

Remove HITL references from surrounding text:
- Line 144: Change `On permanent 4xx errors (401, 403 except HITL), the SDK raises immediately without` to `On permanent 4xx errors (401, 403), the SDK raises immediately without`
- Lines 478, 491, 503: Remove HITL references from the mapping tables

**Step 2: Update TEST-TEMPLATE.md**

Remove HITL references:
- Line 33: Remove `    test_hitl.py          -- HITL approval flow`
- Line 90: Remove `     --hitl-scopes "write:data:*"`

**Step 3: Commit**

```bash
git add tests/sdk-core/user-stories.md tests/TEST-TEMPLATE.md
git commit -m "$(cat <<'EOF'
docs: remove SDK-S6 HITL story and HITL references from test docs
EOF
)"
```

---

### Task 9: Update README.md

**Files:**
- Modify: `README.md`

**Step 1: Remove HITL from feature list (line 28)**

Delete: `- **Human-in-the-loop** — sensitive operations require explicit human approval, cryptographically bound to the issued credential`

**Step 2: Clean Quick Start (lines 56-85)**

Remove `HITLApprovalRequired` from the import on line 58:
```python
from agentauth import AgentAuthApp
```

Delete the HITL example block (lines 77-85, the try/except HITLApprovalRequired).

Renumber steps: step 4 becomes delegation, step 5 becomes validate/revoke.

**Step 3: Remove HITLGroup from architecture diagram (line 114)**

Delete: `        HITLGroup["HITL Approvals<br/>/v1/app/approvals/*"]`
Delete: `    style HITLGroup fill:#fef9c3,stroke:#eab308`

**Step 4: Remove Human Approver from deployment topology**

Delete: `    Human["👤 Human Approver<br/><i>HITL approval UI</i>"]`
Delete: `    Human -.->|"Approve / Deny"| BrokerAPI`
Delete: `    style Human fill:#fce7f3,stroke:#ec4899,stroke-width:2px`

**Step 5: Delete entire HITL section (lines 236-270)**

Delete the `## HITL (Human-in-the-Loop) Approval` section and its sequence diagram.

**Step 6: Remove HITLApprovalRequired from error hierarchy diagram**

Delete: `    Base --> HITL["<b>HITLApprovalRequired</b><br/>HTTP 403 · Human approval needed"]`
Delete: `    style HITL fill:#f59e0b,color:#fff,stroke:#d97706,stroke-width:2px`

**Step 7: Remove HITL from Security Properties table (line 326)**

Delete the row: `| **HITL provenance** | Approving human's identity is cryptographically embedded in the JWT (`original_principal` claim). |`

**Step 8: Remove HITL guide from Documentation table (line 349)**

Delete: `| [HITL Implementation Guide](docs/hitl-implementation-guide.md) | Four patterns for building human approval workflows |`

**Step 9: Commit**

```bash
git add README.md
git commit -m "$(cat <<'EOF'
docs: remove all HITL references from README

Remove HITL feature bullet, quick start example, architecture
diagram nodes, deployment topology, sequence diagram, error
hierarchy entry, security properties row, and docs table entry.
EOF
)"
```

---

### Task 10: Fix _ChallengeResponse TypedDict

**Files:**
- Modify: `src/agentauth/app.py`

**Step 1: Add expires_in to _ChallengeResponse**

The broker returns `expires_in` in the challenge response (per api.md) but the TypedDict is missing it.

Change:
```python
class _ChallengeResponse(TypedDict):
    """GET /v1/challenge response -- 64-char hex nonce with 30s TTL."""

    nonce: str
```

To:
```python
class _ChallengeResponse(TypedDict):
    """GET /v1/challenge response -- 64-char hex nonce with 30s TTL."""

    nonce: str
    expires_in: int
```

**Step 2: Run type check**

Run: `uv run mypy --strict src/agentauth/app.py`
Expected: PASS

**Step 3: Commit**

```bash
git add src/agentauth/app.py
git commit -m "$(cat <<'EOF'
fix: add expires_in to _ChallengeResponse TypedDict

The broker returns expires_in in GET /v1/challenge but the TypedDict
was missing it. Aligns with agentauth-core/docs/api.md.
EOF
)"
```

---

### Task 11: Run GREEN tests + full gate check + contamination check

**Step 1: Run the contamination-absence tests (should now be GREEN)**

Run: `uv run pytest tests/unit/test_no_hitl.py -v`
Expected: ALL PASS

**Step 2: Run full unit test suite**

Run: `uv run pytest tests/unit/ -v`
Expected: ALL PASS

**Step 3: Run gates**

```bash
uv run ruff check .
uv run mypy --strict src/
uv run pytest tests/unit/
```
Expected: All three PASS

**Step 4: Run contamination check**

```bash
grep -ri "hitl\|approval\|oidc\|federation\|sidecar" src/ tests/
```
Expected: Zero matches in `src/`. The only matches in `tests/` should be from `test_no_hitl.py` itself (which contains the word "hitl" in assertions).

Verify `tests/` matches are only in `test_no_hitl.py`:
```bash
grep -ri "hitl\|approval" tests/ --include="*.py" | grep -v test_no_hitl.py
```
Expected: Zero matches.

**Step 5: Commit (if any final fixes were needed)**

If any fixes were required, commit them. Otherwise, this task is just verification.

---

### Task 12: Update pyproject.toml version (if needed)

**Files:**
- Modify: `pyproject.toml`

**Step 1: Check if pyproject.toml has a version field**

If `pyproject.toml` has `version = "0.1.0"`, update to `version = "0.2.0"`.

**Step 2: Run gates**

```bash
uv run ruff check .
uv run mypy --strict src/
uv run pytest tests/unit/
```
Expected: ALL PASS

**Step 3: Commit**

```bash
git add pyproject.toml
git commit -m "$(cat <<'EOF'
chore: bump pyproject.toml version to 0.2.0
EOF
)"
```

---

## Task-to-Story Mapping

| Task | Stories Covered |
|------|----------------|
| Task 1 | S4 (no HITL in SDK) |
| Task 2 | S4 (no HITL in SDK) |
| Task 3 | S4 (no HITL in SDK) |
| Task 4 | S4, S1 (no approval_token, simple get_token) |
| Task 5 | S1, S4 (get_token works without approval) |
| Task 6 | S4 (clean test fixtures) |
| Task 7-8 | S4 (no HITL in docs) |
| Task 9 | S4 (clean README) |
| Task 10 | S3 (API field alignment) |
| Task 11 | S4, S5 (full verification) |
| Task 12 | — (version alignment) |
