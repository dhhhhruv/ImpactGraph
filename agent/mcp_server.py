"""ImpactGraph MCP server: the graph tools exposed over MCP (stdio).

Call set_diff first (repo + diff hunks), then any of the 7 graph tools.
Run: FALKOR_HOST=localhost ./.venv/bin/python -m agent.mcp_server
"""

import os
from typing import Any, Dict, List, Optional

from mcp.server.fastmcp import FastMCP

from agent.tools import ToolBox
from graph.client import GraphClient

mcp = FastMCP("impactgraph")
_state: Dict[str, Optional[ToolBox]] = {"tb": None}


def _client(repo: str) -> GraphClient:
    graph_name = f"impact_{repo.replace('/', '_').replace('-', '_')}"
    host = os.environ.get("FALKOR_HOST", "localhost")
    port = int(os.environ.get("FALKOR_PORT", 6379))
    return GraphClient(host=host, port=port, graph_name=graph_name)


def _run(name: str, args: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    tb = _state["tb"]
    if tb is None:
        return {"outcome": "error", "message": "call set_diff first"}
    return tb.call(name, args or {})


@mcp.tool()
def set_diff(repo: str, diff_hunks: List[Dict[str, Any]]) -> Dict[str, Any]:
    """Start an analysis. repo like 'borgbase/vorta'; diff_hunks like [{"path": "src/x.py", "start": 1, "end": 99}]. Call first."""
    _state["tb"] = ToolBox(_client(repo), diff_hunks)
    return {"outcome": "ready", "repo": repo, "hunks": len(diff_hunks)}


@mcp.tool()
def map_diff_to_functions() -> Dict[str, Any]:
    """Map this PR's diff to changed functions in the graph. Call after set_diff."""
    return _run("map_diff_to_functions")


@mcp.tool()
def get_blast_radius(max_hops: int = 4) -> Dict[str, Any]:
    """Callers affected by the changed functions, with call paths (max_hops 1 to 6)."""
    return _run("get_blast_radius", {"max_hops": max_hops})


@mcp.tool()
def get_affected_tests(max_hops: int = 4) -> Dict[str, Any]:
    """Tests that reach the changed functions, with proof paths (max_hops 1 to 6)."""
    return _run("get_affected_tests", {"max_hops": max_hops})


@mcp.tool()
def find_reviewers() -> Dict[str, Any]:
    """Rank reviewer candidates by history on the changed files."""
    return _run("find_reviewers")


@mcp.tool()
def get_risk() -> Dict[str, Any]:
    """Risk score. Needs get_blast_radius and get_affected_tests first."""
    return _run("get_risk")


@mcp.tool()
def explain_path(from_function: str, to_function: str) -> Dict[str, Any]:
    """Shortest call path between two functions that exist in the graph."""
    return _run("explain_path", {"from_function": from_function, "to_function": to_function})


@mcp.tool()
def get_most_central(limit: int = 10) -> Dict[str, Any]:
    """Most central functions by PageRank (limit up to 20)."""
    return _run("get_most_central", {"limit": limit})


if __name__ == "__main__":
    mcp.run()
