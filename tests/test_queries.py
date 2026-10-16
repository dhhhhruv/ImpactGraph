"""Unit tests for graph.client and graph.queries."""


from graph.client import GraphClient, QueryEvidence
from graph.queries import (
    calculate_reviewer_score,
    q0_diff_to_functions,
    q1_blast_radius,
    q2a_affected_tests,
    q2b_test_proof_path,
    q3_find_reviewers,
    q4_centrality,
    q5_recent_churn,
    validate_hop_limit,
)


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

    def query(self, cypher, params=None):
        self.last_query = cypher
        self.last_params = params or {}
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
