"""Unit tests for FastAPI endpoints in api.main."""

import pytest
from fastapi.testclient import TestClient
from api.main import app, build_cytoscape_elements, get_graph_client
from graph.client import GraphClient
from tests.test_queries import MockGraphDriver, MockResult

client = TestClient(app)


@pytest.fixture(autouse=True)
def mock_graph_client_fallback(monkeypatch):
    try:
        real_client = get_graph_client("test/health")
        real_client.ro_query("RETURN 1 AS ping")
    except Exception:
        canned = {
            "start <=": MockResult(["qname"], [["service.fn"]]),
            "c.qname AS affected": MockResult(
                ["affected", "via", "hops", "path", "rel_count"],
                [["caller", "service.fn", 1, ["caller", "service.fn"], 1]],
            ),
            "t.qname AS test": MockResult(
                ["test", "file", "hops"],
                [["tests.test_svc", "tests/test_svc.py", 1]],
            ),
            "shortestPath": MockResult(
                ["path"], [[["tests.test_svc", "service.fn"]]]
            ),
            "Author": MockResult(
                ["author", "commits", "files_covered", "last_ts"],
                [["bob", 3, 1, 1000]],
            ),
            "ORDER BY pagerank": MockResult(
                ["fn", "pagerank"], [["service.fn", 0.1]]
            ),
            "recent_commits": MockResult(["recent_commits"], [[1]]),
            "WHERE NOT f:Test": MockResult(["qname"], [["service.fn"]]),
            "RETURN f.qname AS qname LIMIT 1": MockResult(["qname"], [["service.fn"]]),
            "RETURN f.path AS path LIMIT 1": MockResult(["path"], [["service.py"]]),
            "caller, ch.qname": MockResult(
                ["caller", "callee", "rel"], [["caller", "callee", "CALLS"]]
            ),
        }
        mock_driver = MockGraphDriver(canned)
        fake_client = GraphClient(driver=mock_driver)
        monkeypatch.setattr("api.main.get_graph_client", lambda repo: fake_client)


def test_health_endpoint():
    """Verify GET /health returns operational status."""
    resp = client.get("/health")
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "ok"
    assert "falkordb" in data


def test_repos_endpoint():
    """Verify GET /repos lists available ingested repositories."""
    resp = client.get("/repos")
    assert resp.status_code == 200
    repos = resp.json()
    assert "borgbase/vorta" in repos


def test_analyze_endpoint():
    """Verify POST /analyze executes agent loop and returns comment."""
    payload = {
        "repo": "test/fixture",
        "diff_hunks": [{"path": "service.py", "start": 1, "end": 10}],
        "head_sha": "api_test_sha",
    }
    resp = client.post("/analyze", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "decision" in data
    assert "pr_comment" in data
    assert "<!-- impactgraph -->" in data["pr_comment"]
    assert data["decision"]["head_sha"] == "api_test_sha:h4"


def test_analyze_honors_hop_depth():
    payload = {
        "repo": "test/fixture",
        "diff_hunks": [{"path": "service.py", "start": 1, "end": 10}],
        "head_sha": "api_depth_test",
        "max_hops": 1,
    }
    resp = client.post("/analyze", json=payload)
    assert resp.status_code == 200
    decision = resp.json()["decision"]
    assert decision["max_hops"] == 1
    assert "CALLS*1..1" in "\n".join(row["cypher"] for row in decision["evidence"])



def test_subgraph_endpoint():
    """Verify GET /subgraph returns Cytoscape-formatted nodes and edges."""
    resp = client.get("/subgraph?repo=test/fixture")
    assert resp.status_code == 200
    data = resp.json()
    assert "elements" in data
    assert "nodes" in data["elements"]
    assert "edges" in data["elements"]


def test_ask_endpoint():
    """Verify POST /ask queries graph facts to answer questions."""
    payload = {"repo": "test/fixture", "question": "What is the blast radius?"}
    resp = client.post("/ask", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert "answer" in data
    assert "evidence_rows" in data


def test_benchmark_endpoint():
    """Verify GET /benchmark serves results payload."""
    resp = client.get("/benchmark")
    assert resp.status_code == 200
    data = resp.json()
    assert "metrics" in data


def test_demo_endpoint():
    """Verify GET /demo/{demo_id} returns cached decision."""
    resp = client.get("/demo/1")
    assert resp.status_code == 200
    data = resp.json()
    assert "decision" in data
    assert "pr_comment" in data
    assert data["decision"]["outcome"] == "cached"
    assert set(data["decision"]["outcomes"].values()) == {"cached"}


def test_featured_demo_endpoint():
    """Verify GET /demo/featured returns featured decision."""
    resp = client.get("/demo/featured")
    assert resp.status_code == 200
    data = resp.json()
    assert data.get("featured") is True
    assert "decision" in data
    assert data["decision"]["outcome"] == "cached"


def test_featured_demo_changes_findings_at_hop_depth():
    depth_one = client.get("/demo/featured?max_hops=1").json()["decision"]
    depth_four = client.get("/demo/featured?max_hops=4").json()["decision"]
    assert len(depth_one["affected_tests"]) == 14
    # 30 is the test query's LIMIT 30 cap, so the live count is "30 or more".
    assert len(depth_four["affected_tests"]) == 30
    assert all(row["hops"] <= 1 for row in depth_one["affected_tests"])
    assert max(row["hops"] for row in depth_four["affected_tests"]) == 4
    assert set(depth_four["test_proof_paths"]) == {
        row["test"] for row in depth_four["affected_tests"]
    }
    assert all(
        len(depth_four["test_proof_paths"][row["test"]]) - 1 == row["hops"]
        for row in depth_four["affected_tests"]
    )
    assert "Same-name baseline found 0 test file(s)" in depth_four["summary"]


def test_test_proof_edges_are_highlighted_in_subgraph_elements():
    elements = build_cytoscape_elements(
        ["pkg.changed"],
        [],
        [{"test": "tests.test_pkg.test_changed", "file": "tests/test_pkg.py"}],
        {"tests.test_pkg.test_changed": ["tests.test_pkg.test_changed", "pkg.changed"]},
    )
    assert elements["edges"][0]["data"]["type"] == "evidence"
    assert {node["data"]["id"] for node in elements["nodes"]} == {
        "pkg.changed",
        "tests.test_pkg.test_changed",
    }


def test_ask_unknown_target_does_not_run_analysis_query(monkeypatch):
    class NameCheckDriver:
        def __init__(self):
            self.queries = []

        def ro_query(self, cypher, params=None):
            self.queries.append((cypher, params))
            return MockResult([], [])

        def query(self, _cypher, _params=None):
            raise AssertionError("unknown target must not run an analysis query")

    driver = NameCheckDriver()
    graph_client = GraphClient(driver=driver)
    monkeypatch.setattr("api.main.get_graph_client", lambda _repo: graph_client)
    response = client.post(
        "/ask",
        json={
            "repo": "test/fixture",
            "question": "Find callers",
            "target_function": "missing.function",
        },
    )
    assert response.status_code == 200
    assert response.json()["outcome"] == "unknown_name"
    assert len(driver.queries) == 1
    assert "RETURN f.qname AS qname LIMIT 1" in driver.queries[0][0]


def test_github_webhook_endpoint_pr_opened():
    """Verify POST /webhook/github parses PR events and queues analysis."""
    payload = {
        "action": "opened",
        "repository": {"full_name": "borgbase/vorta"},
        "pull_request": {"number": 42},
    }
    resp = client.post(
        "/webhook/github",
        json=payload,
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["status"] == "queued"
    assert data["pr_number"] == 42
    assert data["repo"] == "borgbase/vorta"


def test_github_webhook_ignored_event():
    """Verify non-PR events return ignored status."""
    resp = client.post(
        "/webhook/github",
        json={"zen": "Non-blocking ping"},
        headers={"X-GitHub-Event": "ping"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"


def test_github_webhook_ignored_action():
    """Verify PR actions like labeled/closed return ignored status."""
    payload = {
        "action": "closed",
        "repository": {"full_name": "borgbase/vorta"},
        "pull_request": {"number": 42},
    }
    resp = client.post(
        "/webhook/github",
        json=payload,
        headers={"X-GitHub-Event": "pull_request"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "ignored"
