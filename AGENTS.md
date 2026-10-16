# AGENTS.md - single source of truth for ImpactGraph
Every agent reads this first. If you change the schema or a query name, update this file AND queries.cypher.

## What we are building
When a pull request (PR) arrives, an agent asks a FalkorDB graph of the code and its git history:
what can this change break, which tests should run, who should review it, how risky is it.
It posts one PR comment where every claim carries its graph path.
Track: Track 01 - Agents That Act on Connected Data.
Target repo: borgbase/vorta (backup: two other Python repos, decided on Day 1). Demo on OUR FORK.

## The split (graph about 60%, LLM about 40%)
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
- Use only history before each PR's base time (c.ts < $before). No future leakage.

## Coding rules (paste at top of every agent prompt)
Project: ImpactGraph (Python 3.11, FastAPI, FalkorDB, React).
Naming: snake_case functions/variables, PascalCase classes, UPPER_SNAKE for Cypher constants (Q_BLAST, Q_TESTS).
Labels: File, Function, Test, Author, Commit. Edges: DEFINES, CALLS, IMPORTS, AUTHORED, TOUCHED.
Never change schema or query names without updating AGENTS.md and queries.cypher.
Functions under 40 lines, type hints, no new dependencies without asking.
Every tool returns compact JSON. Never return source code to the LLM.
Always pass values as query parameters. Only the hop limit is formatted into a query, after int() validation.
Write a pytest test for each query or function you add. Output only the changed files.
No secrets in the repo. .env is never committed.
Disclosure: AI coding assistants are used in this project and must be listed in the README.

## Layout
impactgraph/ AGENTS.md ORCHESTRATOR.md README.md queries.cypher .env.example docker-compose.yml
ingest/ (ast_parser.py git_history.py load_graph.py) graph/ (client.py queries.py risk.py)
mcp_server/server.py agent/ (loop.py prompts.py comment.py github_actions.py) api/main.py
benchmark/ (collect_prs.py run.py baselines.py results.md prs.json) web/ tests/ demo_cache/
