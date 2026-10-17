"""Tests for graph writes and PageRank fallback boundaries."""

import sys
from types import ModuleType, SimpleNamespace

from ingest.load_graph import (
    Q_CALLS_EDGES,
    Q_LOAD_CALLS,
    Q_PAGERANK,
    Q_SET_PAGERANK,
    _pagerank_networkx,
    compute_pagerank,
    print_counts,
)


class FakeGraph:
    def __init__(self):
        self.reads = []
        self.writes = []

    def ro_query(self, cypher, params=None):
        self.reads.append((cypher, params))
        if cypher == Q_CALLS_EDGES:
            return SimpleNamespace(result_set=[["pkg.a", "pkg.b", "CALLS"]])
        return SimpleNamespace(result_set=[])

    def query(self, cypher, params=None):
        self.writes.append((cypher, params))
        return SimpleNamespace(result_set=[])


def test_calls_edges_are_merged_on_ingest():
    """Repeated ingestion must not create parallel CALLS edges."""
    assert "MERGE (a)-[:CALLS]->(b)" in Q_LOAD_CALLS
    assert "CREATE (a)-[:CALLS]" not in Q_LOAD_CALLS


def test_pagerank_fallback_reads_edges_read_only_and_writes_scores(monkeypatch):
    """NetworkX fallback uses ro_query for reads and query only for storing scores."""
    class TinyGraph:
        def __init__(self):
            self.edges = []

        def add_edge(self, source, target):
            self.edges.append((source, target))

        def number_of_nodes(self):
            return len({n for edge in self.edges for n in edge})

    networkx = ModuleType("networkx")
    networkx.DiGraph = TinyGraph
    networkx.pagerank = lambda graph: (
        {"pkg.a": 0.7, "pkg.b": 0.3} if graph.number_of_nodes() else {}
    )
    monkeypatch.setitem(sys.modules, "networkx", networkx)

    graph = FakeGraph()
    _pagerank_networkx(graph)

    assert graph.reads == [(Q_CALLS_EDGES, None)]
    assert len(graph.writes) == 1
    cypher, params = graph.writes[0]
    assert cypher == Q_SET_PAGERANK
    assert params == {
        "batch": [
            {"qname": "pkg.a", "pagerank": 0.7},
            {"qname": "pkg.b", "pagerank": 0.3},
        ]
    }


def test_algorithm_pagerank_failure_uses_networkx_fallback(monkeypatch):
    """A failed FalkorDB PageRank call falls back to NetworkX."""
    class FailingAlgorithmGraph(FakeGraph):
        def query(self, cypher, params=None):
            if cypher == Q_PAGERANK:
                self.writes.append((cypher, params))
                raise RuntimeError("PageRank procedure unavailable")
            return super().query(cypher, params)

    class TinyGraph:
        def __init__(self):
            self.edges = []

        def add_edge(self, source, target):
            self.edges.append((source, target))

        def number_of_nodes(self):
            return 2

    networkx = ModuleType("networkx")
    networkx.DiGraph = TinyGraph
    networkx.pagerank = lambda graph: (
        {"pkg.a": 0.7, "pkg.b": 0.3} if graph.number_of_nodes() else {}
    )
    monkeypatch.setitem(sys.modules, "networkx", networkx)
    graph = FailingAlgorithmGraph()

    compute_pagerank(graph)

    assert graph.writes[0] == (Q_PAGERANK, None)
    assert graph.reads[0] == (Q_CALLS_EDGES, None)
    assert graph.writes[1][0] == Q_SET_PAGERANK


def test_count_queries_are_read_only():
    """Ingest reporting queries must use the client's read-only call."""
    graph = FakeGraph()
    print_counts(graph)
    assert len(graph.reads) == 2
    assert graph.writes == []
