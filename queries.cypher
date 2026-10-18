// queries.cypher - the Cypher ImpactGraph depends on. Keep in sync with AGENTS.md.
// Verified live against FalkorDB Browser (localhost:3000) on 2026-10-17.

// Indexes (run once, before bulk load)
CREATE INDEX FOR (f:Function) ON (f.qname)
CREATE INDEX FOR (f:Function) ON (f.file)
CREATE INDEX FOR (f:File) ON (f.path)
CREATE INDEX FOR (c:Commit) ON (c.ts)

// Q0 - diff hunk to changed functions
MATCH (f:Function {file: $path})
WHERE f.start <= $hunk_end AND f.end >= $hunk_start
RETURN f.qname AS qname

// Q1 - blast radius (callers, direct and indirect). The hop number is inserted from Python after int() validation.
// size(r) is not used: FalkorDB raises "Type mismatch: expected List, String, or Null but was Path"
// when size() is called on a variable-length relationship pattern variable. length(p) gives the
// same value for this pattern (no repeated edges) and is used instead.
MATCH p = (c:Function)-[r:CALLS*1..4]->(ch:Function)
WHERE ch.qname IN $changed AND NOT c:Test AND NOT c.file STARTS WITH 'tests/'  // tests and test helpers are reported separately (Q2a), not counted as blast radius
RETURN c.qname AS affected, ch.qname AS via, length(p) AS hops,
       [n IN nodes(p) | n.qname] AS path, length(p) AS rel_count
ORDER BY hops LIMIT 200

// Q2a - tests that reach the change
MATCH p = (t:Test)-[r:CALLS*1..6]->(ch:Function)
WHERE ch.qname IN $changed
RETURN t.qname AS test, t.file AS file, min(length(p)) AS hops
ORDER BY hops LIMIT 30

// Q2b - proof path for one test.
// shortestPath must appear directly in RETURN/WITH, not bound via MATCH p = shortestPath(...)
// (FalkorDB: "FalkorDB currently only supports shortestPaths in WITH or RETURN clauses").
// The relationship variable must be unnamed ([:CALLS*], not [r:CALLS*]) - naming it causes
// shortestPath to silently return no rows in this FalkorDB version.
MATCH (t:Test {qname: $test}), (ch:Function {qname: $changed_fn})
RETURN [n IN nodes(shortestPath((t)-[:CALLS*..6]->(ch))) | n.qname] AS path

// Q3 - reviewer evidence (c.ts < $before prevents future leakage in the benchmark)
// a.email is included so the benchmark can map git authors to GitHub usernames
// (git commit author names and GitHub usernames are different identity systems).
MATCH (a:Author)-[au:AUTHORED]->(c:Commit)-[t:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts < $before
RETURN a.name AS author, a.email AS email, count(DISTINCT c) AS commits,
       count(DISTINCT f) AS files_covered, max(c.ts) AS last_ts,
       count(t) AS touch_rels, count(DISTINCT au) AS authored_rels
ORDER BY files_covered DESC, commits DESC LIMIT 10

// Q4 - centrality of the changed code
MATCH (f:Function) WHERE f.qname IN $changed
RETURN f.qname AS fn, f.pagerank AS pagerank ORDER BY pagerank DESC

// Q5 - recent churn
MATCH (c:Commit)-[t:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts > $since AND c.ts < $before
RETURN count(DISTINCT c) AS recent_commits, count(t) AS touch_rels

// PageRank WRITE (ingest only). If algo.pageRank errors, use networkx fallback in Python.
// Verified live: CALL algo.pageRank('Function', 'CALLS') succeeds and returns ranked scores.
CALL algo.pageRank('Function', 'CALLS') YIELD node, score
SET node.pagerank = score

// get_most_central — read stored pagerank (limit formatted after int validation, 1..20)
MATCH (f:Function)
WHERE f.pagerank IS NOT NULL AND NOT f:Test
RETURN f.qname AS qname, f.file AS file, f.pagerank AS score
ORDER BY f.pagerank DESC
LIMIT {limit}

// explain_path - plain Cypher shortestPath (verified live, see Q2b note above).
// CALL algo.SPpaths({sourceNode: a, targetNode: b}) was also verified live and agrees
// with shortestPath on a 2-hop test case (is_network_metered -> call_ipconfig_getpacket).
MATCH (a:Function {qname: $from_qname}), (b:Function {qname: $to_qname})
RETURN [n IN nodes(shortestPath((a)-[:CALLS*..6]->(b))) | n.qname] AS path

// Name existence checks (unknown_name gate; checks use ro_query)
MATCH (f:Function {qname: $qname}) RETURN f.qname AS qname LIMIT 1
MATCH (f:File {path: $path}) RETURN f.path AS path LIMIT 1
MATCH (t:Test {qname: $qname}) RETURN t.qname AS qname LIMIT 1
MATCH (a:Author {name: $name}) RETURN a.name AS name LIMIT 1