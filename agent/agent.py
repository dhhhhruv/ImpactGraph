"""Model-driven agent: Gemini picks graph tools; the decision is built only from tool state."""

import json
import os
import re
import time
import urllib.error
import urllib.request
from typing import Any, Dict, List, Optional

from agent.loop import run_impact_agent
from agent.prompts import SYSTEM_PROMPT, generate_template_summary
from agent.tools import TOOL_SPECS, ToolBox

MAX_STEPS = 8
URL = "https://generativelanguage.googleapis.com/v1beta/models/{m}:generateContent"


def _api_key() -> Optional[str]:
    k = os.environ.get("LLM_API_KEY", "").strip().strip("\"'")
    return k or None


def _call_model(contents: List[Dict[str, Any]], key: str, model: str) -> Dict[str, Any]:
    body = {
        "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
        "contents": contents,
        "tools": [{"functionDeclarations": TOOL_SPECS}],
    }
    req = urllib.request.Request(
        URL.format(m=model), data=json.dumps(body).encode(),
        headers={"x-goog-api-key": key, "Content-Type": "application/json"},
    )
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.load(r)


def _call_with_retry(contents, key, model):
    fallback_model = os.environ.get("LLM_MODEL_FALLBACK", "").strip() or "gemini-3.5-flash"
    last = None
    for m, waits in ((model, (0, 2, 5)), (fallback_model, (0,))):
        for w in waits:
            if w:
                time.sleep(w)
            try:
                return _call_model(contents, key, m)
            except urllib.error.HTTPError as e:
                last = e
                if e.code not in (429, 500, 503):
                    raise
                if e.code == 429:
                    break  # quota: waiting will not help, try the next model
    raise last


FENCE = "\x60" * 3


def _extract_notes(text: str):
    """Pull the JSON object the model was told to finish with; None if absent or invalid."""
    m = re.search(FENCE + r"json\s*(\{.*\})\s*" + FENCE, text, re.S)
    raw = m.group(1) if m else None
    if raw is None:
        s, e = text.find("{"), text.rfind("}")
        raw = text[s:e + 1] if s != -1 and e > s else None
    if not raw:
        return None
    try:
        d = json.loads(raw)
    except ValueError:
        return None
    return d if isinstance(d, dict) and isinstance(d.get("summary"), str) else None


def _grounded(text: str, evidence: str) -> bool:
    names = [n.rstrip(".") for n in re.findall(r"\b(?:src|tests)\.[A-Za-z0-9_.]+", text)]
    return all(n in evidence for n in names)


def run_agent(client, diff_hunks, head_sha="HEAD", before_ts=None, pr_author=None,
              max_hops=4) -> Dict[str, Any]:
    def fallback(reason: str) -> Dict[str, Any]:
        d = run_impact_agent(client, diff_hunks, head_sha=head_sha, before_ts=before_ts,
                             pr_author=pr_author, max_hops=max_hops)
        d["agent_mode"] = "fixed_pipeline"
        d["agent_note"] = reason
        return d

    key = _api_key()
    if not key:
        return fallback("no LLM_API_KEY set")
    model = os.environ.get("LLM_MODEL", "").strip() or "gemini-3.6-flash"
    tb = ToolBox(client, diff_hunks, before_ts=before_ts, pr_author=pr_author)
    contents: List[Dict[str, Any]] = [{"role": "user", "parts": [{"text":
        "Analyze this pull request using the tools. Decide the order yourself, "
        "then finish with a short grounded summary."}]}]
    final_text = ""
    evidence_text = ""
    try:
        for _ in range(MAX_STEPS):
            resp = _call_with_retry(contents, key, model)
            content = resp["candidates"][0]["content"]
            contents.append(content)
            calls = [p["functionCall"] for p in content.get("parts", []) if "functionCall" in p]
            if not calls:
                final_text = " ".join(p.get("text", "") for p in content.get("parts", []))
                break
            parts = []
            for c in calls:
                args = dict(c.get("args") or {})
                if c["name"] in ("get_blast_radius", "get_affected_tests"):
                    args["max_hops"] = max_hops
                result = tb.call(c["name"], args)
                evidence_text += json.dumps(result, default=str)
                parts.append({"functionResponse": {"name": c["name"], "response": {"result": result}}})
            contents.append({"role": "user", "parts": parts})
    except (urllib.error.URLError, KeyError, IndexError, ValueError, TimeoutError) as e:
        detail = type(e).__name__
        if isinstance(e, urllib.error.HTTPError):
            try:
                detail += f" {e.code}: " + e.read().decode()[:300].replace(key, "XXX")
            except Exception:
                detail += f" {e.code}"
        return fallback(f"model call failed: {detail}")

    if tb.blast is None or tb.tests is None or tb.risk is None:
        return fallback("model did not complete blast, tests and risk")

    outcomes = {
        "map_diff": str(tb.map_result.get("outcome")),
        "blast": "answered_with_path" if tb.blast else "not_in_graph",
        "tests": "answered_with_path" if tb.tests else "not_in_graph",
        "reviewers": "answered_with_path" if tb.reviewers else "not_in_graph",
        "centrality": "answered_with_path" if tb.centrality else "not_in_graph",
        "churn": "answered_with_path" if tb.files else "not_in_graph",
        "risk": "answered_with_path",
    }
    decision: Dict[str, Any] = {
        "head_sha": head_sha, "files_changed": tb.files, "changed_functions": tb.changed,
        "blast_radius": tb.blast, "affected_tests": tb.tests, "test_proof_paths": tb.test_paths,
        "reviewers": tb.reviewers, "centrality": tb.centrality, "recent_churn": tb.churn,
        "risk": tb.risk, "max_hops": max_hops, "outcomes": outcomes,
        "outcome": outcomes["map_diff"],
        "evidence": [ev.to_dict() for ev in client.evidence_log],
        "agent_mode": "model", "agent_model": model, "agent_trace": tb.log,
    }
    decision.update(generate_template_summary(decision))
    notes = _extract_notes(final_text) if final_text else None
    if notes and _grounded(json.dumps(notes), evidence_text):
        decision["agent_notes"] = notes["summary"]
        if isinstance(notes.get("section_notes"), dict):
            decision["agent_section_notes"] = notes["section_notes"]
    return decision
