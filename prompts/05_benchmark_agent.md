Project: ImpactGraph (Python 3.11, FastAPI, FalkorDB, React). Read AGENTS.md first; it is the source of truth.
Naming: snake_case functions/variables, PascalCase classes, UPPER_SNAKE for Cypher constants (Q_BLAST, Q_TESTS).
Never change schema or query names without updating AGENTS.md and queries.cypher.
Functions under 40 lines, type hints, no new dependencies without asking.
Every tool returns compact JSON. Never return source code to the LLM.
Pass values as query parameters; only the hop limit is formatted into a query after int() validation.
Write a pytest test for each query or function you add. Output only the changed files. No secrets in the repo.

---
TASK: implement benchmark/collect_prs.py, baselines.py, run.py following benchmark/SELECTION_RULE.md.
- collect_prs.py: pick PRs by the rule, cache every raw GitHub response as JSON, save prs.json. If rate-limit-remaining is low, sleep until reset. Do not use the GitHub search API.
- run.py: calls graph queries directly in Python (NO LLM for graph runs), using only history before each PR base time. Metrics: reviewer hit@3, hit@5, MRR; test recall@k and average tests suggested (PRs with and without test changes reported separately); blast-radius sanity check.
- baselines.py: reviewers = most recent committer, flat commit count. Tests = same-name test file, grep imports. Plus an LLM-only-no-graph baseline.
- Output results.md (table + method + limits) and a JSON file for the Benchmark page. Runs must be reproducible.
