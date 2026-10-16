"""Bulk-load ImpactGraph into FalkorDB from a parsed Python repo."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Sequence

from ingest.ast_parser import BATCH_SIZE, RepoGraph, parse_repo

INDEX_QUERIES: List[str] = [
    "CREATE INDEX FOR (f:Function) ON (f.qname)",
    "CREATE INDEX FOR (f:Function) ON (f.file)",
    "CREATE INDEX FOR (f:File) ON (f.path)",
    "CREATE INDEX FOR (c:Commit) ON (c.ts)",
]

Q_LOAD_FILES = """
UNWIND $batch AS row
MERGE (f:File {path: row.path})
SET f.loc = row.loc
"""

Q_LOAD_FUNCTIONS = """
UNWIND $batch AS row
MERGE (fn:Function {qname: row.qname})
SET fn.name = row.name,
    fn.file = row.file,
    fn.start = row.start,
    fn.end = row.end,
    fn.pagerank = 0.0
"""

Q_LOAD_TESTS = """
UNWIND $batch AS row
MATCH (fn:Function {qname: row.qname})
SET fn:Test
"""

Q_LOAD_DEFINES = """
UNWIND $batch AS row
MATCH (f:File {path: row.file})
MATCH (fn:Function {qname: row.qname})
MERGE (f)-[:DEFINES]->(fn)
"""

Q_LOAD_CALLS = """
UNWIND $batch AS row
MATCH (a:Function {qname: row.caller})
MATCH (b:Function {qname: row.callee})
MERGE (a)-[:CALLS]->(b)
"""

Q_LOAD_IMPORTS = """
UNWIND $batch AS row
MATCH (a:File {path: row.src})
MATCH (b:File {path: row.dst})
MERGE (a)-[:IMPORTS]->(b)
"""

Q_LOAD_AUTHORS = """
UNWIND $batch AS row
MERGE (a:Author {email: row.email})
SET a.name = row.name
"""

Q_LOAD_COMMITS = """
UNWIND $batch AS row
MERGE (c:Commit {sha: row.sha})
SET c.ts = row.ts, c.msg = row.msg
"""

Q_LOAD_AUTHORED = """
UNWIND $batch AS row
MATCH (a:Author {email: row.email})
MATCH (c:Commit {sha: row.sha})
MERGE (a)-[:AUTHORED]->(c)
"""

Q_LOAD_TOUCHED = """
UNWIND $batch AS row
MATCH (c:Commit {sha: row.sha})
MATCH (f:File {path: row.path})
MERGE (c)-[:TOUCHED {added: row.added, deleted: row.deleted}]->(f)
"""

Q_PAGERANK = """
CALL algo.pageRank('Function', 'CALLS') YIELD node, score
SET node.pagerank = score
"""

Q_CALLS_EDGES = """
MATCH (a:Function)-[:CALLS]->(b:Function)
RETURN a.qname AS caller, b.qname AS callee
"""

Q_SET_PAGERANK = """
UNWIND $batch AS row
MATCH (fn:Function {qname: row.qname})
SET fn.pagerank = row.pagerank
"""

Q_COUNT_NODES = """
MATCH (n)
RETURN labels(n) AS labels, count(*) AS cnt
"""

Q_COUNT_EDGES = """
MATCH ()-[r]->()
RETURN type(r) AS type, count(*) AS cnt
"""


def connect_falkor(host: str = "localhost", port: int = 6379) -> Any:
    """Open a FalkorDB client."""
    from falkordb import FalkorDB

    return FalkorDB(host=host, port=port)


def graph_name_for_repo(repo: str) -> str:
    """Map owner/repo to impact_owner_repo graph name."""
    owner, name = repo.split("/", 1)
    return f"impact_{owner}_{name}"


def select_graph(client: Any, name: str, rebuild: bool = False) -> Any:
    """Select a graph, optionally deleting it first on --rebuild."""
    if rebuild:
        try:
            existing = client.select_graph(name)
            existing.delete()
        except Exception:
            pass
    return client.select_graph(name)


def create_indexes(graph: Any) -> None:
    """Create schema indexes from queries.cypher (ignore already-exists)."""
    for cypher in INDEX_QUERIES:
        try:
            graph.query(cypher)
        except Exception:
            continue


def _chunks(rows: Sequence[Dict[str, Any]], size: int = BATCH_SIZE) -> Iterable[List]:
    """Yield successive batches of at most `size` rows."""
    for i in range(0, len(rows), size):
        yield list(rows[i : i + size])


def unwind_load(graph: Any, cypher: str, rows: Sequence[Dict[str, Any]]) -> None:
    """Run an UNWIND $batch load query in batches of BATCH_SIZE."""
    if not rows:
        return
    for batch in _chunks(rows, BATCH_SIZE):
        graph.query(cypher, {"batch": batch})


def load_ast_graph(graph: Any, data: RepoGraph) -> None:
    """Bulk-load File/Function nodes and DEFINES/CALLS/IMPORTS edges."""
    unwind_load(graph, Q_LOAD_FILES, data.files)
    unwind_load(graph, Q_LOAD_FUNCTIONS, data.functions)
    tests = [f for f in data.functions if f.get("is_test")]
    unwind_load(graph, Q_LOAD_TESTS, tests)
    unwind_load(graph, Q_LOAD_DEFINES, data.defines)
    unwind_load(graph, Q_LOAD_CALLS, data.calls)
    unwind_load(graph, Q_LOAD_IMPORTS, data.imports)


def load_history_graph(graph: Any, history: Dict[str, Any]) -> None:
    """Bulk-load Author/Commit nodes and AUTHORED/TOUCHED edges."""
    unwind_load(graph, Q_LOAD_AUTHORS, history.get("authors", []))
    unwind_load(graph, Q_LOAD_COMMITS, history.get("commits", []))
    unwind_load(graph, Q_LOAD_AUTHORED, history.get("authored", []))
    unwind_load(graph, Q_LOAD_TOUCHED, history.get("touched", []))


def _pagerank_networkx(graph: Any) -> None:
    """Compute PageRank with networkx and write scores onto Function nodes."""
    import networkx as nx

    result = graph.query(Q_CALLS_EDGES)
    rows = result.result_set if hasattr(result, "result_set") else []
    g = nx.DiGraph()
    for row in rows or []:
        caller, callee = row[0], row[1]
        g.add_edge(caller, callee)
    if g.number_of_nodes() == 0:
        return
    scores = nx.pagerank(g)
    payload = [{"qname": q, "pagerank": float(s)} for q, s in scores.items()]
    unwind_load(graph, Q_SET_PAGERANK, payload)


def compute_pagerank(graph: Any) -> None:
    """Run FalkorDB PageRank, falling back to networkx if unavailable."""
    try:
        graph.query(Q_PAGERANK)
    except Exception:
        _pagerank_networkx(graph)


def print_counts(graph: Any) -> None:
    """Print node counts per label and edge counts per type."""
    nodes = graph.query(Q_COUNT_NODES)
    print("Nodes:")
    for row in nodes.result_set or []:
        print(f"  {row[0]}: {row[1]}")
    edges = graph.query(Q_COUNT_EDGES)
    print("Edges:")
    for row in edges.result_set or []:
        print(f"  {row[0]}: {row[1]}")


def resolve_repo_path(repo: str, src: Optional[str]) -> Path:
    """Locate a local checkout for owner/repo."""
    if src:
        path = Path(src)
        if not path.is_dir():
            raise FileNotFoundError(f"repo path not found: {src}")
        return path
    name = repo.split("/", 1)[-1]
    for candidate in (Path(name), Path("repos") / name, Path("..") / name):
        if candidate.is_dir():
            return candidate.resolve()
    raise FileNotFoundError(
        f"could not find local clone for {repo}; pass --src /path/to/{name}"
    )


def _try_load_history(repo_path: Path) -> Optional[Dict[str, Any]]:
    """Optionally extract git history when ingest.git_history is available."""
    try:
        from ingest.git_history import extract_history  # type: ignore
    except ImportError:
        return None
    return extract_history(repo_path)


def ingest_repo(
    repo: str,
    src: Optional[str] = None,
    rebuild: bool = False,
    host: str = "localhost",
    port: int = 6379,
) -> Any:
    """Parse, index, bulk-load, and PageRank one repository graph."""
    repo_path = resolve_repo_path(repo, src)
    data = parse_repo(repo_path)
    client = connect_falkor(host=host, port=port)
    graph = select_graph(client, graph_name_for_repo(repo), rebuild=rebuild)
    create_indexes(graph)
    load_ast_graph(graph, data)
    history = _try_load_history(repo_path)
    if history:
        load_history_graph(graph, history)
    compute_pagerank(graph)
    print_counts(graph)
    return graph


def build_arg_parser() -> argparse.ArgumentParser:
    """CLI for python -m ingest.load_graph."""
    p = argparse.ArgumentParser(description="Load ImpactGraph into FalkorDB")
    p.add_argument("--repo", required=True, help="owner/repo (graph impact_owner_repo)")
    p.add_argument("--rebuild", action="store_true", help="delete and reload the graph")
    p.add_argument("--src", default=None, help="local path to the repository checkout")
    p.add_argument("--host", default="localhost")
    p.add_argument("--port", type=int, default=6379)
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Entrypoint: python -m ingest.load_graph --repo owner/repo --rebuild."""
    args = build_arg_parser().parse_args(argv)
    ingest_repo(
        repo=args.repo,
        src=args.src,
        rebuild=args.rebuild,
        host=args.host,
        port=args.port,
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
