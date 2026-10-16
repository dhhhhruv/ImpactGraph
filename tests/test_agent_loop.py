"""Unit tests for agent.loop."""

from agent.loop import run_impact_agent
from graph.client import GraphClient
from tests.test_queries import MockGraphDriver, MockResult


def test_agent_loop_execution():
    """Verify agent loop runs all mandatory steps and returns structured decision."""
    canned = {
        "start <=": MockResult(["qname"], [["vorta.views.backup"]]),
        "(c:Function)-[:CALLS": MockResult(
            ["affected", "via", "hops", "path"],
            [["vorta.main", "vorta.views.backup", 1, ["vorta.main", "vorta.views.backup"]]],
        ),
        "p = (t:Test)": MockResult(
            ["test", "file", "hops"], [["tests.test_backup", "tests/test_backup.py", 2]]
        ),
        "shortestPath": MockResult(
            ["path"], [[["tests.test_backup", "vorta.main", "vorta.views.backup"]]]
        ),
        "Author": MockResult(
            ["author", "commits", "files_covered", "last_ts"],
            [["alice", 5, 1, 1700000000]],
        ),
        "ORDER BY pagerank": MockResult(["fn", "pagerank"], [["vorta.views.backup", 0.12]]),
        "recent_commits": MockResult(["recent_commits"], [[3]]),
    }

    mock_driver = MockGraphDriver(canned)
    client = GraphClient(driver=mock_driver)

    hunks = [{"path": "src/vorta/views.py", "start": 10, "end": 45}]
    decision = run_impact_agent(client, hunks, head_sha="sha_test_1", before_ts=1700000000)

    assert decision["head_sha"] == "sha_test_1"
    assert decision["changed_functions"] == ["vorta.views.backup"]
    assert len(decision["blast_radius"]) == 1
    assert len(decision["affected_tests"]) == 1
    assert "tests.test_backup" in decision["test_proof_paths"]
    assert len(decision["reviewers"]) == 1
    assert decision["risk"]["score"] > 0.0
    assert "summary" in decision
    assert "section_notes" in decision

    # Test cache retrieval
    cached = run_impact_agent(client, hunks, head_sha="sha_test_1")
    assert cached is decision


def test_agent_loop_no_functions_changed():
    """Verify loop handles changes that do not touch any functions gracefully."""
    mock_driver = MockGraphDriver({})
    client = GraphClient(driver=mock_driver)

    hunks = [{"path": "README.md", "start": 1, "end": 10}]
    decision = run_impact_agent(client, hunks, head_sha="sha_readme")

    assert decision["changed_functions"] == []
    assert decision["blast_radius"] == []
    assert decision["affected_tests"] == []
    assert decision["risk"]["score"] == 0.0
    assert decision["risk"]["label"] == "low"
