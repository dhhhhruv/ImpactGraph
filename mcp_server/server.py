"""FastMCP server exposing ImpactGraph change-impact tools for agents."""

from __future__ import annotations

import os
import time
from typing import Any, Dict, List, Optional
from mcp.server.fastmcp import FastMCP

from graph.client import GraphClient
from graph.queries import (
    explain_path as query_explain_path,
    q0_diff_to_functions,
    q1_blast_radius,
    q2a_affected_tests,
    q2b_test_proof_path,
    q3_find_reviewers,
    q4_centrality,
    q5_recent_churn,
)
from graph.risk import calculate_risk

mcp = FastMCP("impactgraph")


def _get_client(repo: str) -> GraphClient:
    """Helper to obtain a GraphClient for a given repository."""
    graph_name = f"impact_{repo.replace('/', '_').replace('-', '_')}"
    host = os.environ.get("FALKOR_HOST", "localhost")
    port = int(os.environ.get("FALKOR_PORT", 6379))
    return GraphClient(host=host, port=port, graph_name=graph_name)


@mcp.tool()
def map_diff_to_functions(
    repo: str,
    diff_hunks: List[Dict[str, Any]],
) -> Dict[str, Any]:
    """Map changed line ranges across diff hunks to defined Python function qnames (Q0).
    Always call this first before any other analysis.
    """
    client = _get_client(repo)
    changed = set()
    for h in diff_hunks:
        fns = q0_diff_to_functions(
            client,
            path=h["path"],
            hunk_start=h.get("start", 1),
            hunk_end=h.get("end", 999999),
        )
        changed.update(fns)
    res = sorted(list(changed))
    return {"changed_functions": res, "count": len(res)}


@mcp.tool()
def get_blast_radius(
    repo: str,
    changed: List[str],
    max_hops: int = 4,
) -> Dict[str, Any]:
    """Find all functions directly and indirectly calling the changed functions (Q1).
    Returns affected callers, hop distance, and execution call paths.
    """
    client = _get_client(repo)
    if not changed:
        return {"affected_callers": [], "count": 0, "top_10": []}
    rows, _ = q1_blast_radius(client, changed, max_hops=max_hops)
    return {
        "count": len(rows),
        "top_10": rows[:10],
    }


@mcp.tool()
def get_affected_tests(
    repo: str,
    changed: List[str],
    max_hops: int = 6,
) -> Dict[str, Any]:
    """Find test functions that can reach the changed functions via call graph (Q2).
    Includes shortest execution proof paths from each test to changed code.
    """
    client = _get_client(repo)
    if not changed:
        return {"tests": [], "count": 0, "proof_paths": {}}
    tests = q2a_affected_tests(client, changed, max_hops=max_hops)
    paths: Dict[str, List[str]] = {}
    for t in tests[:10]:
        t_name = t.get("test", "")
        for ch in changed:
            p = q2b_test_proof_path(client, t_name, ch)
            if p:
                paths[t_name] = p
                break
    return {
        "count": len(tests),
        "tests": tests[:10],
        "proof_paths": paths,
    }


@mcp.tool()
def find_reviewers(
    repo: str,
    files: List[str],
    before_ts: Optional[int] = None,
    pr_author: Optional[str] = None,
) -> Dict[str, Any]:
    """Rank suggested code reviewers based on historical authorship on changed files (Q3).
    Prevents future leakage by scoping commits to c.ts < before_ts.
    """
    client = _get_client(repo)
    ts = before_ts if before_ts is not None else int(time.time())
    reviewers = q3_find_reviewers(client, files, before_ts=ts, pr_author=pr_author)
    return {
        "count": len(reviewers),
        "top_reviewers": reviewers[:5],
    }


@mcp.tool()
def get_risk(
    repo: str,
    changed: List[str],
    files: List[str],
    before_ts: Optional[int] = None,
) -> Dict[str, Any]:
    """Calculate objective change-impact risk score and 4-factor breakdown (Q4, Q5, risk.py).
    Formula: 0.35*blast + 0.25*PageRank + 0.25*uncovered + 0.15*churn.
    """
    client = _get_client(repo)
    ts = before_ts if before_ts is not None else int(time.time())
    blast_rows, _ = q1_blast_radius(client, changed) if changed else ([], None)
    test_rows = q2a_affected_tests(client, changed) if changed else []
    centrality = q4_centrality(client, changed) if changed else []
    churn = q5_recent_churn(client, files, since_ts=ts - (90 * 86400), before_ts=ts)

    max_pr = max((float(r.get("pagerank", 0.0)) for r in centrality), default=0.0)
    changed_count = len(changed)
    covered_ratio = 1.0 if changed_count == 0 else min(len(test_rows) / changed_count, 1.0)
    churn_norm = min(churn / 50.0, 1.0)

    risk_data = calculate_risk(
        blast_radius=len(blast_rows),
        max_pagerank_pct=max_pr,
        covered_ratio=covered_ratio,
        churn_norm=churn_norm,
    )
    return risk_data


@mcp.tool()
def explain_path(
    repo: str,
    from_qname: str,
    to_qname: str,
) -> Dict[str, Any]:
    """Compute the shortest call path between two functions in the graph."""
    client = _get_client(repo)
    path = query_explain_path(client, from_qname, to_qname)
    return {
        "from": from_qname,
        "to": to_qname,
        "path": path,
        "reachable": path is not None,
    }


if __name__ == "__main__":
    mcp.run()
