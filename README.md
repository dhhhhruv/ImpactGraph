# ImpactGraph

> **Graph-powered pull request impact analysis.** When a PR arrives, ImpactGraph asks a FalkorDB graph of your codebase and its git history: *what can this change break, which tests should run, who should review it, how risky is it?* Every claim in the output carries its graph path.

---

## How it works

```
PR diff → AST parser → FalkorDB graph → seven graph tools (ToolBox, also served over MCP) → risk score + blast radius + tests + reviewers
                                                        ↓
                                               Evidence-Bound Summary (fixed template over tool results)
                                                        ↓
                                               GitHub PR comment + React UI
```

- **Graph** finds facts: affected functions, reachable tests, reviewer candidates, risk score, call paths.
- **Agent** (when LLM_API_KEY is set): a Gemini model chooses which graph tools to run and in what order (function calling, step cap 8; the request's hop depth overrides the model's). Models come from LLM_MODEL and LLM_MODEL_FALLBACK. With no key, an API error or an incomplete run, the app falls back to the fixed pipeline and the Agent Trace tab says so. The free tier allows about 20 requests per model per day and one analysis uses about 7, so the demo cache and the fixed pipeline matter.
- **Summary** sentence is always built from the tool results by a fixed template. The model only adds optional notes: function and test names in them are checked against tool results, but other wording is the model's and is not verified.
- **PR action (dry run)**: the PR Action tab shows the comment, risk label, reviewer requests and pytest command built from the decision (POST /action/preview). It posts nothing and makes no model or GitHub call.
- Every name, test, file and person in the facts comes from graph query results. The graph tools, not the model, produce the numbers, and the risk score comes from a formula.

**MCP and the model.** The agent calls the seven graph tools in-process (ToolBox). The same tools are also served over MCP, by a stateless server (mcp_server/server.py) and a stateful one (agent/mcp_server.py), so any MCP client can drive them. The agent itself does not go through MCP.

**Design split.** The intent is roughly 60% graph, 40% model: the graph supplies facts and the model chooses and sequences tools and writes notes. That split is the design, not a measurement.

---

## Features

| Feature | Details |
|---|---|
| **Blast radius** | Call-graph traversal (up to 3 hops) to find every function that can reach changed code |
| **Affected tests** | Shortest path (up to 4 hops) from `Test` nodes back to changed functions |
| **Reviewer recommendation** | Ranked by files covered × commit recency × score formula |
| **Risk scoring** | Objective formula: blast ratio + PageRank centrality + uncovered test ratio + churn |
| **Graph evidence** | Every Cypher query, its parameters, row count, and duration logged to the UI |
| **Most central functions** | `get_most_central(limit <= 20)` returns compact PageRank-ranked qname/file/score rows |
| **Bounded graph depth** | Hop depth 1 / 4 reruns the same analysis and renders graph-backed test proof paths |
| **Benchmark** | 40 PRs, graph vs. 5 baselines (most-recent-committer, flat-count, same-name test, grep-imports, title/@mention heuristic) |
| **Demo cache** | 5 pre-generated PR analyses; app works without a live AI key |
| **Dark UI** | React 18 + Vite + Cytoscape.js (fcose) — click any node to dim everything else |

---

## Architecture

```
impactgraph/
├── ingest/
│   ├── ast_parser.py       # Walk .py files via ast; build qnames + CALLS edges
│   ├── git_history.py      # pydriller → Author/Commit/TOUCHED edges
│   └── load_graph.py       # FalkorDB bulk-load (UNWIND batches of 500) + PageRank
├── graph/
│   ├── client.py           # GraphClient with evidence logging
│   ├── queries.py          # Q0–Q5: diff→fns, blast, tests, proof path, reviewers, centrality, churn
│   └── risk.py             # calculate_risk() — pure formula, no LLM
├── mcp_server/
│   └── server.py           # Stateless MCP server, 12 tools (each call takes repo); run: python -c "from mcp_server.server import mcp; mcp.run()"
├── agent/
│   ├── agent.py            # run_agent(): Gemini function calling over the tools, falls back to the fixed pipeline
│   ├── tools.py            # ToolBox: 7 graph tools used in-process by the agent
│   ├── mcp_server.py       # Stateful MCP server over ToolBox, 8 tools (set_diff first); run: FALKOR_HOST=localhost ./.venv/bin/python -m agent.mcp_server
│   ├── github_actions.py   # Comment, label, reviewers, pytest command (dry run by default)
│   ├── loop.py             # run_impact_agent() — orchestrates all queries + risk
│   ├── comment.py          # format_pr_comment() + validate_decision() hallucination filter
│   └── prompts.py          # Template-based summary generation
├── api/
│   └── main.py             # FastAPI: /health /repos /analyze /subgraph /ask /benchmark /demo/{id} /action/preview
├── benchmark/
│   ├── collect_prs.py      # Download PR data once, save as JSON
│   ├── run.py              # Benchmark runner (graph queries only, no LLM)
│   ├── baselines.py        # 5 baselines (incl. title/@mention heuristic)
│   └── results.md          # Results table
├── web/                    # React 18 + Vite frontend
│   └── src/
│       ├── App.jsx          # Main layout: topbar + left panel + right panel
│       ├── api.js           # Fetch wrappers for all endpoints
│       └── components/
│           ├── RiskCard.jsx        # Gauge + 4-factor bars
│           ├── BlastPanel.jsx      # Blast radius list (click → highlight graph)
│           ├── TestsPanel.jsx      # Tests + "No test reaches this change" finding
│           ├── ReviewersPanel.jsx  # Ranked reviewers
│           ├── AskBox.jsx          # POST /ask
│           ├── GraphCanvas.jsx     # Cytoscape.js canvas, fcose layout
│           ├── EvidenceTab.jsx     # Cypher + params + rows + Copy button
│           └── BenchmarkTab.jsx    # Metric bars + per-PR table + limitations
├── demo_cache/             # 5 pre-generated PR analyses
├── queries.cypher          # All Cypher queries (canonical)
├── AGENTS.md               # Source of truth for schema + coding rules
└── docker-compose.yml      # FalkorDB + API
```

---

## Graph schema

```
Nodes:  File {path, loc}
        Function {qname, name, file, start, end, pagerank}
        Test      ← extra label on Function when name starts with test_ in tests/
        Author {email, name}
        Commit {sha, ts, msg}

Edges:  (File)   -[:DEFINES]->  (Function)
        (Function)-[:CALLS]->   (Function)
        (File)   -[:IMPORTS]->  (File)
        (Author) -[:AUTHORED]-> (Commit)
        (Commit) -[:TOUCHED {added, deleted}]-> (File)
```

> **Honest limit:** call links are name-based and approximate. Documented here so you know.

---

## Local setup

### Prerequisites

- Python 3.11+
- Node.js 18+
- Docker + Docker Compose
- A GitHub personal access token (for ingestion only)

**Platform note:** the commands below are written for macOS and Linux. On Windows, use WSL2 with Docker Desktop and run every command inside WSL2. Native Windows is not tested; the Python path differs there (.venv\Scripts\python instead of ./.venv/bin/python).

### 1 — Clone & environment

```bash
git clone https://github.com/dhhhhruv/ImpactGraph.git
cd ImpactGraph

python3.11 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

Copy the example env file and fill in your tokens:

```bash
cp .env.example .env
# Edit .env:
#   GITHUB_TOKEN=ghp_...
#   FALKOR_HOST=localhost
#   FALKOR_PORT=6379
#   LLM_API_KEY=...            # optional; without it the fixed pipeline runs
#   LLM_MODEL=gemini-3.6-flash
#   LLM_MODEL_FALLBACK=gemini-3.5-flash
```

### 2 — Start FalkorDB

```bash
docker compose up falkordb -d
# Verify:
docker compose ps
# FalkorDB browser UI → http://localhost:3000
```

### 3 — Ingest borgbase/vorta

```bash
# Clone the target repo
mkdir -p repos && git clone https://github.com/borgbase/vorta repos/vorta

# Build the graph (takes ~2–3 min on first run; time varies by machine)
./.venv/bin/python -m ingest.load_graph --repo borgbase/vorta --src repos/vorta --rebuild
```

This bulk-loads about 1,900 nodes and 4,800 edges, runs PageRank, and prints a summary.

### 4 — Start the API

```bash
uvicorn api.main:app --reload --port 8000
# Health check → http://localhost:8000/health
```

### 5 — Start the frontend

```bash
npm --prefix web install
npm --prefix web run dev
# → http://localhost:5173
```

Open `http://localhost:5173`. Click **Demo** to explore pre-computed results, or enter a PR number and click **⚡ Analyze**.

### 6 — Run tests

```bash
pytest tests/ -v
# Expected: all tests pass (109 at the time of writing)
```

---

## Running the benchmark

```bash
# Download PR data (one-time, saves to benchmark/prs.json)
# (optional: prs.json is already included; this calls the GitHub API and overwrites it)
# Repo comes from the TARGET_REPO env var (default borgbase/vorta); the count is fixed at 40.
TARGET_REPO=borgbase/vorta ./.venv/bin/python -m benchmark.collect_prs

# Run benchmark (graph queries only, no LLM)
./.venv/bin/python -m benchmark.run --repo-path repos/vorta

# Results → benchmark/results.md and benchmark/results.json
```

---

## Docker (full stack)

```bash
# Needs a .env file first (see above), because the api service reads it.
docker compose up -d --build
# API  → http://localhost:8000
# FalkorDB browser → http://localhost:3000
# Docker starts FalkorDB and the API only. Run the UI with the Vite dev server,
# which proxies /api to localhost:8000 (a plain static host would not):
npm --prefix web install
npm --prefix web run dev
# UI   → http://localhost:5173
```

---

## API reference

| Method | Endpoint | Description |
|---|---|---|
| GET | `/health` | API + FalkorDB status |
| GET | `/repos` | List ingested repositories |
| POST | `/analyze` | Full impact analysis on a PR diff |
| GET | `/subgraph` | Cytoscape-formatted subgraph for changed functions |
| POST | `/ask` | Answer free-form questions from the graph |
| GET | `/benchmark` | Latest benchmark results JSON |
| GET | `/demo/{id}` | Pre-generated demo PR (id 1–5) |
| GET | `/demo/featured?max_hops=1..6` | Featured real PR with cached results filtered to hop depth |

### Example: analyze a change

```bash
curl -X POST http://localhost:8000/analyze \
  -H "Content-Type: application/json" \
  -d '{
    "repo": "borgbase/vorta",
    "diff_hunks": [{"path": "src/vorta/scheduler/execution.py", "start": 5, "end": 25}],
    "head_sha": "abc123"
  }'
```
---

## License

MIT
