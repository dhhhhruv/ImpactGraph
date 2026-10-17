# ImpactGraph - Project Status

Updated: 2026-10-17 (implementation and verification update)
Deadline: 2026-10-18 23:59 IST (Target Submission: 18:00 IST)

## Summary Table

| Component | Status | Evidence / Notes |
| :--- | :--- | :--- |
| **Repo & Git Structure** | **DONE** | Standalone git repository initialized in `Downloads/impactgraph/`. |
| **Docker & Database** | **CONFIGURED** | FalkorDB Compose configuration is present. Docker daemon and FalkorDB Browser were unavailable during this update, so live algorithm queries could not be verified. |
| **Python Environment** | **DONE** | `.venv` active with Python 3.11, pytest 9.1.1, and all dependencies installed. |
| **Ingestion Pipeline** | **DONE** | Implemented (`ast_parser.py`, `git_history.py`, `load_graph.py`). 5 unit tests pass in `test_ast_parser.py`. |
| **Graph Queries (Q0–Q5)** | **DONE** | Implemented in `graph/client.py` and `graph/queries.py`; analysis reads enforce `ro_query`. Covered by the full pytest suite. |
| **PageRank** | **IMPLEMENTED** | `get_most_central` reads compact ranked Function rows; the NetworkX fallback is covered by pytest. FalkorDB Browser verification of `algo.pageRank` remains pending. |
| **Risk Scoring (`graph/risk.py`)** | **DONE** | Formula includes the uncovered-test risk contribution and is covered by the full pytest suite. |
| **FastMCP Server (`mcp_server/server.py`)** | **DONE** | Seven MCP tools, including `get_most_central`; inputs are checked against graph names and tool reads use `ro_query`. |
| **Agent Loop (`agent/loop.py`)** | **DONE** | Configurable hop depth, graph-name validation, per-tool outcomes, proof paths, and a finding/risk contribution when no test reaches a change. |
| **PR Comment & Guardrails** | **DONE** | `validate_decision()` constrains generated text to graph evidence; PR comments include outcomes and distinguish missing graph evidence from safety. |
| **GitHub Actions & Webhook** | **DONE** | Implemented `agent/github_actions.py` and `/webhook/github` endpoint with background execution. |
| **Backend API (`api/main.py`)** | **DONE** | `/ask` answers are evidence-validated and endpoints return outcome labels. Hop depth is propagated through analysis and featured-cache views. |
| **Frontend UI (`web/`)** | **DONE** | Interactive hop depth 1/4, outcome labels (including Ask), Graph ON/OFF, and highlighted proof paths. Production build passes (1,642 modules). |
| **Benchmark Harness** | **DONE** | Implemented `benchmark/baselines.py`, `benchmark/run.py`, `results.md`, and `results.json`; covered by pytest. |
| **Demo Cache (`demo_cache/`)** | **DONE** | Featured PR #2560 demonstrates the empty same-name baseline against depth-1 and depth-4 test paths; cache outcomes are labeled. Paths were derived from the checked-out source call graph, not verified against the unavailable live FalkorDB instance. |
| **Documentation & README** | **DONE** | README video script includes depth 1 → depth 4 and Graph OFF. `AGENTS.md` and `queries.cypher` document matching query/tool choices and known Browser-verification limitations. |
| **CI / CD Workflow** | **DONE** | `.github/workflows/ci.yml` runs pytest with a FalkorDB service container. |

## Test Suite Results

```bash
./.venv/bin/pytest -q
============================== 90 passed in 0.67s ==============================
```

Frontend production build: `npm run build` — passed (1,642 modules).

Live FalkorDB Browser checks remain outstanding because Docker/the Browser were unavailable:
`CALL algo.SPpaths(...)`, Cypher `shortestPath`, and `CALL algo.pageRank('Function', 'CALLS')`.

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
