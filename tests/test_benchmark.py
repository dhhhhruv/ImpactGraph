"""Unit tests for benchmark metrics and baselines."""

from pathlib import Path

from benchmark.baselines import (
    baseline_flat_commit_count,
    baseline_grep_imports,
    baseline_llm_only,
    baseline_most_recent_committer,
    baseline_same_name_test,
)
from benchmark.run import (
    aggregate_results,
    hit_at_k,
    mean_reciprocal_rank,
    parse_before_ts,
    recall_at_k,
    score_reviewers,
    score_tests,
)
from graph.client import GraphClient
from tests.test_queries import MockResult


def test_hit_at_k_and_mrr():
    """Verify reviewer hit@k and mean reciprocal rank on ranked lists."""
    ranked = ["alice", "bob", "carol", "dave"]
    truth = ["carol"]
    assert hit_at_k(ranked, truth, 3) == 1.0
    assert hit_at_k(ranked, truth, 2) == 0.0
    assert mean_reciprocal_rank(ranked, truth) == 1.0 / 3.0
    assert mean_reciprocal_rank(["x", "y"], ["z"]) == 0.0
    assert hit_at_k(ranked, [], 3) == 0.0


def test_recall_at_k():
    """Verify test suggestion recall@k against ground-truth test files."""
    suggested = [
        "tests/test_a.py",
        "tests/test_b.py",
        "tests/test_c.py",
    ]
    truth = ["tests/test_b.py", "tests/test_d.py"]
    assert recall_at_k(suggested, truth, 5) == 0.5
    assert recall_at_k(suggested, truth, 1) == 0.0
    assert recall_at_k(suggested, [], 5) == 0.0


def test_score_helpers_and_parse_ts():
    """Verify per-PR score helpers and merged_at parsing."""
    rev = score_reviewers(["bob", "alice"], ["alice"])
    assert rev["hit_at_3"] == 1.0
    assert rev["mrr"] == 0.5
    tests = score_tests(["tests/test_a.py"], ["tests/test_a.py"], True)
    assert tests["recall_at_5"] == 1.0
    assert tests["num_suggested"] == 1.0
    no_gt = score_tests(["tests/test_a.py"], [], False)
    assert no_gt["recall_at_5"] == 0.0
    assert parse_before_ts("2024-01-15T12:00:00Z") == 1705320000


class _RoutingDriver:
    """Mock driver that returns different rows for recent vs flat queries."""

    def __init__(self) -> None:
        self.last_query = ""
        self.last_params: dict = {}

    def query(self, cypher: str, params=None):
        self.last_query = cypher
        self.last_params = params or {}
        if "last_ts" in cypher:
            return MockResult(
                ["author", "last_ts"],
                [["bob", 1_699_999_990], ["alice", 1_699_999_900]],
            )
        return MockResult(
            ["author", "commits"],
            [["alice", 9], ["bob", 2], ["pr_author", 20]],
        )


def test_baseline_most_recent_and_flat_count():
    """Reviewer baselines query only commits before before_ts."""
    before = 1_700_000_000
    client = GraphClient(driver=_RoutingDriver())
    recent = baseline_most_recent_committer(
        client, ["a.py"], before, author="pr_author"
    )
    flat = baseline_flat_commit_count(
        client, ["a.py"], before, author="pr_author"
    )
    assert recent == ["bob"]
    assert flat[0] == "alice"
    assert "pr_author" not in flat
    assert client.evidence_log[-1].params["before"] == before


def test_baseline_same_name_and_grep(tmp_path: Path):
    """Same-name and grep-import test baselines on a tiny fake repo."""
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "backup.py").write_text("def run():\n    pass\n")
    tests = tmp_path / "tests"
    tests.mkdir()
    (tests / "test_backup.py").write_text(
        "from src.backup import run\n\ndef test_run():\n    run()\n"
    )
    (tests / "test_other.py").write_text("def test_noop():\n    assert True\n")
    nested = tests / "unit"
    nested.mkdir()
    (nested / "test_backup.py").write_text("# duplicate name\n")

    same = baseline_same_name_test(
        ["src/backup.py"], repo_path=tmp_path
    )
    assert "tests/test_backup.py" in same
    assert "tests/unit/test_backup.py" in same

    grepped = baseline_grep_imports(tmp_path, ["src/backup.py"])
    assert "tests/test_backup.py" in grepped
    assert "tests/test_other.py" not in grepped


def test_baseline_llm_only_heuristic():
    """LLM-only baseline uses title cues and same-name tests, no graph."""
    out = baseline_llm_only("Fix bug in backup (@carol)", ["src/backup.py"])
    assert "carol" in out["reviewers"]
    assert "maintainer" in out["reviewers"]
    assert out["tests"] == ["tests/test_backup.py"]


def test_aggregate_results_metrics():
    """Aggregation averages hit@3 / MRR / recall across synthetic PRs."""
    per_pr = [
        {
            "number": 1,
            "has_test_changes": True,
            "methods": {
                "graph": {
                    "reviewers": {"hit_at_3": 1.0, "hit_at_5": 1.0, "mrr": 1.0},
                    "tests": {
                        "recall_at_5": 1.0,
                        "num_suggested": 2.0,
                        "has_test_changes": 1.0,
                    },
                },
                "llm_only": {
                    "reviewers": {"hit_at_3": 0.0, "hit_at_5": 0.0, "mrr": 0.0},
                    "tests": {
                        "recall_at_5": 0.0,
                        "num_suggested": 1.0,
                        "has_test_changes": 1.0,
                    },
                },
            },
        },
        {
            "number": 2,
            "has_test_changes": False,
            "methods": {
                "graph": {
                    "reviewers": {"hit_at_3": 0.0, "hit_at_5": 1.0, "mrr": 0.25},
                    "tests": {
                        "recall_at_5": 0.0,
                        "num_suggested": 3.0,
                        "has_test_changes": 0.0,
                    },
                },
                "llm_only": {
                    "reviewers": {"hit_at_3": 0.0, "hit_at_5": 0.0, "mrr": 0.0},
                    "tests": {
                        "recall_at_5": 0.0,
                        "num_suggested": 0.0,
                        "has_test_changes": 0.0,
                    },
                },
            },
        },
    ]
    summary = aggregate_results(per_pr)
    graph = summary["methods"]["graph"]
    assert graph["reviewer_hit_at_3"] == 0.5
    assert graph["reviewer_hit_at_5"] == 1.0
    assert graph["reviewer_mrr"] == 0.625
    assert graph["test_recall_at_5_with_tests"] == 1.0
    assert graph["avg_tests_suggested_with_tests"] == 2.0
    assert graph["avg_tests_suggested_without_tests"] == 3.0
    assert summary["methods"]["llm_only"]["reviewer_hit_at_3"] == 0.0
