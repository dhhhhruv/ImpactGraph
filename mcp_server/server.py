"""FastMCP server exposing ImpactGraph graph-query tools for agents."""

from __future__ import annotations

import json
import os
import time
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from graph.client import GraphClient
from graph.queries import (
    confirm_names,
    explain_path as query_explain_path,
    q0_diff_to_functions,
    q1_blast_radius,
    q2a_affected_tests,
    q2b_test_proof_path,
    q3_find_reviewers,
    q4_centrality,
    q5_recent_churn,
    q_most_central,
)
from graph.risk import calculate_risk

mcp = FastMCP("impactgraph")

OUTCOME_ANSWERED = "answered_with_path"
OUTCOME_NOT_IN_GRAPH = "not_in_graph"
OUTCOME_UNKNOWN = "unknown_name"
OUTCOME_CACHED = "cached"


def _dumps(payload: Any) -> str:
    """Compact JSON encoding for tool responses."""
    return json.dumps(payload, separators=(",", ":"))


def _get_client(repo: str) -> GraphClient:
    """Build a GraphClient for impact_<owner>_<repo>."""
    graph_name = f"impact_{repo.replace('/', '_').replace('-', '_')}"
    host = os.environ.get("FALKOR_HOST", "localhost")
    port = int(os.environ.get("FALKOR_PORT", 6379))
    return GraphClient(host=host, port=port, graph_name=graph_name)


def _unknown(kind: str, names: List[str]) -> str:
    """Compact unknown_name outcome payload."""
    return _dumps({"outcome": OUTCOME_UNKNOWN, "kind": kind, "names": names, "rows": []})


def _with_outcome(rows: Any, has_path: bool = False) -> Dict[str, Any]:
    """Attach outcome label to a tool payload."""
    if rows is None or rows == [] or rows == {}:
        return {
            "outcome": OUTCOME_NOT_IN_GRAPH,
            "message": (
                "nothing found in the graph, which may mean the call link is not modelled"
            ),
            "rows": rows if rows is not None else [],
        }
    outcome = OUTCOME_ANSWERED if has_path else OUTCOME_ANSWERED
    return {"outcome": outcome, "rows": rows}


# --- Prompt-1 style tools (compact JSON strings) ---


@mcp.tool()
def blast_radius(
    repo: str, changed_fns: list[str], max_hops: int = 3
) -> str:
    """Q1: callers of changed functions (direct and indirect)."""
    client = _get_client(repo)
    check = confirm_names(client, functions=changed_fns)
    if not check["ok"]:
        return _unknown("function", check["unknown_functions"])
    rows, _ = q1_blast_radius(client, changed_fns, max_hops=max_hops)
    return _dumps(_with_outcome(rows, has_path=bool(rows)))


@mcp.tool()
def affected_tests(
    repo: str, changed_fns: list[str], max_hops: int = 4
) -> str:
    """Q2a: tests that reach changed functions via CALLS."""
    client = _get_client(repo)
    check = confirm_names(client, functions=changed_fns)
    if not check["ok"]:
        return _unknown("function", check["unknown_functions"])
    rows = q2a_affected_tests(client, changed_fns, max_hops=max_hops)
    return _dumps(_with_outcome(rows, has_path=bool(rows)))


@mcp.tool(name="test_proof_path")
def proof_path(repo: str, test_fn: str, changed_fn: str) -> str:
    """Q2b: shortest proof path from a test to a changed function."""
    client = _get_client(repo)
    check = confirm_names(client, functions=[changed_fn], tests=[test_fn])
    if not check["ok"]:
        unknown = check["unknown_functions"] + check.get("unknown_tests", [])
        return _unknown("function_or_test", unknown)
    path = q2b_test_proof_path(client, test_fn, changed_fn)
    return _dumps(_with_outcome(path, has_path=bool(path)))


# Public alias matching the MCP tool name (avoid pytest collecting test_*).
proof_path.__test__ = False
test_proof_path = proof_path
test_proof_path.__test__ = False


@mcp.tool()
def find_reviewers(
    repo: str,
    files: list[str],
    before_ts: int | None = None,
    pr_author: str | None = None,
) -> str:
    """Q3: rank authors on changed files before before_ts."""
    client = _get_client(repo)
    check = confirm_names(
        client, files=files, people=[pr_author] if pr_author is not None else None
    )
    if not check["ok"]:
        unknown = check["unknown_files"] + check.get("unknown_people", [])
        return _unknown("file_or_person", unknown)
    ts = before_ts if before_ts is not None else int(time.time())
    rows = q3_find_reviewers(client, files, before_ts=ts, pr_author=pr_author)
    return _dumps(_with_outcome(rows))


@mcp.tool()
def centrality(repo: str, changed_fns: list[str]) -> str:
    """Q4: PageRank scores for changed functions."""
    client = _get_client(repo)
    check = confirm_names(client, functions=changed_fns)
    if not check["ok"]:
        return _unknown("function", check["unknown_functions"])
    rows = q4_centrality(client, changed_fns)
    return _dumps(_with_outcome(rows))


@mcp.tool()
def recent_churn(
    repo: str, files: list[str], since_ts: int, before_ts: int
) -> str:
    """Q5: commit count on files between since_ts and before_ts."""
    client = _get_client(repo)
    check = confirm_names(client, files=files)
    if not check["ok"]:
        return _unknown("file", check["unknown_files"])
    count = q5_recent_churn(client, files, since_ts=since_ts, before_ts=before_ts)
    return _dumps({"outcome": OUTCOME_ANSWERED, "rows": {"recent_commits": count}})


@mcp.tool()
def get_most_central(repo: str, limit: int = 10) -> str:
    """Return top functions by stored PageRank (limit must be between 1 and 20)."""
    client = _get_client(repo)
    rows = q_most_central(client, limit=limit)
    return _dumps(_with_outcome(rows))


# --- Agent-facing tools (dict payloads used by loop / runtime prompt) ---


@mcp.tool()
def map_diff_to_functions(
    repo: str,
    diff_hunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Map changed line ranges to function qnames (Q0). Call this first."""
    client = _get_client(repo)
    changed: set[str] = set()
    known_files: set[str] = set()
    unknown_files: List[str] = []
    for h in diff_hunks:
        path = h["path"]
        check = confirm_names(client, files=[path])
        if not check["ok"]:
            unknown_files.extend(check["unknown_files"])
            continue
        known_files.add(path)
        fns = q0_diff_to_functions(
            client, path=path, hunk_start=h.get("start", 1), hunk_end=h.get("end", 999999)
        )
        changed.update(fns)
    if unknown_files:
        return {
            "outcome": OUTCOME_UNKNOWN,
            "changed_functions": sorted(changed),
            "known_files": sorted(known_files),
            "count": len(changed),
            "unknown_files": sorted(set(unknown_files)),
        }
    if not changed:
        return {
            "outcome": OUTCOME_NOT_IN_GRAPH,
            "changed_functions": [],
            "known_files": sorted(known_files),
            "count": 0,
            "message": (
                "nothing found in the graph, which may mean the call link is not modelled"
            ),
        }
    res = sorted(changed)
    return {
        "outcome": OUTCOME_ANSWERED,
        "changed_functions": res,
        "known_files": sorted(known_files),
        "count": len(res),
    }


@mcp.tool()
def get_blast_radius(
    repo: str, changed: List[str], max_hops: int = 4
) -> Dict[str, Any]:
    """Find callers of changed functions with hop distance and paths."""
    raw = json.loads(blast_radius(repo, changed, max_hops=max_hops))
    rows = raw.get("rows") or []
    return {
        "outcome": raw.get("outcome"),
        "message": raw.get("message"),
        "count": len(rows) if isinstance(rows, list) else 0,
        "top_10": rows[:10] if isinstance(rows, list) else [],
    }


@mcp.tool()
def get_affected_tests(
    repo: str, changed: List[str], max_hops: int = 6
) -> Dict[str, Any]:
    """Find tests reaching changed functions, with proof paths."""
    client = _get_client(repo)
    check = confirm_names(client, functions=changed)
    if not check["ok"]:
        return {
            "outcome": OUTCOME_UNKNOWN,
            "tests": [],
            "count": 0,
            "proof_paths": {},
            "names": check["unknown_functions"],
        }
    if not changed:
        return {
            "outcome": OUTCOME_NOT_IN_GRAPH,
            "tests": [],
            "count": 0,
            "proof_paths": {},
            "message": "No test reaches this change",
            "finding": True,
        }
    tests = q2a_affected_tests(client, changed, max_hops=max_hops)
    paths: Dict[str, List[str]] = {}
    for t in tests[:10]:
        t_name = t.get("test", "")
        for ch in changed:
            p = q2b_test_proof_path(client, t_name, ch)
            if p:
                paths[t_name] = p
                break
    if not tests:
        return {
            "outcome": OUTCOME_NOT_IN_GRAPH,
            "tests": [],
            "count": 0,
            "proof_paths": {},
            "message": "No test reaches this change",
            "finding": True,
        }
    return {
        "outcome": OUTCOME_ANSWERED,
        "count": len(tests),
        "tests": tests[:10],
        "proof_paths": paths,
    }


@mcp.tool()
def get_risk(
    repo: str,
    changed: List[str],
    files: List[str],
    before_ts: Optional[int] = None,
) -> Dict[str, Any]:
    """Objective risk score from blast, PageRank, coverage, and churn."""
    client = _get_client(repo)
    ts = before_ts if before_ts is not None else int(time.time())
    check = confirm_names(client, functions=changed, files=files)
    if not check["ok"]:
        unknown = check["unknown_functions"] + check["unknown_files"]
        return {"outcome": OUTCOME_UNKNOWN, "names": unknown}
    blast_rows, _ = q1_blast_radius(client, changed) if changed else ([], None)
    test_rows = q2a_affected_tests(client, changed) if changed else []
    cent = q4_centrality(client, changed) if changed else []
    churn = q5_recent_churn(client, files, since_ts=ts - (90 * 86400), before_ts=ts)
    max_pr = max((float(r.get("pagerank", 0.0)) for r in cent), default=0.0)
    covered = min(len(test_rows) / max(len(changed), 1), 1.0)
    risk = calculate_risk(
        blast_radius=len(blast_rows),
        max_pagerank_pct=max_pr,
        covered_ratio=covered,
        churn_norm=min(churn / 50.0, 1.0),
    )
    risk["outcome"] = OUTCOME_ANSWERED
    risk["finding"] = not test_rows
    if not test_rows:
        risk["message"] = "No test reaches this change"
    return risk


@mcp.tool()
def explain_path(repo: str, from_qname: str, to_qname: str) -> Dict[str, Any]:
    """Shortest CALLS path via Cypher shortestPath between two functions."""
    client = _get_client(repo)
    check = confirm_names(client, functions=[from_qname, to_qname])
    if not check["ok"]:
        return {
            "outcome": OUTCOME_UNKNOWN,
            "from": from_qname,
            "to": to_qname,
            "path": None,
            "names": check["unknown_functions"],
        }
    path = query_explain_path(client, from_qname, to_qname)
    if not path:
        return {
            "outcome": OUTCOME_NOT_IN_GRAPH,
            "from": from_qname,
            "to": to_qname,
            "path": None,
            "reachable": False,
            "message": (
                "nothing found in the graph, which may mean the call link is not modelled"
            ),
        }
    return {
        "outcome": OUTCOME_ANSWERED,
        "from": from_qname,
        "to": to_qname,
        "path": path,
        "reachable": True,
    }


if __name__ == "__main__":
    mcp.run(transport="stdio")
