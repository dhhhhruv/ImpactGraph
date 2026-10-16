Project: ImpactGraph (Python 3.11, FastAPI, FalkorDB, React). Read AGENTS.md first; it is the source of truth.
Naming: snake_case functions/variables, PascalCase classes, UPPER_SNAKE for Cypher constants (Q_BLAST, Q_TESTS).
Never change schema or query names without updating AGENTS.md and queries.cypher.
Functions under 40 lines, type hints, no new dependencies without asking.
Every tool returns compact JSON. Never return source code to the LLM.
Pass values as query parameters; only the hop limit is formatted into a query after int() validation.
Write a pytest test for each query or function you add. Output only the changed files. No secrets in the repo.

---
TASK: build web/ with React 18 + Vite + Tailwind + TanStack Query + react-cytoscapejs (fcose layout) + Recharts. Dark theme, big fonts for projector.
- Top bar: repo selector, PR number input, Analyze, Dry-run switch, Graph ON/OFF switch, Demo mode badge.
- Left (about 40%): risk card (gauge, label, four small bars), AI summary clearly labelled AI-written, tests list with Copy pytest command, reviewers, actions taken. Add an Ask box that calls POST /ask.
- Right (about 60%): graph canvas (changed red, affected callers orange, tests green, reviewers purple, evidence path thick blue, everything else dimmed to 20 percent when a row is clicked). Node size follows PageRank. Cap 150 nodes with Show more. Tabs: Agent trace, Evidence (Cypher, params, rows, ms, Copy Cypher, Open in FalkorDB Browser), Benchmark.
- Graph OFF shows the flat baseline beside the graph answer.
- Benchmark page: bars for reviewer hit@3, test recall, average tests suggested, graph vs each baseline (including LLM-only), per-PR table, Method and limitations box.
- Handle loading, per-tool errors, empty states. "No test reaches this change" is a finding, not an error.
