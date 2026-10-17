"""System prompts, templates, and LLM invocation for ImpactGraph."""

import os
from typing import Any, Dict, List, Optional

SYSTEM_PROMPT = """You are ImpactGraph, a change-impact agent. Facts come from a code graph in FalkorDB, accessed ONLY through the provided tools. Your job is to decide what to check, interpret the results, and explain them to a maintainer.

Tools: map_diff_to_functions, get_blast_radius, get_affected_tests, find_reviewers, get_risk, explain_path, get_most_central(limit <= 20).

Rules:
1. Call map_diff_to_functions first.
2. Then call get_blast_radius, get_affected_tests, find_reviewers and get_risk. Use explain_path / get_most_central when helpful.
3. Never invent function names, files, tests or people. Confirm every name passed to a tool exists in a prior tool result. Unknown names → outcome unknown_name (no analysis query).
4. Never estimate or compute risk yourself. Report the score returned by get_risk and explain what drives it.
5. An empty result means "not modelled", not "no impact". Never say "nothing breaks" or "safe". Empty blast → "nothing found in the graph, which may mean the call link is not modelled".
6. "No test reaches this change" is a finding that raises risk, not an error.
7. Surface tool outcomes: answered_with_path | not_in_graph | unknown_name | cached.
8. When reviewer candidates are close, pick the best fit using only the returned evidence and say why in one sentence.
9. For each section write one short why-it-matters line.
10. Finish with JSON: {summary, section_notes: {blast, tests, reviewers, risk}, notable_paths}
No code review comments, no style opinions.
For POST /ask, discard any answer mentioning a function, test, file, or person absent from tool-result rows and replace it with a template built from those rows.
Read-only queries use ro_query; only ingestion/PageRank storage may write."""


def generate_template_summary(data: Dict[str, Any]) -> Dict[str, Any]:
    """Deterministic fallback explanation when LLM is unavailable or offline."""
    changed_count = len(data.get("changed_functions", []))
    blast_count = len(data.get("blast_radius", []))
    test_count = len(data.get("affected_tests", []))
    risk_info = data.get("risk", {})
    score = risk_info.get("score", 0.0)
    label = risk_info.get("label", "low").upper()

    summary = (
        f"Change modifies {changed_count} function(s) with a blast radius of {blast_count} "
        f"caller(s). Assessed as {label} risk (score: {score}) with {test_count} reaching test(s)."
    )

    notes = {
        "blast": (
            f"{blast_count} direct and indirect caller(s) identified in call graph."
            if blast_count > 0
            else (
                "nothing found in the graph, which may mean the call link is not modelled"
            )
        ),
        "tests": (
            f"{test_count} existing test(s) reach this change."
            if test_count > 0
            else "No test reaches this change (finding: potential regression risk)."
        ),
        "reviewers": (
            f"Top reviewers ranked by historical commit frequency and recency on changed files."
        ),
        "risk": (
            f"Score {score} ({label}) driven by blast ratio, PageRank centrality, and test coverage."
        ),
    }

    return {
        "summary": summary,
        "section_notes": notes,
        "notable_paths": [r["path"] for r in data.get("blast_radius", [])[:3] if "path" in r],
    }


def llm_call(prompt: str, system_prompt: str = SYSTEM_PROMPT) -> Optional[str]:
    """Single swappable LLM caller with fallback chain."""
    api_key = os.environ.get("LLM_API_KEY")
    if not api_key:
        return None

    # Placeholder for primary LLM call (e.g. Gemini / Claude)
    # If connection fails or key is invalid, returns None to trigger template fallback
    return None
