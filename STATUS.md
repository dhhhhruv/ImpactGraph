# ImpactGraph - Project Status

Updated: 2026-10-16 19:15 IST (Day 2 Audit)
Deadline: 2026-10-18 23:59 IST (Target Submission: 18:00 IST)

## Summary Table

| Component | Status | Evidence / Notes |
| :--- | :--- | :--- |
| **Repo & Git Structure** | **DONE** | Standalone git repository initialized in `Downloads/impactgraph/`. |
| **Docker & Database** | **DONE** | FalkorDB container running on ports 6379 & 3000; ping and evidence logging verified live. |
| **Python Environment** | **DONE** | `.venv` active with Python 3.11, pytest 9.1.1, and all dependencies installed. |
| **Ingestion Pipeline** | **DONE** | Implemented (`ast_parser.py`, `git_history.py`, `load_graph.py`). Verified with 5 unit tests in `test_ast_parser.py` and live FalkorDB bulk-load test. |
| **Graph Queries (Q0–Q5)** | **DONE** | Implemented in `graph/client.py` and `graph/queries.py`. Evidence logging and 7 unit tests in `tests/test_queries.py` pass. |
| **PageRank** | **DONE** | Implemented in `ingest/load_graph.py` with both FalkorDB algorithm execution and NetworkX fallback. |
| **Risk Scoring (`graph/risk.py`)** | **DONE** | Implemented in `graph/risk.py` and verified by 6 passing unit tests in `tests/test_risk.py`. Functions under 40 lines, type hints, boundary tests pass. |
| **MCP Server (`mcp_server/server.py`)** | **NOT STARTED** | Tool specifications defined in `prompts/02_query_mcp_agent.md`, but no code or server implementation exists. |
| **Agent Loop (`agent/loop.py`)** | **DONE** | Implemented and verified on real `vorta` repository. Traced 200 blast callers, 30 proof paths, and logged 37 live evidence queries. |
| **PR Comment & Actions** | **DONE** | Implemented `agent/comment.py` with markdown comment formatter, collapsible Cypher audit, and `validate_decision()` hallucination filter. 4 unit tests pass. |
| **Backend API (`api/main.py`)** | **DONE** | Implemented `/health`, `/repos`, `/analyze`, `/subgraph`, `/ask`, and `/benchmark`. 6 unit tests pass in `test_api.py`. |
| **Frontend UI (`web/`)** | **NOT STARTED** | React 18 + Vite + Cytoscape app not initialized. |
| **Benchmark Harness** | **DONE** | Implemented `benchmark/baselines.py`, `benchmark/run.py`, `results.md`, and `results.json`. 7 unit tests pass in `test_benchmark.py`. |
| **Demo Cache (`demo_cache/`)** | **DONE** | 5 demo PR decision objects pre-generated from `vorta` into `demo_cache/demo_pr_1.json` - `demo_pr_5.json`. Servable via `GET /demo/{id}`. |
| **Documentation & Blog** | **IN PROGRESS** | `AGENTS.md`, `ORCHESTRATOR.md`, `queries.cypher`, and `SELECTION_RULE.md` exist. `README.md` and blog post outline not started. |

## Cut-Line Tracking (Order of Cuts from AGENTS.md)

1. Webhook (`/webhook/github`) - *Queued for cut if Day 3 slips*
2. Second target repo - *Queued for cut (focusing 100% on borgbase/vorta)*
3. Live trace UI tab - *Candidate for cut*
4. Precomputed test links - *Candidate for cut*
5. Automatic reviewer requests on GitHub - *Candidate for cut (dry-run text only)*
*MANDATORY DELIVERABLES (NEVER CUT)*:
- Benchmark (40 PRs with baselines + LLM-only comparison)
- Path highlighting in UI
- Demo video (2:30 script)
