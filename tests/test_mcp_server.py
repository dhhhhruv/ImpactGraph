"""Unit tests for FastMCP server tools in mcp_server/server.py."""

from unittest.mock import MagicMock, patch
from mcp_server.server import (
    map_diff_to_functions,
    get_blast_radius,
    get_affected_tests,
    find_reviewers,
    get_risk,
    explain_path,
)


def test_mcp_map_diff_to_functions():
    with patch("mcp_server.server.q0_diff_to_functions") as mock_q0:
        mock_q0.return_value = ["pkg.mod.func_a"]
        res = map_diff_to_functions(
            repo="test/repo",
            diff_hunks=[{"path": "pkg/mod.py", "start": 10, "end": 20}],
        )
        assert res["count"] == 1
        assert "pkg.mod.func_a" in res["changed_functions"]


def test_mcp_get_blast_radius():
    with patch("mcp_server.server.q1_blast_radius") as mock_q1:
        mock_q1.return_value = ([{"affected": "pkg.caller", "hops": 1, "path": ["pkg.caller", "pkg.target"]}], None)
        res = get_blast_radius(repo="test/repo", changed=["pkg.target"], max_hops=3)
        assert res["count"] == 1
        assert len(res["top_10"]) == 1


def test_mcp_get_affected_tests():
    with patch("mcp_server.server.q2a_affected_tests") as mock_q2a, \
         patch("mcp_server.server.q2b_test_proof_path") as mock_q2b:
        mock_q2a.return_value = [{"test": "tests.test_app.test_foo", "file": "tests/test_app.py", "hops": 2}]
        mock_q2b.return_value = ["tests.test_app.test_foo", "pkg.caller", "pkg.target"]
        res = get_affected_tests(repo="test/repo", changed=["pkg.target"])
        assert res["count"] == 1
        assert "tests.test_app.test_foo" in res["proof_paths"]


def test_mcp_find_reviewers():
    with patch("mcp_server.server.q3_find_reviewers") as mock_q3:
        mock_q3.return_value = [{"author": "alice", "commits": 10, "files_covered": 2, "score": 0.85}]
        res = find_reviewers(repo="test/repo", files=["pkg/mod.py"])
        assert res["count"] == 1
        assert res["top_reviewers"][0]["author"] == "alice"


def test_mcp_get_risk():
    with patch("mcp_server.server.q1_blast_radius") as mock_q1, \
         patch("mcp_server.server.q2a_affected_tests") as mock_q2a, \
         patch("mcp_server.server.q4_centrality") as mock_q4, \
         patch("mcp_server.server.q5_recent_churn") as mock_q5:
        mock_q1.return_value = ([], None)
        mock_q2a.return_value = []
        mock_q4.return_value = []
        mock_q5.return_value = 0

        res = get_risk(repo="test/repo", changed=["pkg.target"], files=["pkg/mod.py"])
        assert "score" in res
        assert "label" in res
        assert "factors" in res


def test_mcp_explain_path():
    with patch("mcp_server.server.query_explain_path") as mock_explain:
        mock_explain.return_value = ["fn_a", "fn_b"]
        res = explain_path(repo="test/repo", from_qname="fn_a", to_qname="fn_b")
        assert res["reachable"] is True
        assert res["path"] == ["fn_a", "fn_b"]
