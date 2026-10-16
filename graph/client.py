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
    ) -> None:
        self.cypher = cypher
        self.params = params
        self.row_count = row_count
        self.duration_ms = round(duration_ms, 2)

    def to_dict(self) -> Dict[str, Any]:
        """Convert evidence record to dictionary."""
        return {
            "cypher": self.cypher,
            "params": self.params,
            "row_count": self.row_count,
            "duration_ms": self.duration_ms,
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

    def _get_graph(self) -> Any:
        """Lazily initialize FalkorDB graph connection."""
        if self._driver is not None:
            return self._driver
        if self._graph is None:
            from falkordb import FalkorDB

            client = FalkorDB(host=self.host, port=self.port)
            self._graph = client.select_graph(self.graph_name)
        return self._graph

    def execute_query(
        self,
        cypher: str,
        params: Optional[Dict[str, Any]] = None,
    ) -> Tuple[List[Dict[str, Any]], QueryEvidence]:
        """Execute parameterized Cypher query and log evidence."""
        query_params = params or {}
        start_time = time.perf_counter()

        graph = self._get_graph()
        result = graph.query(cypher, query_params)

        duration_ms = (time.perf_counter() - start_time) * 1000.0

        rows: List[Dict[str, Any]] = []
        if hasattr(result, "result_set") and result.result_set:
            header = [col[1] if isinstance(col, (list, tuple)) and len(col) > 1 else col[0] for col in result.header] if hasattr(result, "header") else []
            for row in result.result_set:
                if header and len(header) == len(row):
                    rows.append(dict(zip(header, row)))
                else:
                    rows.append({"value": row})

        evidence = QueryEvidence(
            cypher=cypher.strip(),
            params=query_params,
            row_count=len(rows),
            duration_ms=duration_ms,
        )
        self.evidence_log.append(evidence)
        return rows, evidence
