# ImpactGraph - Project Status

Updated: 2026-10-18 (live verification, real benchmark, identity-mapping fix)
Deadline: 2026-10-18 23:59 IST (Target Submission: 18:00 IST)

## Summary Table

| Component | Status | Evidence / Notes |
| :--- | :--- | :--- |
| **Repo & Git Structure** | **DONE** | Standalone git repository initialized in `Downloads/impactgraph/`. |
| **Docker & Database** | **DONE** | Verified live: `impactgraph-falkordb-1` (3000/6379) and `impactgraph-api-1` (8000) healthy. Graph `impact_borgbase_vorta` loaded (1,897 nodes, 4,784 edges). |
| **Python Environment** | **DONE** | `.venv` active with Python 3.11, pytest 9.1.1, and all dependencies installed. |
| **Ingestion Pipeline** | **DONE** | Implemented (`ast_parser.py`, `git_history.py`, `load_graph.py`). 5 unit tests pass in `test_ast_parser.py`. |
| **Graph Queries (Q0–Q5)** | **DONE** | Implemented in `graph/client.py` and `graph/queries.py`; analysis reads enforce `ro_query`. Covered by the full pytest suite. |
| **PageRank** | **DONE** | Verified live in FalkorDB Browser: `CALL algo.pageRank('Function', 'CALLS')` returns ranked scores. NetworkX fallback is covered by pytest. |
| **Risk Scoring (`graph/risk.py`)** | **DONE** | Formula includes the uncovered-test risk contribution and is covered by the full pytest suite. |
| **FastMCP Server (`mcp_server/server.py`)** | **DONE** | Seven MCP tools, including `get_most_central`; inputs are checked against graph names and tool reads use `ro_query`. |
| **Agent Loop (`agent/loop.py`)** | **DONE** | Configurable hop depth, graph-name validation, per-tool outcomes, proof paths, and a finding/risk contribution when no test reaches a change. |
| **PR Comment & Guardrails** | **DONE** | `validate_decision()` constrains generated text to graph evidence; PR comments include outcomes and distinguish missing graph evidence from safety. |
| **GitHub Actions & Webhook** | **DONE** | Implemented `agent/github_actions.py` and `/webhook/github` endpoint with background execution. |
| **Backend API (`api/main.py`)** | **DONE** | `/ask` answers are evidence-validated and endpoints return outcome labels. Hop depth is propagated through analysis and featured-cache views. |
| **Frontend UI (`web/`)** | **DONE** | Interactive hop depth 1/4, outcome labels (including Ask), Graph ON/OFF, and highlighted proof paths. Production build passes (1,642 modules). |
| **Benchmark Harness** | **DONE** | Real run: 40 PRs from `borgbase/vorta`, 6 methods (`benchmark/results.md`). Graph: Hit@3 0.80, Hit@5 0.85, MRR 0.74, test recall@5 0.51. Strongest unified method, but narrowly loses to specialist baselines on single metrics (flat_commit_count Hit@5 0.88; grep_imports test recall@5 0.57). Fixed author-identity mismatch via `benchmark/map_authors.py` (90/95 emails resolved to GitHub logins). |
| **Demo Cache (`demo_cache/`)** | **DONE** | Featured PR #2560 demonstrates the empty same-name baseline against depth-1 and depth-4 test paths; cache outcomes are labeled. Paths were derived from the checked-out source call graph, not verified against the unavailable live FalkorDB instance. |
| **Documentation & README** | **DONE** | README video script includes depth 1 → depth 4 and Graph OFF. `AGENTS.md` and `queries.cypher` document matching query/tool choices and known Browser-verification limitations. |
| **CI / CD Workflow** | **DONE** | `.github/workflows/ci.yml` runs pytest with a FalkorDB service container. |

## Test Suite Results

```bash
./.venv/bin/pytest -q
============================== 90 passed in 0.67s ==============================
```

Frontend production build: `npm run build` — passed (1,642 modules).

Live FalkorDB verification (2026-10-18, Browser at localhost:3000, real graph):
- `shortestPath` works only directly inside `RETURN`/`WITH` (not `MATCH p = shortestPath(...)`), and the relationship variable must be unnamed (`[:CALLS*]`, not `[r:CALLS*]`), otherwise it silently returns no rows.
- `CALL algo.SPpaths({sourceNode: a, targetNode: b})` works with pre-matched node variables and agrees with `shortestPath`.
- `CALL algo.pageRank('Function', 'CALLS')` works.
- Found and fixed 4 bugs from `size(r)` on a variable-length path ("Type mismatch: expected List, String, or Null but was Path") in `Q_BLAST_TEMPLATE`, `Q_TESTS_TEMPLATE`, `Q_TEST_PATH`, `Q_EXPLAIN_PATH`.

## Frontend (web/) — Architecture

```
web/
  index.html          — SEO meta, Google Fonts (Inter + JetBrains Mono)
  vite.config.js      — Vite + React plugin, /api proxy → localhost:8000
  package.json        — React 18, TanStack Query, cytoscape, react-cytoscapejs, cytoscape-fcose, recharts, lucide-react
  src/
    main.jsx          — QueryClientProvider root
    index.css         — Full dark design system (CSS vars, components, responsive)
    api.js            — Typed fetch wrappers for all backend endpoints (with max_hops)
    App.jsx           — Main layout: topbar (hop depth 1/4 toggle, graph on/off) + left panel + right panel
    components/
      RiskCard.jsx        — Score gauge, badge, 4-factor bar chart
      BlastPanel.jsx      — Clickable blast radius list → highlights graph node
      TestsPanel.jsx      — Tests list + "No test reaches this change" finding + Copy pytest
      ReviewersPanel.jsx  — Ranked reviewers with medal icons and score
      AskBox.jsx          — POST /ask integration with outcome label and evidence rows
      GraphCanvas.jsx     — Cytoscape.js canvas, fcose layout, dimming on click, legend, 150-node cap
      EvidenceTab.jsx     — Cypher + params + rows + duration + Copy button
      BenchmarkTab.jsx    — MetricBar charts (graph vs baseline vs LLM-only), per-PR table, limitations
```
