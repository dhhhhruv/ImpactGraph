from fastapi.testclient import TestClient

from api.main import app

client = TestClient(app)


def _decision():
    return {
        "head_sha": "x",
        "files_changed": ["src/a.py"],
        "changed_functions": [],
        "blast_radius": [],
        "affected_tests": [
            {"file": "tests/unit/test_b.py", "name": "tests.unit.test_b.t1"},
            {"file": "tests/unit/test_a.py", "name": "tests.unit.test_a.t2"},
        ],
        "reviewers": [{"author": "alice"}, {"author": "bob"}, {"author": "carol"}],
        "risk": {"label": "high", "score": 0.8},
        "outcomes": {},
        "summary": "s",
    }


def test_preview_is_dry_run():
    r = client.post("/action/preview", json={"decision": _decision()})
    assert r.status_code == 200
    j = r.json()
    assert j["dry_run"] is True
    assert j["posted"] is False
    assert j["label"] == "dry_run_label_risk:high"
    assert j["reviewers"] == ["alice", "bob"]
    assert j["pytest_command"] == "pytest tests/unit/test_a.py tests/unit/test_b.py"
    assert "<!-- impactgraph -->" in j["pr_comment"]


def test_preview_without_tests():
    d = _decision()
    d["affected_tests"] = []
    j = client.post("/action/preview", json={"decision": d}).json()
    assert j["pytest_command"].startswith("# Finding")
