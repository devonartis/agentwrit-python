"""Verify public API exports from the agentauth package."""

import pytest


def test_import_client_from_top_level():
    from agentauth import AgentAuthApp

    assert AgentAuthApp is not None


def test_version_is_string():
    from agentauth import __version__

    assert isinstance(__version__, str)
    assert len(__version__) > 0


def test_import_errors():
    from agentauth.errors import (
        AgentAuthError,
        AuthenticationError,
        BrokerUnavailableError,
        RateLimitError,
        ScopeCeilingError,
    )

    assert all(
        issubclass(e, AgentAuthError)
        for e in (
            AuthenticationError,
            BrokerUnavailableError,
            RateLimitError,
            ScopeCeilingError,
        )
    )


def test_token_expired_error_removed() -> None:
    """TokenExpiredError is removed from public API in v0.3.0 (G16)."""
    import agentauth

    assert not hasattr(agentauth, "TokenExpiredError")
    assert "TokenExpiredError" not in agentauth.__all__

    with pytest.raises(ImportError):
        from agentauth import TokenExpiredError  # noqa: F401
