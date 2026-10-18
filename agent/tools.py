"""Graph tools for the ImpactGraph agent. Every name is checked against the graph."""

import time
from typing import Any, Dict, List, Optional

from agent.loop import (
    OUTCOME_ANSWERED, OUTCOME_NOT_IN_GRAPH, OUTCOME_UNKNOWN,
    compute_agent_risk, gather_test_paths, map_diffs,
)
from graph.queries import (
    confirm_names, explain_path, q1_blast_radius, q2a_affected_tests,
    q3_find_reviewers, q4_centrality, q5_recent_churn, q_most_central,
)

MAX_ROWS = 15

TOOL_SPECS: List[Dict[str, Any]] = [
    {"name": "map_diff_to_functions",
     "description": "Map this PR's diff to changed functions in the graph. Call first. No arguments.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_blast_radius",
     "description": "Callers affected by the changed functions, with call paths.",
     "parameters": {"type": "object", "properties": {
         "max_hops": {"type": "integer", "description": "1 to 6, default 4"}}}},
    {"name": "get_affected_tests",
     "description": "Tests that reach the changed functions, with proof paths.",
     "parameters": {"type": "object", "properties": {
         "max_hops": {"type": "integer", "description": "1 to 6, default 4"}}}},
    {"name": "find_reviewers",
     "description": "Rank reviewer candidates by history on the changed files.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "get_risk",
     "description": "Risk score from blast radius, centrality, coverage, churn. Needs get_blast_radius and get_affected_tests first.",
     "parameters": {"type": "object", "properties": {}}},
    {"name": "explain_path",
     "description": "Shortest call path between two functions that exist in the graph.",
     "parameters": {"type": "object", "properties": {
         "from_function": {"type": "string"}, "to_function": {"type": "string"}},
         "required": ["from_function", "to_function"]}},
    {"name": "get_most_central",
     "description": "Most central functions by PageRank (limit up to 20).",
     "parameters": {"type": "object", "properties": {"limit": {"type": "integer"}}}},
]


class ToolBox:
    def __init__(self, client, diff_hunks, before_ts: Optional[int] = None,
                 pr_author: Optional[str] = None):
        self.client = client
        self.hunks = diff_hunks
        self.ts = before_ts if before_ts is not None else int(time.time())
        self.pr_author = pr_author
        self.changed: List[str] = []
        self.files: List[str] = []
        self.blast: Optional[List[Dict[str, Any]]] = None
        self.tests: Optional[List[Dict[str, Any]]] = None
        self.test_paths: Dict[str, List[str]] = {}
        self.reviewers: List[Dict[str, Any]] = []
        self.centrality: List[Dict[str, Any]] = []
        self.churn = 0
        self.risk: Optional[Dict[str, Any]] = None
        self.map_result: Dict[str, Any] = {}
        self.log: List[Dict[str, Any]] = []

    def _resolve(self, name: str):
        if confirm_names(self.client, functions=[name])["ok"]:
            return name, None
        rows, _ = self.client.ro_query(
            "MATCH (f:Function) WHERE f.qname ENDS WITH $s RETURN f.qname AS qname LIMIT 5",
            {"s": "." + name},
        )
        found = [str(r.get("qname")) for r in rows]
        if len(found) == 1:
            return found[0], None
        return None, {"outcome": OUTCOME_UNKNOWN, "name": name, "candidates": found,
                      "message": "name is not an exact graph name; pick one candidate or stop"}

    def _need_changed(self):
        if not self.changed:
            return {"outcome": "not_ready", "message": "call map_diff_to_functions first, or it found no functions"}
        return None

    def map_diff_to_functions(self) -> Dict[str, Any]:
        self.map_result = map_diffs(self.client, self.hunks)
        self.changed = list(self.map_result.get("changed_functions") or [])
        self.files = list(self.map_result.get("known_files") or [])
        return {"outcome": self.map_result.get("outcome"), "changed_functions": self.changed,
                "files": self.files, "unknown_files": self.map_result.get("unknown_files", [])}

    def get_blast_radius(self, max_hops: int = 4) -> Dict[str, Any]:
        bad = self._need_changed()
        if bad:
            return bad
        hops = max(1, min(int(max_hops), 6))
        self.blast, _ = q1_blast_radius(self.client, self.changed, max_hops=hops)
        return {"outcome": OUTCOME_ANSWERED if self.blast else OUTCOME_NOT_IN_GRAPH,
                "total": len(self.blast), "rows": self.blast[:MAX_ROWS],
                "message": None if self.blast else "nothing found in the graph, which may mean the call link is not modelled"}

    def get_affected_tests(self, max_hops: int = 4) -> Dict[str, Any]:
        bad = self._need_changed()
        if bad:
            return bad
        hops = max(1, min(int(max_hops), 6))
        self.tests = q2a_affected_tests(self.client, self.changed, max_hops=hops)
        self.test_paths = gather_test_paths(self.client, self.tests, self.changed)
        return {"outcome": OUTCOME_ANSWERED if self.tests else OUTCOME_NOT_IN_GRAPH,
                "total": len(self.tests), "capped_at_30": len(self.tests) >= 30,
                "rows": self.tests[:MAX_ROWS],
                "message": None if self.tests else "No test reaches this change (finding, raises risk)"}

    def find_reviewers(self) -> Dict[str, Any]:
        if not self.files:
            return {"outcome": "not_ready", "message": "call map_diff_to_functions first"}
        if self.pr_author is not None and not confirm_names(self.client, people=[self.pr_author])["ok"]:
            return {"outcome": OUTCOME_UNKNOWN, "message": "PR author not in graph"}
        self.reviewers = q3_find_reviewers(self.client, self.files, before_ts=self.ts, pr_author=self.pr_author)
        return {"outcome": OUTCOME_ANSWERED if self.reviewers else OUTCOME_NOT_IN_GRAPH,
                "rows": self.reviewers[:5]}

    def get_risk(self) -> Dict[str, Any]:
        if self.blast is None or self.tests is None:
            return {"outcome": "not_ready", "message": "call get_blast_radius and get_affected_tests first"}
        self.centrality = q4_centrality(self.client, self.changed)
        self.churn = q5_recent_churn(self.client, self.files, since_ts=self.ts - 90 * 86400, before_ts=self.ts)
        self.risk = compute_agent_risk(self.blast, self.centrality, self.tests, self.churn, len(self.changed))
        return {"outcome": OUTCOME_ANSWERED, "risk": self.risk, "recent_churn": self.churn}

    def explain_path(self, from_function: str, to_function: str) -> Dict[str, Any]:
        a, bad = self._resolve(from_function)
        if bad:
            return bad
        b, bad = self._resolve(to_function)
        if bad:
            return bad
        path = explain_path(self.client, a, b)
        return {"outcome": OUTCOME_ANSWERED if path else OUTCOME_NOT_IN_GRAPH, "path": path}

    def get_most_central(self, limit: int = 10) -> Dict[str, Any]:
        rows = q_most_central(self.client, max(1, min(int(limit), 20)))
        return {"outcome": OUTCOME_ANSWERED if rows else OUTCOME_NOT_IN_GRAPH, "rows": rows}

    def call(self, name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
        args = args or {}
        fn = getattr(self, name, None) if name in {s["name"] for s in TOOL_SPECS} else None
        if fn is None:
            result = {"outcome": "error", "message": f"unknown tool {name}"}
        else:
            try:
                result = fn(**args)
            except Exception as e:  # keep the loop alive; the model sees the error
                result = {"outcome": "error", "message": f"{type(e).__name__}: {str(e)[:200]}"}
        self.log.append({"tool": name, "args": args, "outcome": result.get("outcome")})
        return result
