"""Unit tests for FastAPI endpoints in api.main."""

from fastapi.testclient import TestClient
from api.main import app

client = TestClient(app)


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
    assert data["decision"]["head_sha"] == "api_test_sha"


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
