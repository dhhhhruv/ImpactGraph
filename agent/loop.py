"""Agent loop coordinating graph queries, risk analysis, and explanation."""

import time
from typing import Any, Dict, List, Optional, Set

from agent.prompts import generate_template_summary
from graph.client import GraphClient
from graph.queries import (
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


def map_diffs(client: GraphClient, hunks: List[Dict[str, Any]]) -> List[str]:
    """Execute Q0 across all diff hunks to identify changed functions."""
    changed = set()
    for h in hunks:
        fns = q0_diff_to_functions(
            client,
            path=h["path"],
            hunk_start=h.get("start", 1),
            hunk_end=h.get("end", 999999),
        )
        changed.update(fns)
    return sorted(list(changed))


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
    covered_ratio = 1.0 if changed_count == 0 else min(len(tests) / changed_count, 1.0)
    churn_norm = min(churn / 50.0, 1.0)

    return calculate_risk(
        blast_radius=len(blast),
        max_pagerank_pct=max_pr,
        covered_ratio=covered_ratio,
        churn_norm=churn_norm,
    )


def run_impact_agent(
    client: GraphClient,
    diff_hunks: List[Dict[str, Any]],
    head_sha: str = "HEAD",
    before_ts: Optional[int] = None,
    pr_author: Optional[str] = None,
) -> Dict[str, Any]:
    """Execute change-impact agent loop over code graph and generate decision."""
    if head_sha in _CACHE:
        return _CACHE[head_sha]

    ts = before_ts if before_ts is not None else int(time.time())
    files = list({h["path"] for h in diff_hunks})

    # 1. Mandatory Q0: diff to functions
    changed_fns = map_diffs(client, diff_hunks)

    # 2. Mandatory Q1: blast radius
    blast_rows, _ = q1_blast_radius(client, changed_fns) if changed_fns else ([], None)

    # 3. Mandatory Q2: tests & proof paths
    test_rows = q2a_affected_tests(client, changed_fns) if changed_fns else []
    test_paths = gather_test_paths(client, test_rows, changed_fns)

    # 4. Mandatory Q3 & Q4 & Q5: reviewers, centrality, churn
    reviewers = q3_find_reviewers(client, files, before_ts=ts, pr_author=pr_author)
    centrality = q4_centrality(client, changed_fns) if changed_fns else []
    churn = q5_recent_churn(client, files, since_ts=ts - (90 * 86400), before_ts=ts)

    # 5. Objective risk calculation
    risk_data = compute_agent_risk(blast_rows, centrality, test_rows, churn, len(changed_fns))

    decision = {
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
        "evidence": [ev.to_dict() for ev in client.evidence_log],
    }

    explanation = generate_template_summary(decision)
    decision.update(explanation)

    _CACHE[head_sha] = decision
    return decision
