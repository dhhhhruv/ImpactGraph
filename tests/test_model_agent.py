"""Model-agent loop tests: scripted fake model and fake ToolBox (no network, no graph)."""

import urllib.error
from types import SimpleNamespace

import pytest

import agent.agent as ag

CALLS = []


class FakeBox:
    def __init__(self, client, hunks, before_ts=None, pr_author=None):
        self.changed = ["src.a.f"]
        self.files = ["src/a.py"]
        self.blast = None
        self.tests = None
        self.risk = None
        self.reviewers = []
        self.centrality = []
        self.churn = 0
        self.test_paths = {}
        self.map_result = {"outcome": "answered_with_path"}
        self.log = []

    def call(self, name, args=None):
        args = dict(args or {})
        CALLS.append((name, args))
        self.log.append({"tool": name, "args": args, "outcome": "answered_with_path"})
        if name == "map_diff_to_functions":
            return {"outcome": "answered_with_path", "changed_functions": self.changed, "files": self.files}
        if name == "get_blast_radius":
            self.blast = [{"affected": "src.a.g", "path": ["src.a.g", "src.a.f"]}]
            return {"outcome": "answered_with_path", "rows": self.blast}
        if name == "get_affected_tests":
            self.tests = [{"test": "tests.test_a", "file": "tests/test_a.py", "hops": 1}]
            return {"outcome": "answered_with_path", "rows": self.tests}
        if name == "get_risk":
            self.risk = {"score": 0.1, "label": "low"}
            return {"outcome": "answered_with_path", "risk": self.risk}
        return {"outcome": "error", "message": "unknown tool"}


def fc(name, args=None):
    return {"candidates": [{"content": {"role": "model",
            "parts": [{"functionCall": {"name": name, "args": args or {}}}]}}]}


def txt(text):
    return {"candidates": [{"content": {"role": "model", "parts": [{"text": text}]}}]}


FULL = [fc("map_diff_to_functions"), fc("get_blast_radius", {"max_hops": 4}),
        fc("get_affected_tests", {"max_hops": 4}), fc("get_risk")]


@pytest.fixture(autouse=True)
def agent_env(monkeypatch):
    CALLS.clear()
    monkeypatch.setenv("LLM_API_KEY", "test-key")
    monkeypatch.setattr(ag, "ToolBox", FakeBox)
    monkeypatch.setattr(ag, "run_impact_agent", lambda *a, **k: {"head_sha": "fixed"})


def script(monkeypatch, responses):
    it = iter(responses)

    def fake(contents, key, model):
        r = next(it)
        if isinstance(r, Exception):
            raise r
        return r

    monkeypatch.setattr(ag, "_call_with_retry", fake)


def run(max_hops=1):
    client = SimpleNamespace(evidence_log=[])
    return ag.run_agent(client, [{"path": "src/a.py", "start": 1, "end": 9}],
                        head_sha="t", max_hops=max_hops)


def test_full_model_run(monkeypatch):
    script(monkeypatch, FULL + [txt("done")])
    d = run()
    assert d["agent_mode"] == "model"
    assert [t["tool"] for t in d["agent_trace"]] == [
        "map_diff_to_functions", "get_blast_radius", "get_affected_tests", "get_risk"]


def test_requested_hops_override_model(monkeypatch):
    script(monkeypatch, FULL + [txt("done")])
    run(max_hops=1)
    hops = [a["max_hops"] for n, a in CALLS if n in ("get_blast_radius", "get_affected_tests")]
    assert hops == [1, 1]


def test_grounded_note_is_kept(monkeypatch):
    script(monkeypatch, FULL + [txt('{"summary": "Changes src.a.f; caller src.a.g is affected."}')])
    d = run()
    assert d["agent_notes"].startswith("Changes src.a.f")


def test_ungrounded_note_is_dropped(monkeypatch):
    script(monkeypatch, FULL + [txt('{"summary": "Also breaks src.zzz.ghost."}')])
    d = run()
    assert d["agent_mode"] == "model"
    assert "agent_notes" not in d


def test_api_error_falls_back(monkeypatch):
    script(monkeypatch, [urllib.error.URLError("boom")])
    d = run()
    assert d["agent_mode"] == "fixed_pipeline"
    assert d["agent_note"].startswith("model call failed")


def test_incomplete_run_falls_back(monkeypatch):
    script(monkeypatch, [fc("map_diff_to_functions"), txt("stopping early")])
    d = run()
    assert d["agent_mode"] == "fixed_pipeline"
    assert "did not complete" in d["agent_note"]


def test_no_key_uses_fixed_pipeline(monkeypatch):
    monkeypatch.delenv("LLM_API_KEY", raising=False)
    d = run()
    assert d["agent_mode"] == "fixed_pipeline"
    assert d["agent_note"] == "no LLM_API_KEY set"
