"""Cypher queries Q0-Q5 and wrappers for ImpactGraph.

Strictly follows schema and queries defined in AGENTS.md and queries.cypher.
Values are passed as query parameters; hop limits are int-validated before formatting.
"""

from typing import Any, Dict, List, Optional, Tuple
from graph.client import GraphClient, QueryEvidence

# Q0 - Diff hunk to changed functions
Q_DIFF_TO_FN = """
MATCH (f:Function {file: $path})
WHERE f.start <= $hunk_end AND f.end >= $hunk_start
RETURN f.qname AS qname
"""

# Q1 - Blast radius template (hops validated as integer)
Q_BLAST_TEMPLATE = """
MATCH p = (c:Function)-[:CALLS*1..{hops}]->(ch:Function)
WHERE ch.qname IN $changed
RETURN c.qname AS affected, ch.qname AS via, length(p) AS hops,
       [n IN nodes(p) | n.qname] AS path
ORDER BY hops LIMIT 200
"""

# Q2a - Tests reaching changed functions (hops validated as integer)
Q_TESTS_TEMPLATE = """
MATCH p = (t:Test)-[:CALLS*1..{hops}]->(ch:Function)
WHERE ch.qname IN $changed
RETURN t.qname AS test, t.file AS file, min(length(p)) AS hops
ORDER BY hops LIMIT 30
"""

# Q2b - Shortest proof path for a test
Q_TEST_PATH = """
MATCH (t:Test {qname: $test}), (ch:Function {qname: $changed_fn})
WITH shortestPath((t)-[:CALLS*..6]->(ch)) AS p
WHERE p IS NOT NULL
RETURN [n IN nodes(p) | n.qname] AS path
"""

# Q3 - Reviewer evidence (no future leakage: c.ts < $before)
Q_REVIEWERS = """
MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts < $before
RETURN a.name AS author, count(DISTINCT c) AS commits,
       count(DISTINCT f) AS files_covered, max(c.ts) AS last_ts
ORDER BY files_covered DESC, commits DESC LIMIT 10
"""

# Q4 - Centrality (PageRank) of changed functions
Q_CENTRALITY = """
MATCH (f:Function) WHERE f.qname IN $changed
RETURN f.qname AS fn, f.pagerank AS pagerank ORDER BY pagerank DESC
"""

# Q5 - Recent commit churn
Q_CHURN = """
MATCH (c:Commit)-[:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts > $since AND c.ts < $before
RETURN count(DISTINCT c) AS recent_commits
"""


def validate_hop_limit(hops: int, min_val: int = 1, max_val: int = 10) -> int:
    """Validate and enforce bounds on integer hop limits."""
    val = int(hops)
    if val < min_val or val > max_val:
        raise ValueError(f"Hop limit {val} outside safe range [{min_val}, {max_val}]")
    return val


def q0_diff_to_functions(
    client: GraphClient, path: str, hunk_start: int, hunk_end: int
) -> List[str]:
    """Q0: Map changed file hunk to defined function qnames."""
    params = {"path": path, "hunk_start": int(hunk_start), "hunk_end": int(hunk_end)}
    rows, _ = client.execute_query(Q_DIFF_TO_FN, params)
    return [str(row["qname"]) for row in rows if "qname" in row]


def q1_blast_radius(
    client: GraphClient, changed_qnames: List[str], max_hops: int = 4
) -> Tuple[List[Dict[str, Any]], QueryEvidence]:
    """Q1: Find functions directly and indirectly calling changed functions."""
    safe_hops = validate_hop_limit(max_hops, min_val=1, max_val=6)
    cypher = Q_BLAST_TEMPLATE.format(hops=safe_hops)
    rows, ev = client.execute_query(cypher, {"changed": changed_qnames})
    return rows, ev


def q2a_affected_tests(
    client: GraphClient, changed_qnames: List[str], max_hops: int = 6
) -> List[Dict[str, Any]]:
    """Q2a: Find tests reaching changed functions within max_hops."""
    safe_hops = validate_hop_limit(max_hops, min_val=1, max_val=8)
    cypher = Q_TESTS_TEMPLATE.format(hops=safe_hops)
    rows, _ = client.execute_query(cypher, {"changed": changed_qnames})
    return rows


def q2b_test_proof_path(
    client: GraphClient, test_qname: str, changed_fn: str
) -> Optional[List[str]]:
    """Q2b: Get shortest execution path from test to changed function."""
    params = {"test": test_qname, "changed_fn": changed_fn}
    rows, _ = client.execute_query(Q_TEST_PATH, params)
    if rows and "path" in rows[0]:
        return list(rows[0]["path"])
    return None


def calculate_reviewer_score(
    files_covered: int,
    total_files: int,
    commits: int,
    max_commits: int,
    last_ts: int,
    before_ts: int,
) -> float:
    """Calculate reviewer fitness score in Python (0.0 to 1.0)."""
    cov_ratio = files_covered / max(total_files, 1)
    comm_ratio = commits / max(max_commits, 1)
    age_days = max((before_ts - last_ts) / 86400.0, 0.0)
    recency = 0.5 ** (age_days / 180.0)
    return round(0.5 * cov_ratio + 0.3 * comm_ratio + 0.2 * recency, 4)


def q3_find_reviewers(
    client: GraphClient,
    files: List[str],
    before_ts: int,
    pr_author: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """Q3: Rank reviewers by historical authorship on changed files."""
    params = {"files": files, "before": int(before_ts)}
    rows, _ = client.execute_query(Q_REVIEWERS, params)
    if not rows:
        return []

    filtered = [r for r in rows if pr_author is None or r.get("author") != pr_author]
    max_commits = max((int(r.get("commits", 1)) for r in filtered), default=1)
    total_files = len(files)

    scored = []
    for r in filtered:
        score = calculate_reviewer_score(
            int(r.get("files_covered", 0)),
            total_files,
            int(r.get("commits", 0)),
            max_commits,
            int(r.get("last_ts", 0)),
            before_ts,
        )
        item = dict(r)
        item["score"] = score
        scored.append(item)

    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def q4_centrality(
    client: GraphClient, changed_qnames: List[str]
) -> List[Dict[str, Any]]:
    """Q4: Retrieve PageRank centrality for changed functions."""
    rows, _ = client.execute_query(Q_CENTRALITY, {"changed": changed_qnames})
    return rows


def q5_recent_churn(
    client: GraphClient, files: List[str], since_ts: int, before_ts: int
) -> int:
    """Q5: Count commits touching changed files between since_ts and before_ts."""
    params = {"files": files, "since": int(since_ts), "before": int(before_ts)}
    rows, _ = client.execute_query(Q_CHURN, params)
    if rows and "recent_commits" in rows[0]:
        return int(rows[0]["recent_commits"])
    return 0


# explain_path shortestPath between two arbitrary functions
Q_EXPLAIN_PATH = """
MATCH (a:Function {qname: $from_qname}), (b:Function {qname: $to_qname})
WITH shortestPath((a)-[:CALLS*..6]->(b)) AS p
WHERE p IS NOT NULL
RETURN [n IN nodes(p) | n.qname] AS path
"""


def explain_path(
    client: GraphClient, from_qname: str, to_qname: str
) -> Optional[List[str]]:
    """Explain call path between two functions via shortest path."""
    params = {"from_qname": from_qname, "to_qname": to_qname}
    rows, _ = client.execute_query(Q_EXPLAIN_PATH, params)
    if rows and "path" in rows[0]:
        return list(rows[0]["path"])
    return None

