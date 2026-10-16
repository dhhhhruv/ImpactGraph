Project: ImpactGraph (Python 3.11, FastAPI, FalkorDB, React). Read AGENTS.md first; it is the source of truth.
Naming: snake_case functions/variables, PascalCase classes, UPPER_SNAKE for Cypher constants (Q_BLAST, Q_TESTS).
Never change schema or query names without updating AGENTS.md and queries.cypher.
Functions under 40 lines, type hints, no new dependencies without asking.
Every tool returns compact JSON. Never return source code to the LLM.
Pass values as query parameters; only the hop limit is formatted into a query after int() validation.
Write a pytest test for each query or function you add. Output only the changed files. No secrets in the repo.

---
TASK: implement ingest/ast_parser.py, git_history.py and load_graph.py using the schema in AGENTS.md.
- Parse every .py file with ast. Collect functions (module.Class.method qnames) and raw calls.
- Resolve calls: (1) prefer same-module function with that name, (2) else one imported by that module, (3) else accept name matches only if 3 or fewer candidates. Skip builtins and very common names (get, set, append, items).
- Read last 1500 commits with pydriller. Skip merges and bots. Store sha, author, committer date as unix ts, each modified file with added/deleted.
- Create indexes first, bulk load with UNWIND in batches of 500, then run PageRank (fallback: networkx) and store it on Function nodes.
- Mark Test label on Function nodes named test_* inside tests/.
- Add: python -m ingest.load_graph --repo owner/repo --rebuild (deletes and reloads graph impact_owner_repo).
- Finish with a script that prints node and edge counts per label.
- Also write scripts/callgraph_spotcheck.py that picks 15 random functions and prints their callers so humans can check them.
