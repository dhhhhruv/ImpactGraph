"""FalkorDB graph client with structured evidence logging for ImpactGraph."""

import time
from typing import Any, Dict, List, Optional, Tuple


class QueryEvidence:
    """Stores query execution metadata for UI and PR explanations."""

    def __init__(
        self,
        cypher: str,
        params: Dict[str, Any],
        row_count: int,
        duration_ms: float,
        read_only: bool = False,
    ) -> None:
        self.cypher = cypher
        self.params = params
        self.row_count = row_count
        self.duration_ms = round(duration_ms, 2)
        self.read_only = read_only

    def to_dict(self) -> Dict[str, Any]:
        """Convert evidence record to dictionary."""
        return {
            "cypher": self.cypher,
            "params": self.params,
            "row_count": self.row_count,
            "duration_ms": self.duration_ms,
            "read_only": self.read_only,
        }


class GraphClient:
    """Manages FalkorDB connection and query execution with evidence tracking."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 6379,
        graph_name: str = "impact_borgbase_vorta",
        driver: Optional[Any] = None,
    ) -> None:
        self.host = host
        self.port = port
        self.graph_name = graph_name
        self.evidence_log: List[QueryEvidence] = []
        self._driver = driver
        self._graph = None
        self.write_calls: int = 0
        self.read_calls: int = 0

    def _get_graph(self) -> Any:
        """Lazily initialize FalkorDB graph connection."""
        if self._driver is not None:
            return self._driver
        if self._graph is None:
            from falkordb import FalkorDB

            client = FalkorDB(host=self.host, port=self.port)
            self._graph = client.select_graph(self.graph_name)
        return self._graph

    def _parse_result(self, result: Any) -> List[Dict[str, Any]]:
        """Convert a FalkorDB result object into a list of row dicts."""
        rows: List[Dict[str, Any]] = []
        if not (hasattr(result, "result_set") and result.result_set):
            return rows
        header: List[str] = []
        if hasattr(result, "header"):
            for col in result.header:
                if isinstance(col, (list, tuple)) and len(col) > 1:
                    header.append(col[1])
                else:
                    header.append(col[0] if isinstance(col, (list, tuple)) else str(col))
        for row in result.result_set:
            if header and len(header) == len(row):
                rows.append(dict(zip(header, row)))
            else:
                rows.append({"value": row})
        return rows

    def _run(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]],
        read_only: bool,
    ) -> Tuple[List[Dict[str, Any]], QueryEvidence]:
        """Execute a Cypher query (read-only or write) and log evidence."""
        query_params = params or {}
        start_time = time.perf_counter()
        graph = self._get_graph()
        if read_only:
            self.read_calls += 1
            if not hasattr(graph, "ro_query"):
                raise AttributeError("Graph driver does not provide read-only ro_query")
            result = graph.ro_query(cypher, query_params)
        else:
            self.write_calls += 1
            result = graph.query(cypher, query_params)
        duration_ms = (time.perf_counter() - start_time) * 1000.0
        rows = self._parse_result(result)
        evidence = QueryEvidence(
            cypher=cypher.strip(),
            params=query_params,
            row_count=len(rows),
            duration_ms=duration_ms,
            read_only=read_only,
        )
        self.evidence_log.append(evidence)
        return rows, evidence

    def ro_query(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], QueryEvidence]:
        """Execute a read-only Cypher query (tools and analysis must use this)."""
        return self._run(cypher, params, read_only=True)

    def execute_query(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], QueryEvidence]:
        """Execute a write-capable Cypher query (ingest / PageRank SET only)."""
        return self._run(cypher, params, read_only=False)
