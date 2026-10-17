"""Unit tests for agent.loop."""

from unittest.mock import patch

from agent.loop import compute_agent_risk, map_diffs, run_impact_agent
from graph.client import GraphClient
from tests.test_queries import MockGraphDriver, MockResult


def test_agent_loop_execution():
    """Verify agent loop runs all mandatory steps and returns structured decision."""
    canned = {
        "start <=": MockResult(["qname"], [["vorta.views.backup"]]),
        "c.qname AS affected": MockResult(
            ["affected", "via", "hops", "path", "rel_count"],
            [["vorta.main", "vorta.views.backup", 1, ["vorta.main", "vorta.views.backup"], 1]],
        ),
        "t.qname AS test": MockResult(
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
    assert cached is not decision
    assert cached["outcome"] == "cached"
    assert set(cached["outcomes"].values()) == {"cached"}
    assert decision["outcome"] == "answered_with_path"


def test_agent_loop_no_functions_changed():
    """Verify loop handles changes that do not touch any functions gracefully."""
    mock_driver = MockGraphDriver({})
    client = GraphClient(driver=mock_driver)

    hunks = [{"path": "README.md", "start": 1, "end": 10}]
    decision = run_impact_agent(client, hunks, head_sha="sha_readme")

    assert decision["changed_functions"] == []
    assert decision["blast_radius"] == []
    assert decision["affected_tests"] == []
    assert decision["risk"]["score"] == 0.25
    assert decision["risk"]["factors"]["uncovered_component"] == 0.25
    assert decision["risk"]["label"] == "low"
    assert "No test reaches this change" in decision["risk"]["notes"]
    assert decision["section_notes"]["tests"].startswith("No test reaches this change")


def test_risk_without_reaching_tests_has_zero_coverage():
    risk = compute_agent_risk([], [], [], 0, changed_count=1)
    assert risk["raw_inputs"]["covered_ratio"] == 0
    assert risk["factors"]["uncovered_component"] == 0.25


def test_map_diff_skips_unknown_file_mapping_query():
    client = GraphClient(driver=MockGraphDriver())
    with patch(
        "agent.loop.confirm_names",
        side_effect=lambda _client, files=None, **_kwargs: {
            "ok": files != ["missing.py"],
            "unknown_files": ["missing.py"] if files == ["missing.py"] else [],
            "unknown_functions": [],
        },
    ), patch(
        "agent.loop.q0_diff_to_functions", return_value=["pkg.fn"]
    ) as q0:
        result = map_diffs(
            client,
            [
                {"path": "known.py", "start": 1, "end": 2},
                {"path": "missing.py", "start": 1, "end": 2},
            ],
        )
    assert result["outcome"] == "unknown_name"
    assert result["changed_functions"] == ["pkg.fn"]
    assert result["known_files"] == ["known.py"]
    q0.assert_called_once()


def test_agent_hop_depth_is_used_for_blast_and_test_queries():
    mock_driver = MockGraphDriver(
        {
            "start <=": MockResult(["qname"], [["vorta.views.backup"]]),
            "c.qname AS affected": MockResult([], []),
            "t.qname AS test": MockResult([], []),
        }
    )
    client = GraphClient(driver=mock_driver)
    decision = run_impact_agent(
        client,
        [{"path": "src/vorta/views.py", "start": 10, "end": 45}],
        head_sha="sha_depth_1",
        before_ts=1700000000,
        max_hops=1,
    )
    queries = [event.cypher for event in client.evidence_log]
    assert any("CALLS*1..1" in query for query in queries)
    assert decision["max_hops"] == 1


def test_unknown_pr_author_skips_reviewer_query():
    client = GraphClient(driver=MockGraphDriver())

    def confirm_known_file_but_unknown_author(_client, files=None, people=None, **_kwargs):
        if people:
            return {
                "ok": False,
                "unknown_functions": [],
                "unknown_files": [],
                "unknown_tests": [],
                "unknown_people": people,
            }
        return {
            "ok": True,
            "unknown_functions": [],
            "unknown_files": [],
            "unknown_tests": [],
            "unknown_people": [],
        }

    with patch("agent.loop.confirm_names", side_effect=confirm_known_file_but_unknown_author), patch(
        "agent.loop.q3_find_reviewers"
    ) as find_reviewers:
        decision = run_impact_agent(
            client,
            [{"path": "src/module.py", "start": 1, "end": 2}],
            head_sha="sha_unknown_author",
            pr_author="Unknown Author",
        )

    find_reviewers.assert_not_called()
    assert decision["outcomes"]["reviewers"] == "unknown_name"
