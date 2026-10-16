"""Unit tests for ingest.git_history."""

from ingest.git_history import is_bot


def test_is_bot_detection():
    """Verify bot author detection logic."""
    assert is_bot("dependabot[bot]", "dependabot@github.com") is True
    assert is_bot("renovate-bot", "renovate@bot.com") is True
    assert is_bot("codecov", "support@codecov.io") is True
    assert is_bot("Alice Smith", "alice@example.com") is False
    assert is_bot("Bob Jones", "bob@vorta.org") is False
