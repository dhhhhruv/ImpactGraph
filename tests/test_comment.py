"""Unit tests for agent.comment."""

from agent.comment import MARKER, format_pr_comment, validate_decision


def _base_decision(**overrides):
    """Minimal decision object matching agent.loop output shape."""
    data = {
        "head_sha": "abc123",
        "files_changed": ["src/vorta/views.py"],
        "changed_functions": ["vorta.views.backup"],
        "blast_radius": [
            {
                "affected": "vorta.main",
                "via": "vorta.views.backup",
                "hops": 1,
                "path": ["vorta.main", "vorta.views.backup"],
            }
        ],
        "affected_tests": [
            {"test": "tests.test_backup", "file": "tests/test_backup.py", "hops": 2}
        ],
        "test_proof_paths": {
            "tests.test_backup": [
                "tests.test_backup",
                "vorta.main",
                "vorta.views.backup",
            ]
        },
        "reviewers": [
            {
                "author": "alice",
                "commits": 5,
                "files_covered": 1,
                "last_ts": 1700000000,
                "score": 0.8,
            }
        ],
        "centrality": [{"fn": "vorta.views.backup", "pagerank": 0.12}],
        "recent_churn": 3,
        "risk": {
            "score": 0.42,
            "label": "medium",
            "factors": {
                "blast_component": 0.14,
                "pagerank_component": 0.10,
                "uncovered_component": 0.12,
                "churn_component": 0.06,
            },
            "notes": [],
        },
        "evidence": [
            {
                "cypher": "MATCH (f:Function) RETURN f.qname",
                "params": {},
                "row_count": 1,
                "duration_ms": 12.5,
            }
        ],
        "summary": "Change touches vorta.views.backup with medium risk.",
        "section_notes": {
            "blast": "vorta.main calls the changed function.",
            "tests": "tests.test_backup reaches the change.",
            "reviewers": "alice has recent history on these files.",
            "risk": "Score driven by blast and coverage.",
        },
        "notable_paths": [["vorta.main", "vorta.views.backup"]],
    }
    data.update(overrides)
    return data


def test_comment_contains_hidden_marker():
    """PR comment must start with the ImpactGraph HTML marker."""
    comment = format_pr_comment(_base_decision())
    assert comment.startswith(MARKER)
    assert "<!-- impactgraph -->" in comment


def test_comment_formats_sections():
    """Comment includes risk, blast, tests, reviewers, and evidence."""
    comment = format_pr_comment(_base_decision())
    assert "## Risk: Medium (0.42)" in comment
    assert "Blast radius" in comment
    assert "`vorta.main`" in comment
    assert "## Tests to Run" in comment
    assert "```bash" in comment
    assert "pytest tests/test_backup.py" in comment
    assert "## Suggested Reviewers" in comment
    assert "alice" in comment
    assert "## Graph Evidence" in comment
    assert "<details>" in comment
    assert "12.5 ms" in comment


def test_comment_no_tests_is_finding():
    """When no tests reach the change, report a finding (not an error)."""
    decision = _base_decision(
        affected_tests=[],
        test_proof_paths={},
        section_notes={
            "blast": "ok",
            "tests": "No test reaches this change",
            "reviewers": "ok",
            "risk": "ok",
        },
        risk={
            "score": 0.5,
            "label": "medium",
            "factors": {
                "blast_component": 0.1,
                "pagerank_component": 0.1,
                "uncovered_component": 0.25,
                "churn_component": 0.05,
            },
            "notes": ["No test reaches this change"],
        },
    )
    comment = format_pr_comment(decision)
    assert "No test reaches this change" in comment
    assert "**Finding:** No test reaches this change" in comment
    assert "error" not in comment.lower()
    assert "```bash" not in comment


def test_validate_decision_removes_hallucinated_functions():
    """validate_decision strips function names absent from graph evidence."""
    decision = _base_decision(
        summary=(
            "Change touches vorta.views.backup and also "
            "fake.module.does_not_exist which is invented."
        ),
        section_notes={
            "blast": "fake.module.does_not_exist looks risky.",
            "tests": "tests.test_backup is fine.",
            "reviewers": "alice is fine.",
            "risk": "ok",
        },
        notable_paths=[
            ["vorta.main", "vorta.views.backup"],
            ["fake.module.does_not_exist"],
        ],
    )
    cleaned = validate_decision(decision)
    assert "vorta.views.backup" in cleaned["summary"]
    assert "fake.module.does_not_exist" not in cleaned["summary"]
    assert "fake.module.does_not_exist" not in cleaned["section_notes"]["blast"]
    assert "tests.test_backup" in cleaned["section_notes"]["tests"]
    assert ["fake.module.does_not_exist"] not in cleaned["notable_paths"]
    assert ["vorta.main", "vorta.views.backup"] in cleaned["notable_paths"]
