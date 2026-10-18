"""Benchmark runner: graph vs baselines, no LLM for graph predictions."""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence, Set

from benchmark.baselines import (
    baseline_flat_commit_count,
    baseline_grep_imports,
    baseline_llm_only,
    baseline_most_recent_committer,
    baseline_same_name_test,
)
from graph.client import GraphClient
from graph.queries import q0_diff_to_functions, q1_blast_radius, q2a_affected_tests, q3_find_reviewers

def load_author_map() -> Dict[str, str]:
    """Load email -> GitHub login map (missing/unresolved emails are skipped)."""
    if not AUTHOR_MAP_FILE.is_file():
        return {}
    raw = json.loads(AUTHOR_MAP_FILE.read_text(encoding="utf-8"))
    return {
        email: info["github_login"]
        for email, info in raw.items()
        if info.get("github_login")
    }

BENCH_DIR = Path(__file__).resolve().parent
DEFAULT_PRS = BENCH_DIR / "prs.json"
RESULTS_MD = BENCH_DIR / "results.md"
RESULTS_JSON = BENCH_DIR / "results.json"
AUTHOR_MAP_FILE = BENCH_DIR / "author_map.json"

SAMPLE_PRS: List[Dict[str, Any]] = [
    {
        "number": 1,
        "title": "Fix backup path handling",
        "author": "alice",
        "merged_at": "2024-01-15T12:00:00Z",
        "changed_py_files": ["src/vorta/backup.py"],
        "ground_truth_reviewers": ["bob", "carol"],
        "ground_truth_tests": ["tests/test_backup.py"],
        "has_test_changes": True,
    },
    {
        "number": 2,
        "title": "Docs tweak only",
        "author": "dave",
        "merged_at": "2024-02-01T09:30:00Z",
        "changed_py_files": ["src/vorta/utils.py"],
        "ground_truth_reviewers": ["bob"],
        "ground_truth_tests": [],
        "has_test_changes": False,
    },
]


def parse_before_ts(merged_at: str) -> int:
    """Convert PR merged_at ISO timestamp to unix seconds (UTC)."""
    text = merged_at.strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(text)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return int(dt.timestamp())


def load_prs(path: Path | None = None) -> List[Dict[str, Any]]:
    """Load prs.json, or sample PRs when the file is missing/empty."""
    prs_path = path or DEFAULT_PRS
    if prs_path.is_file():
        data = json.loads(prs_path.read_text(encoding="utf-8"))
        if isinstance(data, list) and data:
            return data
    return list(SAMPLE_PRS)


def normalize_name(value: str) -> str:
    """Case-fold names/paths for metric comparisons."""
    return str(value).strip().lower().replace("\\", "/")


def hit_at_k(ranked: Sequence[str], truth: Sequence[str], k: int) -> float:
    """1.0 if any ground-truth item appears in the top-k ranked list."""
    if not truth:
        return 0.0
    top = {normalize_name(x) for x in list(ranked)[:k]}
    return 1.0 if any(normalize_name(t) in top for t in truth) else 0.0


def mean_reciprocal_rank(ranked: Sequence[str], truth: Sequence[str]) -> float:
    """MRR for the first ground-truth hit in a ranked list."""
    if not truth:
        return 0.0
    want = {normalize_name(t) for t in truth}
    for i, item in enumerate(ranked, start=1):
        if normalize_name(item) in want:
            return 1.0 / float(i)
    return 0.0


def recall_at_k(suggested: Sequence[str], truth: Sequence[str], k: int) -> float:
    """|top-k suggestions ∩ truth| / |truth|; 0 when truth is empty."""
    if not truth:
        return 0.0
    top = {normalize_name(x) for x in list(suggested)[:k]}
    hits = sum(1 for t in truth if normalize_name(t) in top)
    return hits / float(len(truth))


def changed_functions_for_pr(
    client: GraphClient, files: List[str]
) -> List[str]:
    """Map each changed file to functions via Q0 over the whole file."""
    found: List[str] = []
    seen: Set[str] = set()
    for path in files:
        for qname in q0_diff_to_functions(client, path, 1, 999999):
            if qname not in seen:
                seen.add(qname)
                found.append(qname)
    return found


def graph_predictions(
    client: GraphClient, pr: Dict[str, Any]
) -> Dict[str, Any]:
    """Run Q0/Q1/Q2/Q3 for one PR using only history before merged_at."""
    files = list(pr.get("changed_py_files") or [])
    before = parse_before_ts(str(pr["merged_at"]))
    changed = changed_functions_for_pr(client, files)
    blast: List[Dict[str, Any]] = []
    tests: List[Dict[str, Any]] = []
    if changed:
        blast, _ = q1_blast_radius(client, changed)
        tests = q2a_affected_tests(client, changed)
    author_map = load_author_map()
    reviewers = q3_find_reviewers(client, files, before_ts=before, pr_author=None)
    pr_author = pr.get("author")
    mapped = []
    for r in reviewers:
        login = author_map.get(r.get("email", ""), r.get("author"))
        if login and login != pr_author:
            mapped.append(login)
    return {
        "reviewers": mapped,
        "tests": [str(t["file"]) for t in tests if t.get("file")],
        "blast_size": len(blast),
        "changed_functions": changed,
    }


def baseline_predictions(
    client: GraphClient,
    pr: Dict[str, Any],
    repo_path: Optional[Path],
) -> Dict[str, Dict[str, List[str]]]:
    """Run all four baselines for one PR."""
    files = list(pr.get("changed_py_files") or [])
    before = parse_before_ts(str(pr["merged_at"]))
    author = pr.get("author")
    llm = baseline_llm_only(str(pr.get("title") or ""), files)
    same = baseline_same_name_test(files, repo_path=repo_path)
    grep = (
        baseline_grep_imports(repo_path, files)
        if repo_path is not None
        else []
    )
    return {
        "most_recent_committer": {
            "reviewers": baseline_most_recent_committer(
                client, files, before, author
            ),
            "tests": [],
        },
        "flat_commit_count": {
            "reviewers": baseline_flat_commit_count(
                client, files, before, author
            ),
            "tests": [],
        },
        "same_name_test": {"reviewers": [], "tests": same},
        "grep_imports": {"reviewers": [], "tests": grep},
        "llm_only": llm,
    }


def _mean(values: Iterable[float]) -> float:
    """Arithmetic mean rounded to 4 decimals; 0.0 for an empty series."""
    vals = list(values)
    if not vals:
        return 0.0
    return round(sum(vals) / float(len(vals)), 4)


def score_reviewers(
    ranked: Sequence[str], truth: Sequence[str]
) -> Dict[str, float]:
    """Compute hit@3, hit@5, and MRR for one PR's reviewer ranking."""
    return {
        "hit_at_3": hit_at_k(ranked, truth, 3),
        "hit_at_5": hit_at_k(ranked, truth, 5),
        "mrr": mean_reciprocal_rank(ranked, truth),
    }


def score_tests(
    suggested: Sequence[str],
    truth: Sequence[str],
    has_test_changes: bool,
) -> Dict[str, float]:
    """Compute recall@5 and suggestion count; recall only when GT tests exist."""
    return {
        "recall_at_5": (
            recall_at_k(suggested, truth, 5) if has_test_changes else 0.0
        ),
        "num_suggested": float(len(suggested)),
        "has_test_changes": 1.0 if has_test_changes else 0.0,
    }


def evaluate_pr(
    client: GraphClient,
    pr: Dict[str, Any],
    repo_path: Optional[Path],
) -> Dict[str, Any]:
    """Score graph and baseline predictions against PR ground truth."""
    truth_rev = list(pr.get("ground_truth_reviewers") or [])
    truth_tests = list(pr.get("ground_truth_tests") or [])
    has_tests = bool(pr.get("has_test_changes"))
    graph = graph_predictions(client, pr)
    bases = baseline_predictions(client, pr, repo_path)
    methods = {
        "graph": {
            "reviewers": score_reviewers(graph["reviewers"], truth_rev),
            "tests": score_tests(graph["tests"], truth_tests, has_tests),
            "blast_size": graph["blast_size"],
            "predicted_reviewers": graph["reviewers"][:5],
            "predicted_tests": graph["tests"][:10],
        }
    }
    for name, pred in bases.items():
        methods[name] = {
            "reviewers": score_reviewers(pred.get("reviewers", []), truth_rev),
            "tests": score_tests(pred.get("tests", []), truth_tests, has_tests),
            "predicted_reviewers": list(pred.get("reviewers", []))[:5],
            "predicted_tests": list(pred.get("tests", []))[:10],
        }
    return {
        "number": pr.get("number"),
        "title": pr.get("title"),
        "has_test_changes": has_tests,
        "methods": methods,
    }


def _aggregate_method(rows: List[Dict[str, Any]], method: str) -> Dict[str, Any]:
    """Aggregate reviewer/test metrics for one method across PRs."""
    with_tests = [r for r in rows if r.get("has_test_changes")]
    without = [r for r in rows if not r.get("has_test_changes")]

    def rev_metric(key: str) -> float:
        return _mean(r["methods"][method]["reviewers"][key] for r in rows)

    def test_metric(subset: List[Dict[str, Any]], key: str) -> float:
        if not subset:
            return 0.0
        return _mean(r["methods"][method]["tests"][key] for r in subset)

    return {
        "reviewer_hit_at_3": rev_metric("hit_at_3"),
        "reviewer_hit_at_5": rev_metric("hit_at_5"),
        "reviewer_mrr": rev_metric("mrr"),
        "test_recall_at_5_with_tests": test_metric(with_tests, "recall_at_5"),
        "avg_tests_suggested_with_tests": test_metric(
            with_tests, "num_suggested"
        ),
        "avg_tests_suggested_without_tests": test_metric(
            without, "num_suggested"
        ),
        "n_prs": len(rows),
        "n_with_test_changes": len(with_tests),
        "n_without_test_changes": len(without),
    }


def aggregate_results(per_pr: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Build method-level summary tables from per-PR scores."""
    if not per_pr:
        return {"methods": {}, "per_pr": []}
    method_names = list(per_pr[0]["methods"].keys())
    methods = {name: _aggregate_method(per_pr, name) for name in method_names}
    return {"methods": methods, "per_pr": per_pr}


def _summary_table_rows(methods: Dict[str, Any]) -> List[str]:
    """Build Markdown table rows for method-level metrics."""
    rows = [
        "| Method | Hit@3 | Hit@5 | MRR | "
        "Test recall@5 (with tests) | Avg tests (with) | Avg tests (without) |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    for name, m in methods.items():
        rows.append(
            f"| {name} | {m['reviewer_hit_at_3']:.4f} | "
            f"{m['reviewer_hit_at_5']:.4f} | {m['reviewer_mrr']:.4f} | "
            f"{m['test_recall_at_5_with_tests']:.4f} | "
            f"{m['avg_tests_suggested_with_tests']:.4f} | "
            f"{m['avg_tests_suggested_without_tests']:.4f} |"
        )
    return rows


def render_results_md(summary: Dict[str, Any]) -> str:
    """Render Markdown comparison table plus method notes and limits."""
    lines = [
        "# ImpactGraph Benchmark Results",
        "",
        "Graph queries run directly in Python (no LLM). "
        "All authorship uses `c.ts < merged_at` (no future leakage).",
        "",
        "## Summary",
        "",
        *_summary_table_rows(summary.get("methods") or {}),
        "",
        "## Method",
        "",
        "- **graph**: Q3 reviewers + Q2a tests via call graph.",
        "- **most_recent_committer**: latest author on changed files.",
        "- **flat_commit_count**: authors ranked by raw commit count.",
        "- **same_name_test**: `tests/test_<stem>.py` naming heuristic.",
        "- **grep_imports**: `tests/` files importing changed modules.",
        "- **llm_only**: title/@mention heuristic, no graph.",
        "",
        "## Limits",
        "",
        "- Reviewers may be assigned for non-expertise reasons.",
        "- A PR without test edits does not mean no test was needed.",
        "- Call graph links are name-based and approximate.",
        "",
    ]
    return "\n".join(lines)


def write_outputs(summary: Dict[str, Any]) -> None:
    """Write results.md and results.json for the Benchmark UI tab."""
    RESULTS_MD.write_text(render_results_md(summary), encoding="utf-8")
    payload = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "methods": summary.get("methods", {}),
        "per_pr": summary.get("per_pr", []),
        "limits": [
            "Reviewers may be assigned for non-expertise reasons.",
            "No test change does not imply no test was needed.",
            "Call graph is name-based and approximate.",
        ],
    }
    RESULTS_JSON.write_text(json.dumps(payload, indent=2), encoding="utf-8")


def run_benchmark(
    client: GraphClient,
    prs: Optional[List[Dict[str, Any]]] = None,
    repo_path: Optional[Path] = None,
) -> Dict[str, Any]:
    """Evaluate all PRs and return aggregated results."""
    items = prs if prs is not None else load_prs()
    per_pr = [evaluate_pr(client, pr, repo_path) for pr in items]
    summary = aggregate_results(per_pr)
    write_outputs(summary)
    return summary


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI for python -m benchmark.run."""
    p = argparse.ArgumentParser(description="Run ImpactGraph benchmark")
    p.add_argument("--prs", default=str(DEFAULT_PRS), help="path to prs.json")
    p.add_argument("--repo-path", default=None, help="local checkout for test baselines")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=6379)
    p.add_argument("--graph", default="impact_borgbase_vorta")
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entrypoint: load PRs, score graph vs baselines, write results."""
    args = build_arg_parser().parse_args(argv)
    client = GraphClient(host=args.host, port=args.port, graph_name=args.graph)
    repo = Path(args.repo_path) if args.repo_path else None
    summary = run_benchmark(client, prs=load_prs(Path(args.prs)), repo_path=repo)
    print(render_results_md(summary))
    print(f"Wrote {RESULTS_MD} and {RESULTS_JSON}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
