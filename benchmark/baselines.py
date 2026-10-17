"""Non-graph and LLM-only baselines for the ImpactGraph benchmark."""

from __future__ import annotations

import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

from graph.client import GraphClient

Q_MOST_RECENT = """
MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts < $before
RETURN a.name AS author, max(c.ts) AS last_ts
ORDER BY last_ts DESC
LIMIT 20
"""

Q_FLAT_COMMITS = """
MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts < $before
RETURN a.name AS author, count(DISTINCT c) AS commits
ORDER BY commits DESC
LIMIT 20
"""


def _exclude_author(names: List[str], author: Optional[str]) -> List[str]:
    """Drop the PR author (case-insensitive) from a ranked name list."""
    if not author:
        return names
    skip = author.lower()
    return [n for n in names if str(n).lower() != skip]


def baseline_most_recent_committer(
    client: GraphClient,
    files: List[str],
    before_ts: int,
    author: Optional[str] = None,
) -> List[str]:
    """Return the single most recent committer on files before before_ts."""
    if not files:
        return []
    params = {"files": files, "before": int(before_ts)}
    rows, _ = client.ro_query(Q_MOST_RECENT, params)
    ranked = [str(r["author"]) for r in rows if r.get("author")]
    filtered = _exclude_author(ranked, author)
    return filtered[:1]


def baseline_flat_commit_count(
    client: GraphClient,
    files: List[str],
    before_ts: int,
    author: Optional[str] = None,
) -> List[str]:
    """Rank authors by raw commit count on changed files before before_ts."""
    if not files:
        return []
    params = {"files": files, "before": int(before_ts)}
    rows, _ = client.ro_query(Q_FLAT_COMMITS, params)
    ranked = [str(r["author"]) for r in rows if r.get("author")]
    return _exclude_author(ranked, author)


def _module_stem(file_path: str) -> Optional[str]:
    """Return the file stem for non-test Python paths."""
    path = Path(file_path.replace("\\", "/"))
    if path.suffix != ".py":
        return None
    stem = path.stem
    if stem.startswith("test_") or stem == "__init__":
        return None
    return stem


def baseline_same_name_test(
    changed_files: List[str],
    repo_path: Optional[str | Path] = None,
) -> List[str]:
    """Suggest tests/test_<stem>.py (and repo matches under tests/**)."""
    suggested: List[str] = []
    seen: Set[str] = set()
    root = Path(repo_path) if repo_path else None
    for path in changed_files:
        stem = _module_stem(path)
        if stem is None:
            continue
        candidates = [f"tests/test_{stem}.py"]
        if root and root.is_dir():
            candidates.extend(
                str(p.relative_to(root)).replace("\\", "/")
                for p in root.glob(f"tests/**/test_{stem}.py")
            )
        for cand in candidates:
            if cand in seen:
                continue
            if root is None or (root / cand).is_file():
                seen.add(cand)
                suggested.append(cand)
    return suggested


def _import_patterns(module_hint: str) -> List[re.Pattern[str]]:
    """Build regexes that match imports of a module name or final segment."""
    escaped = re.escape(module_hint)
    return [
        re.compile(rf"^\s*import\s+{escaped}\b", re.M),
        re.compile(rf"^\s*from\s+{escaped}\b", re.M),
        re.compile(rf"^\s*import\s+[\w.]*{escaped}\b", re.M),
        re.compile(rf"^\s*from\s+[\w.]*{escaped}\b", re.M),
    ]


def _module_hints(file_path: str) -> List[str]:
    """Derive importable module strings from a repo-relative file path."""
    norm = file_path.replace("\\", "/").replace("/", ".")
    if norm.endswith(".py"):
        norm = norm[:-3]
    if norm.endswith(".__init__"):
        norm = norm[: -len(".__init__")]
    parts = [p for p in norm.split(".") if p]
    if not parts:
        return []
    hints = {".".join(parts), parts[-1]}
    if len(parts) >= 2:
        hints.add(".".join(parts[-2:]))
    return sorted(hints, key=len, reverse=True)


def baseline_grep_imports(
    repo_path: str | Path,
    changed_files: List[str],
) -> List[str]:
    """Return test files under tests/ that import a changed module name."""
    root = Path(repo_path)
    tests_dir = root / "tests"
    if not tests_dir.is_dir():
        return []
    patterns: List[re.Pattern[str]] = []
    for path in changed_files:
        for hint in _module_hints(path):
            patterns.extend(_import_patterns(hint))
    if not patterns:
        return []
    hits: List[str] = []
    for test_file in sorted(tests_dir.rglob("*.py")):
        try:
            text = test_file.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        if any(p.search(text) for p in patterns):
            rel = str(test_file.relative_to(root)).replace("\\", "/")
            hits.append(rel)
    return hits


def baseline_llm_only(
    pr_title: str,
    changed_files: List[str],
) -> Dict[str, List[str]]:
    """Heuristic stand-in for an LLM with no graph access."""
    title = (pr_title or "").lower()
    reviewers: List[str] = []
    # Title @mentions are the only "person" signal without git history.
    for match in re.findall(r"@([A-Za-z][\w-]*)", pr_title or ""):
        if match.lower() not in {r.lower() for r in reviewers}:
            reviewers.append(match)
    if "fix" in title or "bug" in title:
        reviewers.append("maintainer")
    tests = baseline_same_name_test(changed_files, repo_path=None)
    # Prefer fewer suggestions when the title does not mention tests.
    if "test" not in title:
        tests = tests[:1]
    return {"reviewers": reviewers, "tests": tests}
