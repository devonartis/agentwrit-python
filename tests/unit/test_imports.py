"""Verify public API exports from the agentauth package."""


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
        TokenExpiredError,
    )

    assert all(
        issubclass(e, AgentAuthError)
        for e in (
            AuthenticationError,
            BrokerUnavailableError,
            RateLimitError,
            ScopeCeilingError,
            TokenExpiredError,
        )
    )
