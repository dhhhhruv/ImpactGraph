"""PR comment formatting and hallucination validation for ImpactGraph."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, Iterable, List, Set

MARKER = "<!-- impactgraph -->"

_QNAME_RE = re.compile(r"\b[A-Za-z_][\w]*(?:\.[A-Za-z_][\w]*)+\b")
_PATH_RE = re.compile(r"\b[\w./-]+\.py\b")
_HANDLE_RE = re.compile(r"@([A-Za-z][\w-]*)")


def _risk_badge(label: str) -> str:
    """Title-case risk label for the badge heading."""
    return str(label or "low").strip().capitalize()


def _format_risk_section(decision: Dict[str, Any]) -> List[str]:
    """Render risk badge, score, factor breakdown, and optional note."""
    risk = decision.get("risk") or {}
    factors = risk.get("factors") or {}
    label = _risk_badge(str(risk.get("label", "low")))
    score = risk.get("score", 0.0)
    lines = [
        f"## Risk: {label} ({score})",
        "",
        "| Factor | Contribution |",
        "| --- | ---: |",
        f"| Blast radius | {factors.get('blast_component', 0.0)} |",
        f"| PageRank | {factors.get('pagerank_component', 0.0)} |",
        f"| Uncovered tests | {factors.get('uncovered_component', 0.0)} |",
        f"| Churn | {factors.get('churn_component', 0.0)} |",
    ]
    note = (decision.get("section_notes") or {}).get("risk")
    if note:
        lines.extend(["", f"> {note}"])
    return lines


def _format_path(path: Any) -> str:
    """Render a call-path list as a readable arrow chain."""
    if isinstance(path, list):
        return " → ".join(str(p) for p in path)
    return str(path)


def _format_blast_section(decision: Dict[str, Any]) -> List[str]:
    """Render affected callers with hop counts and graph paths."""
    lines = ["## Affected Callers (Blast radius)", ""]
    blast = decision.get("blast_radius") or []
    if not blast:
        lines.append("_No callers identified._")
    else:
        for row in blast:
            affected = row.get("affected", "?")
            hops = row.get("hops", "?")
            path = _format_path(row.get("path", []))
            lines.append(f"- `{affected}` ({hops} hop(s)): `{path}`")
    note = (decision.get("section_notes") or {}).get("blast")
    if note:
        lines.extend(["", f"> {note}"])
    return lines


def _test_files(tests: Iterable[Dict[str, Any]]) -> List[str]:
    """Unique test file paths preserving first-seen order."""
    seen: Set[str] = set()
    ordered: List[str] = []
    for t in tests:
        path = str(t.get("file") or "").strip()
        if path and path not in seen:
            seen.add(path)
            ordered.append(path)
    return ordered


def _format_tests_section(decision: Dict[str, Any]) -> List[str]:
    """Render tests-to-run list, pytest block, or no-test finding."""
    lines = ["## Tests to Run", ""]
    tests = decision.get("affected_tests") or []
    if not tests:
        lines.append("**Finding:** No test reaches this change")
    else:
        for t in tests:
            name = t.get("test", "?")
            path = t.get("file", "?")
            hops = t.get("hops", "?")
            lines.append(f"- `{name}` (`{path}`, {hops} hop(s))")
        files = _test_files(tests)
        cmd = "pytest " + " ".join(files) if files else "pytest"
        lines.extend(["", "```bash", cmd, "```"])
    note = (decision.get("section_notes") or {}).get("tests")
    if note:
        lines.extend(["", f"> {note}"])
    return lines


def _format_reviewers_section(decision: Dict[str, Any]) -> List[str]:
    """Render ranked reviewers with coverage, commits, and score."""
    lines = ["## Suggested Reviewers", ""]
    reviewers = decision.get("reviewers") or []
    if not reviewers:
        lines.append("_No reviewer candidates found._")
    else:
        for i, r in enumerate(reviewers, start=1):
            name = r.get("author", "?")
            files = r.get("files_covered", 0)
            commits = r.get("commits", 0)
            score = r.get("score", 0.0)
            lines.append(
                f"{i}. **{name}** — files covered: {files}, "
                f"commits: {commits}, score: {score}"
            )
    note = (decision.get("section_notes") or {}).get("reviewers")
    if note:
        lines.extend(["", f"> {note}"])
    return lines


def _format_evidence_section(decision: Dict[str, Any]) -> List[str]:
    """Render collapsible Cypher evidence with query runtimes."""
    lines = [
        "## Graph Evidence",
        "",
        "<details>",
        "<summary>Cypher queries and runtimes</summary>",
        "",
    ]
    evidence = decision.get("evidence") or []
    if not evidence:
        lines.append("_No query evidence recorded._")
    else:
        for ev in evidence:
            ms = ev.get("duration_ms", 0)
            cypher = str(ev.get("cypher", "")).strip()
            lines.append(f"**{ms} ms**")
            lines.extend(["", "```cypher", cypher, "```", ""])
    lines.append("</details>")
    return lines


def format_pr_comment(decision: Dict[str, Any]) -> str:
    """Render a GitHub PR comment from a validated decision object."""
    safe = validate_decision(decision)
    parts: List[str] = [MARKER, ""]
    summary = safe.get("summary")
    if summary:
        parts.extend([str(summary), ""])
    parts.extend(_format_risk_section(safe))
    parts.append("")
    parts.extend(_format_blast_section(safe))
    parts.append("")
    parts.extend(_format_tests_section(safe))
    parts.append("")
    parts.extend(_format_reviewers_section(safe))
    parts.append("")
    parts.extend(_format_evidence_section(safe))
    parts.append("")
    return "\n".join(parts)


def _add_token(allowed: Set[str], value: Any) -> None:
    """Add a non-empty string token to the allowed set."""
    if value is None:
        return
    text = str(value).strip()
    if text:
        allowed.add(text)


def _add_path_nodes(allowed: Set[str], path: Any) -> None:
    """Add each node in a call-path list to the allowed set."""
    if isinstance(path, list):
        for node in path:
            _add_token(allowed, node)
    else:
        _add_token(allowed, path)


def _collect_evidence_tokens(allowed: Set[str], ev: Dict[str, Any]) -> None:
    """Harvest allowed names from evidence params and optional rows."""
    params = ev.get("params") or {}
    for key in ("changed", "files", "path", "test", "changed_fn"):
        val = params.get(key)
        if isinstance(val, list):
            for item in val:
                _add_token(allowed, item)
        else:
            _add_token(allowed, val)
    for row in ev.get("rows") or []:
        if not isinstance(row, dict):
            continue
        for val in row.values():
            if isinstance(val, list):
                _add_path_nodes(allowed, val)
            else:
                _add_token(allowed, val)


def _collect_allowed(decision: Dict[str, Any]) -> Set[str]:
    """Build the set of graph-backed names the LLM may mention."""
    allowed: Set[str] = set()
    for fn in decision.get("changed_functions") or []:
        _add_token(allowed, fn)
    for path in decision.get("files_changed") or []:
        _add_token(allowed, path)
    for row in decision.get("blast_radius") or []:
        _add_token(allowed, row.get("affected"))
        _add_token(allowed, row.get("via"))
        _add_path_nodes(allowed, row.get("path"))
    for row in decision.get("affected_tests") or []:
        _add_token(allowed, row.get("test"))
        _add_token(allowed, row.get("file"))
    for path in (decision.get("test_proof_paths") or {}).values():
        _add_path_nodes(allowed, path)
    for row in decision.get("reviewers") or []:
        _add_token(allowed, row.get("author"))
    for row in decision.get("centrality") or []:
        _add_token(allowed, row.get("fn"))
    for ev in decision.get("evidence") or []:
        _collect_evidence_tokens(allowed, ev)
    return allowed


def _collapse_spaces(text: str) -> str:
    """Normalize whitespace left after token removal."""
    cleaned = re.sub(r"[ \t]{2,}", " ", text)
    cleaned = re.sub(r" +([,.;:])", r"\1", cleaned)
    return cleaned.strip()


def _sanitize_text(text: str, allowed: Set[str], people: Set[str]) -> str:
    """Strip qnames, paths, and @handles absent from graph evidence."""
    if not text:
        return text
    people_l = {p.lower() for p in people}

    def repl_qname(match: re.Match[str]) -> str:
        token = match.group(0)
        return token if token in allowed else ""

    def repl_path(match: re.Match[str]) -> str:
        token = match.group(0)
        return token if token in allowed else ""

    def repl_handle(match: re.Match[str]) -> str:
        handle = match.group(1)
        if handle in people or handle.lower() in people_l:
            return match.group(0)
        return ""

    cleaned = _QNAME_RE.sub(repl_qname, text)
    cleaned = _PATH_RE.sub(repl_path, cleaned)
    cleaned = _HANDLE_RE.sub(repl_handle, cleaned)
    return _collapse_spaces(cleaned)


def _sanitize_notable_paths(paths: List[Any], allowed: Set[str]) -> List[Any]:
    """Drop notable paths that include any non-allowed node."""
    kept: List[Any] = []
    for path in paths:
        if isinstance(path, list):
            if all(str(n) in allowed for n in path):
                kept.append(path)
        elif str(path) in allowed:
            kept.append(path)
    return kept


def validate_decision(decision: Dict[str, Any]) -> Dict[str, Any]:
    """Drop LLM mentions of functions/tests/files/people absent from evidence."""
    out = copy.deepcopy(decision)
    allowed = _collect_allowed(out)
    people = {
        str(r.get("author", "")).strip()
        for r in (out.get("reviewers") or [])
        if r.get("author")
    }

    if isinstance(out.get("summary"), str):
        out["summary"] = _sanitize_text(out["summary"], allowed, people)

    notes = out.get("section_notes")
    if isinstance(notes, dict):
        out["section_notes"] = {
            key: (
                _sanitize_text(val, allowed, people)
                if isinstance(val, str)
                else val
            )
            for key, val in notes.items()
        }

    if isinstance(out.get("notable_paths"), list):
        out["notable_paths"] = _sanitize_notable_paths(
            out["notable_paths"], allowed
        )
    return out
