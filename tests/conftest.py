"""Shared test fixtures."""

import pytest


@pytest.fixture(autouse=True)
def no_llm_key(monkeypatch):
    """Keep tests offline and deterministic: no model calls unless a test opts in."""
    monkeypatch.delenv("LLM_API_KEY", raising=False)
