"""Agent loop coordinating graph queries, risk analysis, and explanation."""

import copy
import time
from typing import Any, Dict, List, Optional

from agent.prompts import generate_template_summary
from graph.client import GraphClient
from graph.queries import (
    confirm_names,
    q0_diff_to_functions,
    q1_blast_radius,
    q2a_affected_tests,
    q2b_test_proof_path,
    q3_find_reviewers,
    q4_centrality,
    q5_recent_churn,
)
from graph.risk import calculate_risk

_CACHE: Dict[str, Dict[str, Any]] = {}

OUTCOME_ANSWERED = "answered_with_path"
OUTCOME_NOT_IN_GRAPH = "not_in_graph"
OUTCOME_UNKNOWN = "unknown_name"
OUTCOME_CACHED = "cached"

EMPTY_BLAST_MSG = (
    "nothing found in the graph, which may mean the call link is not modelled"
)


def map_diffs(client: GraphClient, hunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Execute Q0 across diff hunks; unknown files get outcome unknown_name."""
    changed: set[str] = set()
    known_files: set[str] = set()
    unknown_files: List[str] = []
    for h in hunks:
        path = h["path"]
        check = confirm_names(client, files=[path])
        if not check["ok"]:
            unknown_files.extend(check["unknown_files"])
            continue
        known_files.add(path)
        fns = q0_diff_to_functions(
            client,
            path=path,
            hunk_start=h.get("start", 1),
            hunk_end=h.get("end", 999999),
        )
        changed.update(fns)
    fns_sorted = sorted(changed)
    if unknown_files:
        return {
            "outcome": OUTCOME_UNKNOWN,
            "changed_functions": fns_sorted,
            "known_files": sorted(known_files),
            "unknown_files": sorted(set(unknown_files)),
        }
    if not fns_sorted:
        return {
            "outcome": OUTCOME_NOT_IN_GRAPH,
            "changed_functions": [],
            "known_files": sorted(known_files),
            "message": EMPTY_BLAST_MSG,
        }
    return {
        "outcome": OUTCOME_ANSWERED,
        "changed_functions": fns_sorted,
        "known_files": sorted(known_files),
    }


def gather_test_paths(
    client: GraphClient, tests: List[Dict[str, Any]], changed_fns: List[str]
) -> Dict[str, List[str]]:
    """Execute Q2b shortest path for each discovered test."""
    paths: Dict[str, List[str]] = {}
    for t in tests:
        test_name = t.get("test", "")
        for ch in changed_fns:
            p = q2b_test_proof_path(client, test_name, ch)
            if p:
                paths[test_name] = p
                break
    return paths


def compute_agent_risk(
    blast: List[Dict[str, Any]],
    centrality: List[Dict[str, Any]],
    tests: List[Dict[str, Any]],
    churn: int,
    changed_count: int,
) -> Dict[str, Any]:
    """Calculate normalized risk metrics and objective score."""
    max_pr = max((float(r.get("pagerank", 0.0)) for r in centrality), default=0.0)
    covered_ratio = min(len(tests) / max(changed_count, 1), 1.0)
    churn_norm = min(churn / 50.0, 1.0)
    return calculate_risk(
        blast_radius=len(blast),
        max_pagerank_pct=max_pr,
        covered_ratio=covered_ratio,
        churn_norm=churn_norm,
    )


def _tool_outcomes(
    map_result: Dict[str, Any],
    blast: List[Dict[str, Any]],
    tests: List[Dict[str, Any]],
    reviewers: List[Dict[str, Any]],
    centrality: List[Dict[str, Any]],
    reviewer_outcome: str,
) -> Dict[str, str]:
    """Derive per-section outcome labels for UI and PR comment."""
    return {
        "map_diff": str(map_result.get("outcome", OUTCOME_ANSWERED)),
        "blast": OUTCOME_ANSWERED if blast else OUTCOME_NOT_IN_GRAPH,
        "tests": OUTCOME_ANSWERED if tests else OUTCOME_NOT_IN_GRAPH,
        "reviewers": reviewer_outcome,
        "centrality": OUTCOME_ANSWERED if centrality else OUTCOME_NOT_IN_GRAPH,
        "churn": OUTCOME_ANSWERED if map_result.get("known_files") else OUTCOME_NOT_IN_GRAPH,
        "risk": OUTCOME_ANSWERED,
    }


def run_impact_agent(
    client: GraphClient,
    diff_hunks: List[Dict[str, Any]],
    head_sha: str = "HEAD",
    before_ts: Optional[int] = None,
    pr_author: Optional[str] = None,
    max_hops: int = 4,
) -> Dict[str, Any]:
    """Execute change-impact agent loop over code graph and generate decision."""
    if head_sha in _CACHE:
        cached = copy.deepcopy(_CACHE[head_sha])
        cached["outcome"] = OUTCOME_CACHED
        cached["outcomes"] = {key: OUTCOME_CACHED for key in cached.get("outcomes", {})}
        return cached

    ts = before_ts if before_ts is not None else int(time.time())
    map_result = map_diffs(client, diff_hunks)
    files = list(map_result.get("known_files") or [])
    changed_fns = list(map_result.get("changed_functions") or [])

    blast_rows: List[Dict[str, Any]] = []
    test_rows: List[Dict[str, Any]] = []
    test_paths: Dict[str, List[str]] = {}
    if changed_fns:
        blast_rows, _ = q1_blast_radius(client, changed_fns, max_hops=max_hops)
        test_rows = q2a_affected_tests(client, changed_fns, max_hops=max_hops)
        test_paths = gather_test_paths(client, test_rows, changed_fns)

    reviewer_outcome = OUTCOME_NOT_IN_GRAPH
    reviewers: List[Dict[str, Any]] = []
    if files:
        author_check = (
            confirm_names(client, people=[pr_author])
            if pr_author is not None
            else {"ok": True}
        )
        if author_check["ok"]:
            reviewers = q3_find_reviewers(
                client, files, before_ts=ts, pr_author=pr_author
            )
            reviewer_outcome = (
                OUTCOME_ANSWERED if reviewers else OUTCOME_NOT_IN_GRAPH
            )
        else:
            reviewer_outcome = OUTCOME_UNKNOWN
    centrality = q4_centrality(client, changed_fns) if changed_fns else []
    churn = (
        q5_recent_churn(client, files, since_ts=ts - (90 * 86400), before_ts=ts)
        if files
        else 0
    )
    risk_data = compute_agent_risk(
        blast_rows, centrality, test_rows, churn, len(changed_fns)
    )

    outcomes = _tool_outcomes(
        map_result, blast_rows, test_rows, reviewers, centrality, reviewer_outcome
    )
    decision: Dict[str, Any] = {
        "head_sha": head_sha,
        "files_changed": files,
        "changed_functions": changed_fns,
        "blast_radius": blast_rows,
        "affected_tests": test_rows,
        "test_proof_paths": test_paths,
        "reviewers": reviewers,
        "centrality": centrality,
        "recent_churn": churn,
        "risk": risk_data,
        "max_hops": max_hops,
        "outcomes": outcomes,
        "outcome": outcomes["map_diff"],
        "evidence": [ev.to_dict() for ev in client.evidence_log],
    }
    if not blast_rows and changed_fns:
        decision["blast_message"] = EMPTY_BLAST_MSG
    explanation = generate_template_summary(decision)
    decision.update(explanation)
    _CACHE[head_sha] = decision
    return decision
