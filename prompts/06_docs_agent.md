Project: ImpactGraph (Python 3.11, FastAPI, FalkorDB, React). Read AGENTS.md first; it is the source of truth.
Naming: snake_case functions/variables, PascalCase classes, UPPER_SNAKE for Cypher constants (Q_BLAST, Q_TESTS).
Never change schema or query names without updating AGENTS.md and queries.cypher.
Functions under 40 lines, type hints, no new dependencies without asking.
Every tool returns compact JSON. Never return source code to the LLM.
Pass values as query parameters; only the hop limit is formatted into a query after int() validation.
Write a pytest test for each query or function you add. Output only the changed files. No secrets in the repo.

---
TASK: write README.md in this order: 20-second demo GIF placeholder, three bullets (what it does, why the graph is essential, headline benchmark numbers), three-command quickstart (cp .env.example .env; docker compose up; one ingest command), architecture diagram, graph data model with counts per label, the exact Cypher queries and why each exists, how to run the agent, benchmark method and results, limitations (name-based call links, proxy ground truth, measured result of the 15-function spot check), AI-use disclosure, track entered (Track 01), live link and video link.
Rule: do not claim any number that is not in benchmark/results.md.
