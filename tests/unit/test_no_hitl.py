"""Verify HITL contamination is fully removed from the SDK."""

from __future__ import annotations

import importlib
import inspect
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
        assert not hasattr(
            importlib.import_module("agentauth.errors"), "HITLApprovalRequired"
        )

    def test_no_approval_token_parameter(self) -> None:
        """get_token() must not accept an approval_token parameter."""
        from agentauth.client import AgentAuthClient

        sig: inspect.Signature = inspect.signature(AgentAuthClient.get_token)
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
