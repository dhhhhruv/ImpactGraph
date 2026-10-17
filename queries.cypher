// queries.cypher - the Cypher ImpactGraph depends on. Keep in sync with AGENTS.md.
// Verify exact syntax in FalkorDB Browser (port 3000) before relying on any of these.
// Browser verification is pending when the local FalkorDB service is unavailable.

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
// Relationship alias `r` is bound and referenced (FalkorDB known limitation).
MATCH p = (c:Function)-[r:CALLS*1..4]->(ch:Function)
WHERE ch.qname IN $changed
RETURN c.qname AS affected, ch.qname AS via, length(p) AS hops,
       [n IN nodes(p) | n.qname] AS path, size(r) AS rel_count
ORDER BY hops LIMIT 200

// Q2a - tests that reach the change
MATCH p = (t:Test)-[r:CALLS*1..6]->(ch:Function)
WHERE ch.qname IN $changed AND size(r) >= 1
RETURN t.qname AS test, t.file AS file, min(length(p)) AS hops
ORDER BY hops LIMIT 30

// Q2b - proof path for one test; relationship alias r is explicitly referenced.
MATCH (t:Test {qname: $test}), (ch:Function {qname: $changed_fn})
MATCH p = shortestPath((t)-[r:CALLS*..6]->(ch))
WHERE p IS NOT NULL AND size(r) >= 0
RETURN [n IN nodes(p) | n.qname] AS path

// Q3 - reviewer evidence (c.ts < $before prevents future leakage in the benchmark)
MATCH (a:Author)-[au:AUTHORED]->(c:Commit)-[t:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts < $before
RETURN a.name AS author, count(DISTINCT c) AS commits,
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
CALL algo.pageRank('Function', 'CALLS') YIELD node, score
SET node.pagerank = score

// get_most_central — read stored pagerank (limit formatted after int validation, 1..20)
MATCH (f:Function)
WHERE f.pagerank IS NOT NULL AND NOT f:Test
RETURN f.qname AS qname, f.file AS file, f.pagerank AS score
ORDER BY f.pagerank DESC
LIMIT {limit}

// explain_path - current choice: plain Cypher shortestPath, with relationship alias referenced.
// Browser comparison against CALL algo.SPpaths(...) is pending (local service unavailable).
MATCH (a:Function {qname: $from_qname}), (b:Function {qname: $to_qname})
MATCH p = shortestPath((a)-[r:CALLS*..6]->(b))
WHERE p IS NOT NULL AND size(r) >= 0
RETURN [n IN nodes(p) | n.qname] AS path

// Name existence checks (unknown_name gate; checks use ro_query)
MATCH (f:Function {qname: $qname}) RETURN f.qname AS qname LIMIT 1
MATCH (f:File {path: $path}) RETURN f.path AS path LIMIT 1
MATCH (t:Test {qname: $qname}) RETURN t.qname AS qname LIMIT 1
MATCH (a:Author {name: $name}) RETURN a.name AS name LIMIT 1
