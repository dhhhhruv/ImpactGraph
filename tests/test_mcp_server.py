"""Unit tests for FastMCP server tools in mcp_server/server.py."""

import json
import pytest
from unittest.mock import MagicMock, patch

from graph.client import GraphClient
from mcp_server.server import (
    affected_tests,
    blast_radius,
    centrality,
    explain_path,
    find_reviewers,
    get_affected_tests,
    get_blast_radius,
    get_most_central,
    get_risk,
    map_diff_to_functions,
    recent_churn,
    proof_path,
)
from tests.test_queries import MockResult

proof_path.__test__ = False


def _ok_names(*_a, **_k):
    return {"ok": True, "unknown_functions": [], "unknown_files": []}


def test_blast_radius_json():
    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.q1_blast_radius"
    ) as mock_q1:
        mock_q1.return_value = (
            [{"affected": "mod.fn", "hops": 1, "path": ["mod.fn", "mod.target"]}],
            None,
        )
        raw = blast_radius(repo="borgbase/vorta", changed_fns=["mod.target"], max_hops=3)
        data = json.loads(raw)
        assert data["outcome"] == "answered_with_path"
        assert data["rows"][0]["affected"] == "mod.fn"


def test_affected_tests_json():
    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.q2a_affected_tests"
    ) as mock_q2:
        mock_q2.return_value = [
            {"test": "tests.t.test_a", "file": "tests/t.py", "hops": 2}
        ]
        raw = affected_tests(repo="a/b", changed_fns=["mod.target"])
        data = json.loads(raw)
        assert "test" in data["rows"][0]


def test_test_proof_path_json():
    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.q2b_test_proof_path"
    ) as mock_p:
        mock_p.return_value = ["tests.t", "mod.target"]
        raw = proof_path(repo="a/b", test_fn="tests.t", changed_fn="mod.target")
        data = json.loads(raw)
        assert data["rows"] == ["tests.t", "mod.target"]


def test_find_reviewers_json():
    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.q3_find_reviewers"
    ) as mock_q3:
        mock_q3.return_value = [{"author": "alice", "score": 0.9}]
        raw = find_reviewers(repo="a/b", files=["x.py"], before_ts=1)
        data = json.loads(raw)
        assert data["rows"][0]["author"] == "alice"


def test_centrality_json():
    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.q4_centrality"
    ) as mock_q4:
        mock_q4.return_value = [{"fn": "mod.fn", "pagerank": 0.1}]
        raw = centrality(repo="a/b", changed_fns=["mod.fn"])
        data = json.loads(raw)
        assert "pagerank" in data["rows"][0]


def test_recent_churn_json():
    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.q5_recent_churn"
    ) as mock_q5:
        mock_q5.return_value = 7
        raw = recent_churn(repo="a/b", files=["x.py"], since_ts=1, before_ts=2)
        data = json.loads(raw)
        assert data["rows"]["recent_commits"] == 7


def test_get_most_central_json():
    with patch("mcp_server.server.q_most_central") as mock_mc:
        mock_mc.return_value = [
            {"qname": "mod.core", "file": "mod.py", "score": 0.22}
        ]
        raw = get_most_central(repo="a/b", limit=5)
        data = json.loads(raw)
        assert data["rows"][0]["qname"] == "mod.core"
        mock_mc.assert_called_once()
        assert mock_mc.call_args.kwargs.get("limit") == 5 or mock_mc.call_args[0][1] == 5


def test_unknown_name_skips_query():
    with patch(
        "mcp_server.server.confirm_names",
        return_value={
            "ok": False,
            "unknown_functions": ["no.such.fn"],
            "unknown_files": [],
        },
    ), patch("mcp_server.server.q1_blast_radius") as mock_q1:
        raw = blast_radius(repo="a/b", changed_fns=["no.such.fn"])
        data = json.loads(raw)
        assert data["outcome"] == "unknown_name"
        mock_q1.assert_not_called()


def test_unknown_file_skips_diff_mapping_query():
    with patch(
        "mcp_server.server.confirm_names",
        return_value={
            "ok": False,
            "unknown_functions": [],
            "unknown_files": ["missing.py"],
        },
    ), patch("mcp_server.server.q0_diff_to_functions") as mock_q0:
        result = map_diff_to_functions(
            repo="a/b", diff_hunks=[{"path": "missing.py", "start": 1, "end": 2}]
        )
    assert result["outcome"] == "unknown_name"
    mock_q0.assert_not_called()


def test_unknown_test_skips_proof_query():
    with patch(
        "mcp_server.server.confirm_names",
        return_value={
            "ok": False,
            "unknown_functions": [],
            "unknown_files": [],
            "unknown_tests": ["tests.missing.test_case"],
        },
    ), patch("mcp_server.server.q2b_test_proof_path") as mock_path:
        data = json.loads(
            proof_path(repo="a/b", test_fn="tests.missing.test_case", changed_fn="pkg.fn")
        )
    assert data["outcome"] == "unknown_name"
    mock_path.assert_not_called()


def test_unknown_reviewer_name_skips_reviewer_query():
    with patch(
        "mcp_server.server.confirm_names",
        return_value={
            "ok": False,
            "unknown_functions": [],
            "unknown_files": [],
            "unknown_people": ["Not In Graph"],
        },
    ), patch("mcp_server.server.q3_find_reviewers") as mock_reviewers:
        data = json.loads(
            find_reviewers(
                repo="a/b", files=["pkg.py"], pr_author="Not In Graph"
            )
        )
    assert data["outcome"] == "unknown_name"
    mock_reviewers.assert_not_called()


def test_get_risk_rejects_unknown_file_before_analysis_queries():
    with patch(
        "mcp_server.server.confirm_names",
        return_value={
            "ok": False,
            "unknown_functions": [],
            "unknown_files": ["missing.py"],
        },
    ), patch("mcp_server.server.q1_blast_radius") as mock_blast, patch(
        "mcp_server.server.q5_recent_churn"
    ) as mock_churn:
        data = get_risk(repo="a/b", changed=["pkg.fn"], files=["missing.py"])
    assert data["outcome"] == "unknown_name"
    mock_blast.assert_not_called()
    mock_churn.assert_not_called()


def test_get_most_central_rejects_limit_above_twenty():
    with pytest.raises(ValueError, match="between 1 and 20"):
        get_most_central(repo="a/b", limit=21)


def test_agent_tools_still_work():
    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.q0_diff_to_functions", return_value=["pkg.mod.func_a"]
    ):
        res = map_diff_to_functions(
            repo="test/repo",
            diff_hunks=[{"path": "pkg/mod.py", "start": 10, "end": 20}],
        )
        assert res["count"] == 1
        assert res["outcome"] == "answered_with_path"

    with patch("mcp_server.server.blast_radius") as mock_br:
        mock_br.return_value = json.dumps(
            {"outcome": "answered_with_path", "rows": [{"affected": "a"}]}
        )
        res = get_blast_radius(repo="t/r", changed=["x"])
        assert res["count"] == 1

    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.q2a_affected_tests", return_value=[]
    ), patch("mcp_server.server.q2b_test_proof_path", return_value=None):
        res = get_affected_tests(repo="t/r", changed=["x"])
        assert res["message"] == "No test reaches this change"
        assert res.get("finding") is True
        assert res["outcome"] == "not_in_graph"

    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.q1_blast_radius", return_value=([], None)
    ), patch("mcp_server.server.q2a_affected_tests", return_value=[]), patch(
        "mcp_server.server.q4_centrality", return_value=[]
    ), patch("mcp_server.server.q5_recent_churn", return_value=0):
        res = get_risk(repo="t/r", changed=["x"], files=["x.py"])
        assert "score" in res
        assert res["finding"] is True
        assert res["factors"]["uncovered_component"] == 0.25

    with patch("mcp_server.server.confirm_names", side_effect=_ok_names), patch(
        "mcp_server.server.query_explain_path", return_value=["a", "b"]
    ):
        res = explain_path(repo="t/r", from_qname="a", to_qname="b")
        assert res["reachable"] is True


def test_tools_use_ro_query_not_write():
    """Fail if a query tool uses the write path (execute_query / query)."""
    mock_client = MagicMock()
    mock_client.ro_query.return_value = (
        [{"affected": "mod.fn", "hops": 1, "path": ["mod.fn"]}],
        None,
    )
    mock_client.execute_query.side_effect = AssertionError("write call forbidden")
    mock_client.write_calls = 0
    mock_client.read_calls = 0

    with patch("mcp_server.server._get_client", return_value=mock_client), patch(
        "mcp_server.server.confirm_names", side_effect=_ok_names
    ), patch(
        "mcp_server.server.q1_blast_radius",
        side_effect=lambda client, *a, **k: (
            client.ro_query("MATCH (n) RETURN n", {})[0],
            None,
        ),
    ):
        blast_radius(repo="a/b", changed_fns=["mod.target"])
        mock_client.ro_query.assert_called()
        mock_client.execute_query.assert_not_called()


def test_all_mcp_tools_are_read_only():
    """Every exposed graph tool must fail if it attempts a write-capable query."""
    class ReadOnlyDriver:
        def __init__(self):
            self.reads = 0

        def query(self, _cypher, _params=None):
            raise AssertionError("MCP analysis must never call query()")

        def ro_query(self, cypher, params=None):
            self.reads += 1
            params = params or {}
            if "RETURN f.qname AS qname LIMIT 1" in cypher:
                return MockResult(["qname"], [[params["qname"]]])
            if "RETURN f.path AS path LIMIT 1" in cypher:
                return MockResult(["path"], [[params["path"]]])
            if "RETURN t.qname AS qname LIMIT 1" in cypher:
                return MockResult(["qname"], [[params["qname"]]])
            if "RETURN a.name AS name LIMIT 1" in cypher:
                return MockResult(["name"], [[params["name"]]])
            return MockResult([], [])

    driver = ReadOnlyDriver()
    client = GraphClient(driver=driver)
    with patch("mcp_server.server._get_client", return_value=client):
        blast_radius(repo="a/b", changed_fns=["pkg.fn"])
        affected_tests(repo="a/b", changed_fns=["pkg.fn"])
        proof_path(repo="a/b", test_fn="tests.pkg.test_fn", changed_fn="pkg.fn")
        find_reviewers(repo="a/b", files=["pkg.py"])
        centrality(repo="a/b", changed_fns=["pkg.fn"])
        recent_churn(repo="a/b", files=["pkg.py"], since_ts=1, before_ts=2)
        get_most_central(repo="a/b")
        map_diff_to_functions(
            repo="a/b", diff_hunks=[{"path": "pkg.py", "start": 1, "end": 2}]
        )
        get_blast_radius(repo="a/b", changed=["pkg.fn"])
        get_affected_tests(repo="a/b", changed=["pkg.fn"])
        get_risk(repo="a/b", changed=["pkg.fn"], files=["pkg.py"])
        explain_path(repo="a/b", from_qname="pkg.fn", to_qname="pkg.other")
    assert driver.reads > 0
