"""Retry and fallback-model behaviour (no network)."""

import urllib.error

import pytest

import agent.agent as ag


def http_error(code):
    return urllib.error.HTTPError("http://x", code, "err", {}, None)


@pytest.fixture(autouse=True)
def env(monkeypatch):
    monkeypatch.setenv("LLM_MODEL_FALLBACK", "model-b")
    monkeypatch.setattr(ag.time, "sleep", lambda s: None)


def test_429_skips_retries_and_uses_fallback(monkeypatch):
    seen = []

    def fake(contents, key, model):
        seen.append(model)
        if model == "model-a":
            raise http_error(429)
        return {"ok": True}

    monkeypatch.setattr(ag, "_call_model", fake)
    assert ag._call_with_retry([], "k", "model-a") == {"ok": True}
    assert seen == ["model-a", "model-b"]


def test_503_retries_primary_three_times_then_falls_back(monkeypatch):
    seen = []

    def fake(contents, key, model):
        seen.append(model)
        if model == "model-a":
            raise http_error(503)
        return {"ok": True}

    monkeypatch.setattr(ag, "_call_model", fake)
    assert ag._call_with_retry([], "k", "model-a") == {"ok": True}
    assert seen == ["model-a", "model-a", "model-a", "model-b"]


def test_429_on_both_models_raises(monkeypatch):
    monkeypatch.setattr(ag, "_call_model", lambda c, k, m: (_ for _ in ()).throw(http_error(429)))
    with pytest.raises(urllib.error.HTTPError):
        ag._call_with_retry([], "k", "model-a")
