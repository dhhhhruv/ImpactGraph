// queries.cypher - the Cypher ImpactGraph depends on. Keep in sync with AGENTS.md.
// Verify exact syntax in FalkorDB Browser (port 3000) before relying on any of these.

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
MATCH p = (c:Function)-[:CALLS*1..4]->(ch:Function)
WHERE ch.qname IN $changed
RETURN c.qname AS affected, ch.qname AS via, length(p) AS hops,
       [n IN nodes(p) | n.qname] AS path
ORDER BY hops LIMIT 200

// Q2a - tests that reach the change
MATCH p = (t:Test)-[:CALLS*1..6]->(ch:Function)
WHERE ch.qname IN $changed
RETURN t.qname AS test, t.file AS file, min(length(p)) AS hops
ORDER BY hops LIMIT 30

// Q2b - proof path for one test
MATCH (t:Test {qname: $test}), (ch:Function {qname: $changed_fn})
WITH shortestPath((t)-[:CALLS*..6]->(ch)) AS p
WHERE p IS NOT NULL
RETURN [n IN nodes(p) | n.qname] AS path

// Q3 - reviewer evidence (c.ts < $before prevents future leakage in the benchmark)
MATCH (a:Author)-[:AUTHORED]->(c:Commit)-[:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts < $before
RETURN a.name AS author, count(DISTINCT c) AS commits,
       count(DISTINCT f) AS files_covered, max(c.ts) AS last_ts
ORDER BY files_covered DESC, commits DESC LIMIT 10

// Q4 - centrality of the changed code
MATCH (f:Function) WHERE f.qname IN $changed
RETURN f.qname AS fn, f.pagerank AS pagerank ORDER BY pagerank DESC

// Q5 - recent churn
MATCH (c:Commit)-[:TOUCHED]->(f:File)
WHERE f.path IN $files AND c.ts > $since AND c.ts < $before
RETURN count(DISTINCT c) AS recent_commits

// PageRank (check docs.falkordb.com/algorithms; fallback = networkx in Python)
CALL algo.pageRank('Function', 'CALLS') YIELD node, score
SET node.pagerank = score
