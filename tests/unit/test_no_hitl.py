"""Verify HITL contamination is fully removed from the SDK."""

from __future__ import annotations

import importlib
import inspect
import pathlib
from typing import Final

REPO_ROOT: Final[pathlib.Path] = pathlib.Path(__file__).resolve().parent.parent.parent
SRC_DIR: Final[pathlib.Path] = REPO_ROOT / "src"
DOCS_DIR: Final[pathlib.Path] = REPO_ROOT / "docs"
README_PATH: Final[pathlib.Path] = REPO_ROOT / "README.md"


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
        assert not hasattr(
            importlib.import_module("agentauth.errors"), "HITLApprovalRequired"
        )

    def test_no_approval_token_parameter(self) -> None:
        """get_token() must not accept an approval_token parameter."""
        from agentauth.app import AgentAuthApp

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

    def test_no_hitl_strings_in_docs(self) -> None:
        """No doc file under docs/ or README.md may contain 'hitl' (case-insensitive)."""
        violations: list[str] = []
        scan_files: list[pathlib.Path] = list(DOCS_DIR.rglob("*.md")) + [README_PATH]
        for md_file in scan_files:
            if not md_file.exists():
                continue
            content: str = md_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if "hitl" in line.lower():
                    violations.append(f"{md_file.relative_to(REPO_ROOT)}:{i}")
        assert violations == [], f"HITL references found in docs: {violations}"

    def test_no_approval_strings_in_docs(self) -> None:
        """No doc file under docs/ or README.md may contain 'approval' (case-insensitive)."""
        violations: list[str] = []
        scan_files: list[pathlib.Path] = list(DOCS_DIR.rglob("*.md")) + [README_PATH]
        for md_file in scan_files:
            if not md_file.exists():
                continue
            content: str = md_file.read_text()
            for i, line in enumerate(content.splitlines(), 1):
                if "approval" in line.lower():
                    violations.append(f"{md_file.relative_to(REPO_ROOT)}:{i}")
        assert violations == [], f"Approval references found in docs: {violations}"

    def test_version_is_0_2_0(self) -> None:
        """Package version must be 0.2.0 after HITL removal."""
        from agentauth import __version__

        assert __version__ == "0.2.0"
