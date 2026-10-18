# AGENTS.md - single source of truth for ImpactGraph
Every agent reads this first. If you change the schema or a query name, update this file AND queries.cypher.

## What we are building
When a pull request (PR) arrives, an agent asks a FalkorDB graph of the code and its git history:
what can this change break, which tests should run, who should review it, how risky is it.
It posts one PR comment where every claim carries its graph path.
Track: Track 01 - Agents That Act on Connected Data.
Target repo: borgbase/vorta (backup: two other Python repos, decided on Day 1). Demo on OUR FORK.

## The split (design intent: graph about 60%, LLM about 40%)
Current status: when LLM_API_KEY is set, a Gemini model chooses and sequences the graph tools (agent/agent.py) and may add notes; with no key, an API error or an incomplete run, the fixed pipeline runs instead. The summary sentence is always a fixed template over tool results, and /ask uses fixed Cypher queries. Grounding checks function and test names only, not every claim. The 60/40 split is the design intent, not measured.
- GRAPH finds facts: affected functions, tests, reviewers, risk score, paths.
- LLM decides and explains: picks what to check next, digs deeper when something looks odd,
  chooses between close reviewer candidates, writes the "why this matters" text,
  answers follow-up questions in the UI (via POST /ask, which queries the graph again).
- The LLM NEVER invents a name, number, test, file or person. Only values returned by tools.
- The risk score comes from the formula in graph/risk.py. The LLM explains it, never computes it.

## Graph schema (do not change without updating this file)
Nodes: File {path, loc} | Function {qname, name, file, start, end, pagerank}
       Test (extra label on Function whose name starts with test_ inside tests/)
       Author {email, name} | Commit {sha, ts, msg}
Edges: (File)-[:DEFINES]->(Function), (Function)-[:CALLS]->(Function), (File)-[:IMPORTS]->(File),
       (Author)-[:AUTHORED]->(Commit), (Commit)-[:TOUCHED {added, deleted}]->(File)
One graph per repo, named impact_<owner>_<repo>.
Honest limit (goes in README): call links are name-based and approximate.

## MCP tools (mcp_server/server.py)
Query tools (compact JSON strings): blast_radius, affected_tests, test_proof_path,
find_reviewers, centrality, recent_churn, get_most_central(limit: int, max 20).
Agent tools (dicts): map_diff_to_functions, get_blast_radius, get_affected_tests,
find_reviewers, get_risk, explain_path, get_most_central(limit: int, max 20).
Every tool result carries exactly one outcome: answered_with_path | not_in_graph |
unknown_name | cached. Empty results mean "not modelled", never "safe" / "nothing breaks".
Names passed into tools must exist in the graph or the tool returns unknown_name without
running the requested analysis query. Existence checks themselves use read-only queries.
Read-only analysis uses GraphClient.ro_query; only ingest and PageRank storage may write.
CALLS edges are ingested with MERGE to prevent duplicates. Every relationship alias in a
query is referenced in the result/filter to avoid FalkorDB miscounting.

## Algorithms
- explain_path / Q2b use Cypher `shortestPath((a)-[:CALLS*..6]->(b))`, unnamed relationship.
  Verified live against FalkorDB Browser (localhost:3000, 2026-10-17): the relationship
  variable must NOT be named inside shortestPath() — naming it (e.g. `[r:CALLS*]`) causes
  the query to silently return no rows in this FalkorDB version. Also, shortestPath must
  appear directly in a RETURN or WITH clause, not bound via `MATCH p = shortestPath(...)`
  (that raises "FalkorDB currently only supports shortestPaths in WITH or RETURN clauses").
  `CALL algo.SPpaths({sourceNode: a, targetNode: b})` was also verified live and agrees
  with shortestPath's result on a 2-hop test case (is_network_metered -> call_ipconfig_getpacket).
- PageRank storage tries `CALL algo.pageRank('Function', 'CALLS')`; on an algorithm error,
  ingest/load_graph.py falls back to NetworkX and stores scores on Function.pagerank.
  Verified live against FalkorDB Browser (localhost:3000, 2026-10-17): the call succeeds
  and returns ranked (node.name, score) pairs. get_most_central reads the stored scores
  and returns only qname, file, and score.
- Never call `size()` on a variable-length relationship variable (e.g. `size(r)` for `[r:CALLS*..6]`).
  FalkorDB raises "Type mismatch: expected List, String, or Null but was Path". Use `length(p)` on
  a named path instead. This was a real bug in Q_BLAST_TEMPLATE, Q_TESTS_TEMPLATE, Q_TEST_PATH and
  Q_EXPLAIN_PATH, found and fixed on 2026-10-18 against the live graph (impact_borgbase_vorta).

## Failsafes
1. GitHub limits: use a token. Download PR data ONCE, save as JSON, commit it. Benchmark never calls GitHub again.
2. AI limits: running app uses its own separate key, never a coding account. Pre-generate the 5 demo PRs
   into demo_cache/. If the AI is down, show the graph's answer anyway (template-only comment).
3. Messy call graph: hand-check 15 functions on Day 1. If too noisy, shorten chain length (max 3 hops).
4. Weak benchmark answers: choose PRs by the written rule in benchmark/SELECTION_RULE.md BEFORE looking
   at results. README says these are rough checks. Hand-check about 10 PRs.
5. Repo problem: test vorta in the first hour. Switch to a backup repo if thin.
6. Graph feature fails (e.g. PageRank): compute with networkx in plain Python, store on nodes.
7. Hosting problems: local Docker is the main path, deploy is a bonus. Wake live link before recording.
8. Out of time, cut in this order: webhook, second repo, live trace, precomputed test links,
   reviewer requests. NEVER cut: benchmark, path highlighting, demo video.

## Benchmark rules
- Benchmark runs graph queries directly in Python, no LLM.
- Baselines: reviewers = last committer, flat commit count. Tests = same-name file, grep imports.
- Add an "LLM only, no graph" baseline to prove the graph matters.
- Reviewer history uses commits with c.ts before each PR's base commit time (c.ts < $before). Test and blast-radius queries use a single final snapshot, so test recall may be optimistic. Do not claim "no future leakage".
- Author identity: the graph's Author nodes use git display names (e.g. "Manu"), while GitHub ground
  truth uses logins (e.g. "m3nu"). Without mapping, reviewer metrics are 0.0 for every method.
  Reviewer queries return a.email; benchmark/map_authors.py resolves each email to a GitHub login
  (90 of 95 resolved, saved in benchmark/author_map.json); run.py and baselines.py map email -> login
  and fall back to the raw name when unresolved.
- Real run: 40 vorta PRs, 6 methods. Graph is the strongest unified method: essentially equal to
  flat_commit_count on reviewers (Hit@3 0.83, Hit@5 0.88) and narrowly behind grep_imports on test
  recall@5 (0.57 vs 0.51). The benchmark maps each changed file to all of its functions (whole file),
  not to changed hunks. Report this honestly; see benchmark/results.md.

## Coding rules (paste at top of every agent prompt)
Project: ImpactGraph (Python 3.11, FastAPI, FalkorDB, React).
Naming: snake_case functions/variables, PascalCase classes, UPPER_SNAKE for Cypher constants (Q_BLAST, Q_TESTS).
Labels: File, Function, Test, Author, Commit. Edges: DEFINES, CALLS, IMPORTS, AUTHORED, TOUCHED.
Never change schema or query names without updating AGENTS.md and queries.cypher.
Functions under 40 lines, type hints, no new dependencies without asking.
Every tool returns compact JSON. Never return source code to the LLM.
Always pass values as query parameters. Only validated hop/limit integers may be formatted into a query.
Write a pytest test for each query or function you add. Output only the changed files.
No secrets in the repo. .env is never committed.
Disclosure: AI coding assistants are used in this project and must be listed in the README.

## Layout
impactgraph/ AGENTS.md ORCHESTRATOR.md README.md queries.cypher .env.example docker-compose.yml
ingest/ (ast_parser.py git_history.py load_graph.py) graph/ (client.py queries.py risk.py)
mcp_server/server.py agent/ (loop.py prompts.py comment.py github_actions.py) api/main.py
benchmark/ (collect_prs.py run.py baselines.py results.md prs.json) web/ tests/ demo_cache/
