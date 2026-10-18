"""Unit tests for graph.client and graph.queries."""

from pathlib import Path

import pytest

from graph.client import GraphClient, QueryEvidence
from graph.queries import (
    calculate_reviewer_score,
    confirm_names,
    explain_path,
    q0_diff_to_functions,
    q1_blast_radius,
    q2a_affected_tests,
    q2b_test_proof_path,
    q3_find_reviewers,
    q4_centrality,
    q5_recent_churn,
    q_most_central,
    validate_hop_limit,
)
from graph.queries import Q_EXPLAIN_PATH, Q_REVIEWERS, Q_TEST_PATH


class MockResult:
    """Mock FalkorDB result object."""

    def __init__(self, header, result_set):
        self.header = [[h] for h in header]
        self.result_set = result_set


class MockGraphDriver:
    """Mock FalkorDB graph driver for unit testing."""

    def __init__(self, canned_responses=None):
        self.canned_responses = canned_responses or {}
        self.last_query = None
        self.last_params = None
        self.query_calls = 0
        self.ro_query_calls = 0

    def query(self, cypher, params=None):
        self.query_calls += 1
        return self._dispatch(cypher, params)

    def ro_query(self, cypher, params=None):
        self.ro_query_calls += 1
        return self._dispatch(cypher, params)

    def _dispatch(self, cypher, params=None):
        self.last_query = cypher
        self.last_params = params or {}
        # Name-existence helpers used by confirm_names
        if "RETURN f.path AS path" in cypher and self.last_params.get("path"):
            return MockResult(["path"], [[self.last_params["path"]]])
        if "RETURN f.qname AS qname LIMIT 1" in cypher and self.last_params.get("qname"):
            return MockResult(["qname"], [[self.last_params["qname"]]])
        if "RETURN t.qname AS qname LIMIT 1" in cypher and self.last_params.get("qname"):
            return MockResult(["qname"], [[self.last_params["qname"]]])
        if "RETURN a.name AS name LIMIT 1" in cypher and self.last_params.get("name"):
            return MockResult(["name"], [[self.last_params["name"]]])
        for key, res in self.canned_responses.items():
            if key in cypher:
                return res
        return MockResult([], [])


def test_hop_limit_validation():
    """Verify hop limit bounds and non-int rejection."""
    assert validate_hop_limit(3, 1, 6) == 3
    assert validate_hop_limit("4", 1, 6) == 4
    try:
        validate_hop_limit(0, 1, 6)
        assert False, "Should raise ValueError"
    except ValueError:
        pass
    try:
        validate_hop_limit(7, 1, 6)
        assert False, "Should raise ValueError"
    except ValueError:
        pass


def test_client_evidence_logging():
    """Verify GraphClient logs cypher, params, row count and latency."""
    mock_driver = MockGraphDriver({
        "Function": MockResult(["qname"], [["vorta.views.backup"]])
    })
    client = GraphClient(driver=mock_driver)
    rows, ev = client.execute_query("MATCH (f:Function) RETURN f.qname", {"param": 1})

    assert len(rows) == 1
    assert rows[0]["qname"] == "vorta.views.backup"
    assert ev.row_count == 1
    assert ev.params == {"param": 1}
    assert ev.duration_ms >= 0.0
    assert len(client.evidence_log) == 1
    assert ev.read_only is False
    assert client.write_calls == 1


def test_ro_query_increments_read_calls():
    """Read-only path must use ro_query and not count as a write."""
    mock_driver = MockGraphDriver({
        "Function": MockResult(["qname"], [["vorta.views.backup"]])
    })
    client = GraphClient(driver=mock_driver)
    rows, ev = client.ro_query("MATCH (f:Function) RETURN f.qname", {})
    assert rows[0]["qname"] == "vorta.views.backup"
    assert ev.read_only is True
    assert client.read_calls == 1
    assert client.write_calls == 0
    assert mock_driver.ro_query_calls == 1


def test_q_most_central():
    """Top PageRank functions returned as compact rows."""
    mock_driver = MockGraphDriver({
        "ORDER BY f.pagerank": MockResult(
            ["qname", "file", "score"],
            [["mod.core", "mod.py", 0.3]],
        )
    })
    client = GraphClient(driver=mock_driver)
    rows = q_most_central(client, limit=5)
    assert rows[0]["qname"] == "mod.core"
    assert rows[0]["score"] == 0.3
    assert set(rows[0]) == {"qname", "file", "score"}


def test_q_most_central_enforces_maximum_limit():
    """The centrality query must reject limits above its public maximum."""
    client = GraphClient(driver=MockGraphDriver())
    with pytest.raises(ValueError, match="between 1 and 20"):
        q_most_central(client, limit=21)


def test_confirm_names_checks_function_file_test_and_person():
    """Every tool name category is checked using read-only existence queries."""
    driver = MockGraphDriver()
    client = GraphClient(driver=driver)
    result = confirm_names(
        client,
        functions=["pkg.fn"],
        files=["pkg.py"],
        tests=["tests.test_pkg.test_fn"],
        people=["Alice"],
    )
    assert result["ok"] is True
    assert result["unknown_functions"] == []
    assert result["unknown_files"] == []
    assert result["unknown_tests"] == []
    assert result["unknown_people"] == []
    assert driver.query_calls == 0
    assert driver.ro_query_calls == 4


def test_q0_diff_to_functions():
    """Verify Q0 parameter binding and output extraction."""
    mock_driver = MockGraphDriver({
        "Function": MockResult(["qname"], [["vorta.views.backup"], ["vorta.views.restore"]])
    })
    client = GraphClient(driver=mock_driver)
    qnames = q0_diff_to_functions(client, "src/vorta/views.py", 10, 45)

    assert qnames == ["vorta.views.backup", "vorta.views.restore"]
    assert mock_driver.last_params == {"path": "src/vorta/views.py", "hunk_start": 10, "hunk_end": 45}


def test_q1_blast_radius():
    """Verify Q1 hop formatting and evidence capture."""
    mock_driver = MockGraphDriver({
        "CALLS": MockResult(
            ["affected", "via", "hops", "path"],
            [["vorta.main", "vorta.views.backup", 1, ["vorta.main", "vorta.views.backup"]]],
        )
    })
    client = GraphClient(driver=mock_driver)
    rows, ev = q1_blast_radius(client, ["vorta.views.backup"], max_hops=3)

    assert len(rows) == 1
    assert rows[0]["affected"] == "vorta.main"
    assert "CALLS*1..3" in mock_driver.last_query
    assert mock_driver.last_params == {"changed": ["vorta.views.backup"]}
    assert ev.row_count == 1


def test_q2a_and_q2b_tests():
    """Verify Q2a test collection and Q2b proof path."""
    mock_driver = MockGraphDriver({
        "p = (t:Test)": MockResult(["test", "file", "hops"], [["tests.test_backup", "tests/test_backup.py", 2]]),
        "shortestPath": MockResult(["path"], [[["tests.test_backup", "vorta.main", "vorta.views.backup"]]]),
    })
    client = GraphClient(driver=mock_driver)
    tests = q2a_affected_tests(client, ["vorta.views.backup"], max_hops=4)
    assert len(tests) == 1
    assert tests[0]["test"] == "tests.test_backup"

    path = q2b_test_proof_path(client, "tests.test_backup", "vorta.views.backup")
    assert path == ["tests.test_backup", "vorta.main", "vorta.views.backup"]
    assert "shortestPath" in mock_driver.last_query
    assert "RETURN [n IN nodes(shortestPath(" in mock_driver.last_query


def test_reviewer_scoring_and_q3():
    """Verify reviewer scoring formula and author exclusion."""
    # Last committer 180 days ago: recency = 0.5**1 = 0.5
    # Covered 1/2 files = 0.5, commits 10/10 = 1.0 -> 0.5*0.5 + 0.3*1.0 + 0.2*0.5 = 0.25 + 0.30 + 0.10 = 0.65
    now_ts = 1700000000
    ts_180d_ago = now_ts - (180 * 86400)
    score = calculate_reviewer_score(1, 2, 10, 10, ts_180d_ago, now_ts)
    assert score == 0.65

    mock_driver = MockGraphDriver({
        "Author": MockResult(
            ["author", "commits", "files_covered", "last_ts"],
            [
                ["alice", 10, 2, now_ts],
                ["pr_creator", 15, 2, now_ts],
                ["bob", 2, 1, ts_180d_ago],
            ],
        )
    })
    client = GraphClient(driver=mock_driver)
    reviewers = q3_find_reviewers(client, ["f1.py", "f2.py"], before_ts=now_ts, pr_author="pr_creator")

    assert len(reviewers) == 2
    assert "count(DISTINCT au)" in mock_driver.last_query
    assert reviewers[0]["author"] == "alice"
    assert reviewers[1]["author"] == "bob"
    assert all(r["author"] != "pr_creator" for r in reviewers)


def test_q4_centrality_and_q5_churn():
    """Verify Q4 PageRank query and Q5 churn count."""
    mock_driver = MockGraphDriver({
        "ORDER BY pagerank": MockResult(["fn", "pagerank"], [["vorta.core", 0.045]]),
        "recent_commits": MockResult(["recent_commits"], [[7]]),
    })
    client = GraphClient(driver=mock_driver)
    centrality = q4_centrality(client, ["vorta.core"])
    assert centrality[0]["pagerank"] == 0.045

    churn = q5_recent_churn(client, ["f1.py"], since_ts=1000, before_ts=2000)
    assert churn == 7


def test_all_analysis_queries_use_read_only_driver_call():
    """Every graph analysis query must call ro_query, never the write path."""
    driver = MockGraphDriver()
    client = GraphClient(driver=driver)
    q0_diff_to_functions(client, "pkg.py", 1, 5)
    q1_blast_radius(client, ["pkg.fn"])
    q2a_affected_tests(client, ["pkg.fn"])
    q2b_test_proof_path(client, "tests.test_pkg.test_fn", "pkg.fn")
    q3_find_reviewers(client, ["pkg.py"], before_ts=10)
    q4_centrality(client, ["pkg.fn"])
    q5_recent_churn(client, ["pkg.py"], since_ts=1, before_ts=10)
    q_most_central(client, limit=20)
    explain_path(client, "pkg.fn", "pkg.other")
    assert driver.ro_query_calls == 9
    assert driver.query_calls == 0


def test_read_only_query_never_falls_back_to_write_call():
    """A driver without ro_query must fail explicitly instead of writing."""
    class WriteOnlyDriver:
        def query(self, _cypher, _params=None):
            raise AssertionError("write-capable call must not run")

    client = GraphClient(driver=WriteOnlyDriver())
    with pytest.raises(AttributeError, match="read-only ro_query"):
        client.ro_query("RETURN 1")


def test_agent_and_query_docs_match_runtime_query_contract():
    """Canonical docs retain the selected algorithms, bounded limit, and aliases."""
    root = Path(__file__).resolve().parents[1]
    cypher = (root / "queries.cypher").read_text()
    agents = (root / "AGENTS.md").read_text()
    for query in (Q_TEST_PATH, Q_EXPLAIN_PATH, Q_REVIEWERS):
        fragments = [
            line.strip()
            for line in query.splitlines()
            if line.strip().startswith(("MATCH ", "WHERE ", "RETURN ", "ORDER BY"))
        ]
        assert all(fragment in cypher for fragment in fragments)
    assert "get_most_central(limit: int, max 20)" in agents
    assert "CALL algo.pageRank('Function', 'CALLS')" in cypher
    assert "LIMIT {limit}" in cypher
    assert 'Empty results mean "not modelled"' in agents
