"""Unit tests for graph.risk."""

from graph.risk import calculate_risk, classify_risk


def test_classify_risk_boundaries():
    """Verify classification thresholds (<0.33 low, <0.66 medium, >=0.66 high)."""
    assert classify_risk(0.0) == "low"
    assert classify_risk(0.3299) == "low"
    assert classify_risk(0.33) == "medium"
    assert classify_risk(0.50) == "medium"
    assert classify_risk(0.6599) == "medium"
    assert classify_risk(0.66) == "high"
    assert classify_risk(1.0) == "high"


def test_all_zeros_minimal_risk():
    """Verify minimal risk when blast=0, pr=0, churn=0, and tests cover 100%."""
    res = calculate_risk(
        blast_radius=0,
        max_pagerank_pct=0.0,
        covered_ratio=1.0,
        churn_norm=0.0,
    )
    assert res["score"] == 0.0
    assert res["label"] == "low"
    assert res["factors"]["blast_component"] == 0.0
    assert res["factors"]["pagerank_component"] == 0.0
    assert res["factors"]["uncovered_component"] == 0.0
    assert res["factors"]["churn_component"] == 0.0
    assert "No test reaches this change" not in res["notes"]


def test_all_ones_maximal_risk():
    """Verify maximal risk when blast=50, pr=1, churn=1, and tests cover 0%."""
    res = calculate_risk(
        blast_radius=50,
        max_pagerank_pct=1.0,
        covered_ratio=0.0,
        churn_norm=1.0,
    )
    assert res["score"] == 1.0
    assert res["label"] == "high"
    assert res["factors"]["blast_component"] == 0.35
    assert res["factors"]["pagerank_component"] == 0.25
    assert res["factors"]["uncovered_component"] == 0.25
    assert res["factors"]["churn_component"] == 0.15
    assert "No test reaches this change" in res["notes"]
    assert "Blast radius saturated (>= 50 affected functions)" in res["notes"]


def test_no_test_reaches_finding():
    """Verify covered_ratio=0.0 is treated as a finding note, not an exception."""
    res = calculate_risk(
        blast_radius=10,
        max_pagerank_pct=0.2,
        covered_ratio=0.0,
        churn_norm=0.1,
    )
    assert "No test reaches this change" in res["notes"]
    assert res["factors"]["uncovered_component"] == 0.25


def test_blast_radius_capping():
    """Verify blast radius over 50 is capped at 50 (0.35 max contribution)."""
    res1 = calculate_risk(50, 0.5, 0.5, 0.5)
    res2 = calculate_risk(500, 0.5, 0.5, 0.5)
    assert res1["score"] == res2["score"]
    assert res2["factors"]["blast_component"] == 0.35
    assert "Blast radius saturated (>= 50 affected functions)" in res2["notes"]


def test_exact_boundary_scores():
    """Verify boundary conditions for exactly targeted scores."""
    # To get score == 0.33:
    # 0.35*(blast/50) = 0.33 when blast/50 = 0.33/0.35
    res_medium = calculate_risk(
        blast_radius=20,  # 0.35 * 0.4 = 0.14
        max_pagerank_pct=0.76,  # 0.25 * 0.76 = 0.19
        covered_ratio=1.0,  # 0.0
        churn_norm=0.0,  # 0.0 -> total 0.33
    )
    assert res_medium["score"] == 0.33
    assert res_medium["label"] == "medium"

    # To get score == 0.66:
    # blast 50 (0.35) + pr 0.84 (0.21) + covered 0.6 (0.25*0.4 = 0.10) -> total 0.66
    res_high = calculate_risk(
        blast_radius=50,
        max_pagerank_pct=0.84,
        covered_ratio=0.6,
        churn_norm=0.0,
    )
    assert res_high["score"] == 0.66
    assert res_high["label"] == "high"
