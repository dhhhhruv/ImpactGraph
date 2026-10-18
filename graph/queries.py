"""Cypher queries Q0-Q5 and wrappers for ImpactGraph.

Strictly follows schema and queries defined in AGENTS.md and queries.cypher.
Values are passed as query parameters; hop limits are int-validated before formatting.
All non-write queries use GraphClient.ro_query.
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
MATCH p = (c:Function)-[r:CALLS*1..{hops}]->(ch:Function)
WHERE ch.qname IN $changed AND NOT c:Test AND NOT c.file STARTS WITH 'tests/'
RETURN c.qname AS affected, ch.qname AS via, length(p) AS hops,
       [n IN nodes(p) | n.qname] AS path, length(p) AS rel_count
ORDER BY hops LIMIT 200
"""

# Q2a - Tests reaching changed functions (hops validated as integer)
Q_TESTS_TEMPLATE = """
MATCH p = (t:Test)-[r:CALLS*1..{hops}]->(ch:Function)
WHERE ch.qname IN $changed
RETURN t.qname AS test, t.file AS file, min(length(p)) AS hops
ORDER BY hops LIMIT 30
"""

# Q2b - proof path (Cypher shortestPath; algo.SPpaths not used — see AGENTS.md)
Q_TEST_PATH = """
MATCH (t:Test {qname: $test}), (ch:Function {qname: $changed_fn})
RETURN [n IN nodes(shortestPath((t)-[:CALLS*..6]->(ch))) | n.qname] AS path
"""

# Q3 - Reviewer evidence (no future leakage: c.ts < $before)
Q_REVIEWERS = """
MATCH (a:Author)-[au:AUTHORED]->(c:Commit)-[t:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts < $before
RETURN a.name AS author, a.email AS email, count(DISTINCT c) AS commits,
       count(DISTINCT f) AS files_covered, max(c.ts) AS last_ts,
       count(t) AS touch_rels, count(DISTINCT au) AS authored_rels
ORDER BY files_covered DESC, commits DESC LIMIT 10
"""

# Q4 - Centrality (PageRank) of changed functions
Q_CENTRALITY = """
MATCH (f:Function) WHERE f.qname IN $changed
RETURN f.qname AS fn, f.pagerank AS pagerank ORDER BY pagerank DESC
"""

# Q5 - Recent commit churn
Q_CHURN = """
MATCH (c:Commit)-[t:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts > $since AND c.ts < $before
RETURN count(DISTINCT c) AS recent_commits, count(t) AS touch_rels
"""

# explain_path — Cypher shortestPath (chosen over CALL algo.SPpaths)
Q_EXPLAIN_PATH = """
MATCH (a:Function {qname: $from_qname}), (b:Function {qname: $to_qname})
RETURN [n IN nodes(shortestPath((a)-[:CALLS*..6]->(b))) | n.qname] AS path
"""

Q_FN_EXISTS = """
MATCH (f:Function {qname: $qname})
RETURN f.qname AS qname LIMIT 1
"""

Q_FILE_EXISTS = """
MATCH (f:File {path: $path})
RETURN f.path AS path LIMIT 1
"""

Q_TEST_EXISTS = """
MATCH (t:Test {qname: $qname})
RETURN t.qname AS qname LIMIT 1
"""

Q_PERSON_EXISTS = """
MATCH (a:Author {name: $name})
RETURN a.name AS name LIMIT 1
"""

Q_MOST_CENTRAL_TEMPLATE = """
MATCH (f:Function)
WHERE f.pagerank IS NOT NULL AND NOT f:Test
RETURN f.qname AS qname, f.file AS file, f.pagerank AS score
ORDER BY f.pagerank DESC
LIMIT {limit}
"""


def validate_hop_limit(hops: int, min_val: int = 1, max_val: int = 10) -> int:
    """Validate and enforce bounds on integer hop limits."""
    val = int(hops)
    if val < min_val or val > max_val:
        raise ValueError(f"Hop limit {val} outside safe range [{min_val}, {max_val}]")
    return val


def function_exists(client: GraphClient, qname: str) -> bool:
    """Return True if a Function node with this qname exists."""
    rows, _ = client.ro_query(Q_FN_EXISTS, {"qname": qname})
    return bool(rows)


def file_exists(client: GraphClient, path: str) -> bool:
    """Return True if a File node with this path exists."""
    rows, _ = client.ro_query(Q_FILE_EXISTS, {"path": path})
    return bool(rows)


def test_exists(client: GraphClient, qname: str) -> bool:
    """Return True if a Test node with this qname exists."""
    rows, _ = client.ro_query(Q_TEST_EXISTS, {"qname": qname})
    return bool(rows)


def person_exists(client: GraphClient, name: str) -> bool:
    """Return True if an Author node with this name exists."""
    rows, _ = client.ro_query(Q_PERSON_EXISTS, {"name": name})
    return bool(rows)


def confirm_names(
    client: GraphClient,
    functions: Optional[List[str]] = None,
    files: Optional[List[str]] = None,
    tests: Optional[List[str]] = None,
    people: Optional[List[str]] = None,
) -> Dict[str, Any]:
    """Confirm every supplied graph name exists; return unknown lists."""
    unknown_fns = [q for q in (functions or []) if not function_exists(client, q)]
    unknown_files = [p for p in (files or []) if not file_exists(client, p)]
    unknown_tests = [q for q in (tests or []) if not test_exists(client, q)]
    unknown_people = [n for n in (people or []) if not person_exists(client, n)]
    return {
        "ok": not unknown_fns and not unknown_files and not unknown_tests and not unknown_people,
        "unknown_functions": unknown_fns,
        "unknown_files": unknown_files,
        "unknown_tests": unknown_tests,
        "unknown_people": unknown_people,
    }


def q0_diff_to_functions(
    client: GraphClient, path: str, hunk_start: int, hunk_end: int
) -> List[str]:
    """Q0: Map changed file hunk to defined function qnames."""
    params = {"path": path, "hunk_start": int(hunk_start), "hunk_end": int(hunk_end)}
    rows, _ = client.ro_query(Q_DIFF_TO_FN, params)
    return [str(row["qname"]) for row in rows if "qname" in row]


def q1_blast_radius(
    client: GraphClient, changed_qnames: List[str], max_hops: int = 4
) -> Tuple[List[Dict[str, Any]], QueryEvidence]:
    """Q1: Find functions directly and indirectly calling changed functions."""
    safe_hops = validate_hop_limit(max_hops, min_val=1, max_val=6)
    cypher = Q_BLAST_TEMPLATE.format(hops=safe_hops)
    rows, ev = client.ro_query(cypher, {"changed": changed_qnames})
    # One row per affected function (rows arrive ordered by hops, so the first is the shortest path).
    seen = set()
    unique_rows = []
    for row in rows:
        key = row.get("affected")
        if key in seen:
            continue
        seen.add(key)
        unique_rows.append(row)
    return unique_rows, ev


def q2a_affected_tests(
    client: GraphClient, changed_qnames: List[str], max_hops: int = 6
) -> List[Dict[str, Any]]:
    """Q2a: Find tests reaching changed functions within max_hops."""
    safe_hops = validate_hop_limit(max_hops, min_val=1, max_val=8)
    cypher = Q_TESTS_TEMPLATE.format(hops=safe_hops)
    rows, _ = client.ro_query(cypher, {"changed": changed_qnames})
    return rows


def q2b_test_proof_path(
    client: GraphClient, test_qname: str, changed_fn: str
) -> Optional[List[str]]:
    """Q2b: Get shortest execution path from test to changed function."""
    params = {"test": test_qname, "changed_fn": changed_fn}
    rows, _ = client.ro_query(Q_TEST_PATH, params)
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
    rows, _ = client.ro_query(Q_REVIEWERS, params)
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
    rows, _ = client.ro_query(Q_CENTRALITY, {"changed": changed_qnames})
    return rows


def q5_recent_churn(
    client: GraphClient, files: List[str], since_ts: int, before_ts: int
) -> int:
    """Q5: Count commits touching changed files between since_ts and before_ts."""
    params = {"files": files, "since": int(since_ts), "before": int(before_ts)}
    rows, _ = client.ro_query(Q_CHURN, params)
    if rows and "recent_commits" in rows[0]:
        return int(rows[0]["recent_commits"])
    return 0


def explain_path(
    client: GraphClient, from_qname: str, to_qname: str
) -> Optional[List[str]]:
    """Shortest CALLS path via Cypher shortestPath (Browser check pending)."""
    params = {"from_qname": from_qname, "to_qname": to_qname}
    rows, _ = client.ro_query(Q_EXPLAIN_PATH, params)
    if rows and "path" in rows[0]:
        return list(rows[0]["path"])
    return None


def q_most_central(client: GraphClient, limit: int = 10) -> List[Dict[str, Any]]:
    """Return top Function nodes by stored pagerank score, with a 1..20 limit."""
    safe_limit = int(limit)
    if safe_limit < 1 or safe_limit > 20:
        raise ValueError("Centrality limit must be between 1 and 20")
    cypher = Q_MOST_CENTRAL_TEMPLATE.format(limit=safe_limit)
    rows, _ = client.ro_query(cypher, {})
    return [
        {
            "qname": str(r.get("qname", "")),
            "file": str(r.get("file", "")),
            "score": float(r.get("score") or 0.0),
        }
        for r in rows
    ]
