"""Risk scoring engine for ImpactGraph.

Pure Python implementation. Computes objective risk score and classification
based on blast radius, PageRank centrality, test coverage, and code churn.
Formula defined in AGENTS.md:
s = 0.35*min(blast/50, 1) + 0.25*max_pagerank_pct + 0.25*(1-covered_ratio) + 0.15*churn_norm
"""

from typing import Any, Dict, List


def classify_risk(score: float) -> str:
    """Classify risk score into low, medium, or high."""
    if score < 0.33:
        return "low"
    if score < 0.66:
        return "medium"
    return "high"


def calculate_risk(
    blast_radius: int,
    max_pagerank_pct: float,
    covered_ratio: float,
    churn_norm: float,
) -> Dict[str, Any]:
    """Calculate normalized risk score and factor breakdown.
    
    Args:
        blast_radius: Number of affected callers (direct and indirect).
        max_pagerank_pct: Centrality percentile [0.0, 1.0].
        covered_ratio: Ratio of changed functions covered by tests [0.0, 1.0].
        churn_norm: Normalized recent commit churn [0.0, 1.0].
        
    Returns:
        Dict containing total score, label, factors, and findings notes.
    """
    blast_norm = min(max(blast_radius, 0) / 50.0, 1.0)
    pr_norm = min(max(max_pagerank_pct, 0.0), 1.0)
    cov_norm = min(max(covered_ratio, 0.0), 1.0)
    churn_factor = min(max(churn_norm, 0.0), 1.0)

    score = (
        0.35 * blast_norm
        + 0.25 * pr_norm
        + 0.25 * (1.0 - cov_norm)
        + 0.15 * churn_factor
    )
    score = round(min(max(score, 0.0), 1.0), 4)

    notes: List[str] = []
    if cov_norm == 0.0:
        notes.append("No test reaches this change")
    if blast_radius >= 50:
        notes.append("Blast radius saturated (>= 50 affected functions)")

    return {
        "score": score,
        "label": classify_risk(score),
        "factors": {
            "blast_component": round(0.35 * blast_norm, 4),
            "pagerank_component": round(0.25 * pr_norm, 4),
            "uncovered_component": round(0.25 * (1.0 - cov_norm), 4),
            "churn_component": round(0.15 * churn_factor, 4),
        },
        "raw_inputs": {
            "blast_radius": blast_radius,
            "max_pagerank_pct": pr_norm,
            "covered_ratio": cov_norm,
            "churn_norm": churn_factor,
        },
        "notes": notes,
    }
