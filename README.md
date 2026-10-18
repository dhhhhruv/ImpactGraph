# ImpactGraph

> **Graph-powered pull request impact analysis.** When a PR arrives, ImpactGraph asks a FalkorDB graph of your codebase and its git history: *what can this change break, which tests should run, who should review it, how risky is it?* Every claim in the output carries its graph path.

**Hackathon:** Graph Hacks (WeMakeDevs x FalkorDB), **Track 01**.

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

**Target repo:** [`borgbase/vorta`](https://github.com/borgbase/vorta) (open-source backup client).

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
# Expected: all tests pass (92 at the time of writing)
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

## UI walkthrough

**Top bar:** repo selector · PR number input · Analyze button · Dry-run toggle · Graph on/off · Hop depth (1 / 4) · Demo mode

### Demo video script notes (≈2:30)

1. Open the featured real PR, [borgbase/vorta#2560](https://github.com/borgbase/vorta/pull/2560), and ask which tests reach `SchedulerExecution.create_backup`. The same-name baseline finds **0** files.
2. At **Hop depth 1**, show the 14 tests that call `create_backup` directly, each with its proof path. Switch the same question to **Hop depth 4**; the blast radius grows from 1 caller to 13 and the test list from 14 to 30 (the query caps at 30), reached through scheduler state and timer calls, with each path drawn in the graph.
3. Toggle **Graph OFF** to compare the flat same-name baseline with the graph findings.
4. Close on outcomes (`answered_with_path` / `not_in_graph` / `unknown_name` / `cached`) — empty means not modelled, never "safe".

The featured analysis was regenerated on 2026-10-18 from the live FalkorDB graph (`impact_borgbase_vorta`) and cached in `demo_cache/featured.json`. Test lists are capped at 30 rows per query, so counts at 30 are lower bounds.

**Left panel (40%):**
- Evidence-Bound Summary (a fixed template over the tool results; the model's notes, if any, are shown separately and only names are checked)
- Risk card — score, label, 4-factor breakdown bars
- Blast radius — clickable list; clicking a row dims all non-adjacent graph nodes
- Tests to run — with `pytest` command and one-click copy; "**Finding: No test reaches this change**" when empty
- Suggested reviewers — ranked by coverage + recency
- Ask the graph — free-form questions answered by live Cypher

**Right panel (60%):**
- **Graph tab** — Cytoscape.js canvas (fcose layout); changed=red, callers=orange, tests=green; click any node to highlight its neighborhood (everything else dims to 20%); node size follows PageRank; capped at 150 nodes
- **Graph OFF** — flat baseline view beside the graph answer
- **Evidence tab** — every Cypher query with params, row count, duration, and a Copy button
- **Benchmark tab** — metric bars (ImpactGraph vs baselines vs title/@mention heuristic), per-PR table, method & limitations

---

## Benchmark results

40 real merged PRs from `borgbase/vorta`, chosen by the written rule in [`benchmark/SELECTION_RULE.md`](benchmark/SELECTION_RULE.md). Ground truth is who actually reviewed each PR and which tests the PR actually touched. Full table: [`benchmark/results.md`](benchmark/results.md).

| Method | Reviewer Hit@3 | Hit@5 | MRR | Test recall@5 |
| --- | ---: | ---: | ---: | ---: |
| **ImpactGraph** | 0.80 | 0.88 | 0.73 | 0.51 |
| flat_commit_count | 0.83 | 0.88 | 0.72 | n/a |
| most_recent_committer | 0.20 | 0.20 | 0.20 | n/a |
| grep_imports | n/a | n/a | n/a | 0.57 |
| same_name_test | n/a | n/a | n/a | 0.46 |
| llm_only | 0.00 | 0.00 | 0.00 | 0.00 |

**What this shows, honestly:** the graph is not the best at every single metric. A plain commit-count ranking is essentially equal to it on reviewers in this sample (Hit@3 0.83 vs 0.80, the same Hit@5, MRR 0.72 vs 0.73; one PR is worth 0.025, so I treat it as a tie), and a grep-imports heuristic beats it slightly on test recall. What the graph does is deliver both answers from one structure, reviewers and affected tests together, with a traceable path for each claim. No single baseline does both. The title/@mention heuristic baseline (a stand-in for an LLM with no graph evidence; no model is actually called) scores zero on both metrics. The benchmark maps each changed file to all of its functions (whole file), not to the changed hunks the demo uses, so its per-PR blast sizes are not comparable to the demo's numbers.

Baselines compared:
- **most_recent_committer**: last author to touch each changed file
- **flat_commit_count**: authors ranked by raw commit count
- **same_name_test**: `tests/test_<stem>.py` naming heuristic
- **grep_imports**: test files importing changed modules
- **Title/@mention heuristic** (code name `llm_only`; no model is called): title + @mention heuristic, zero graph evidence

Test recall is measured over the PRs that actually edited tests.

### Author identity mapping

The graph stores git commit display names (for example "Manu"), while GitHub ground truth uses usernames (for example "m3nu"). Before mapping, every reviewer metric was 0.0 for every method because the two never matched. `benchmark/map_authors.py` resolves each commit email to a GitHub login via the GitHub commits API (90 of 95 unique author emails resolved; the rest fall back to the raw name). The result is saved in `benchmark/author_map.json`. These emails already appear in vorta's public git history.

### Call-graph accuracy

A 15-function spot check against the vorta source (seed 42, evidence in [`benchmark/spotcheck.md`](benchmark/spotcheck.md)) found no caller in the graph that is absent from the code. The graph is incomplete, though. It does not model:

- **Constructor calls.** All 72 `__init__` methods show zero callers, so a change to a constructor looks uncalled.
- **Qt signal connections.** A slot wired with `.connect(self.slot)` has no caller in the graph.
- **Calls through attribute receivers**, such as `self._state.record_finish(...)`.
- **Which class a shared method name reaches.** Same-named methods (for example the three `deliver` methods) share their callers.

When the graph finds nothing, the report says so instead of claiming the change is safe.

### Limits

- 40 PRs from one repository, so small differences between methods are within noise.
- Reviewers may be assigned for reasons other than expertise.
- A PR that doesn't edit tests doesn't mean no test was needed.
- Call graph links are name-based and approximate.

Reviewer history is cut at each PR's base commit time. Test and blast-radius queries run on a single final snapshot of the repo (they take no timestamp), so absolute test recall may be optimistic for every method. The benchmark makes no claim of zero leakage.

---

## Disclosure

AI coding assistants (Google Antigravity, Cursor) were used in this project to accelerate development. All graph schema, query logic, risk formulas, and benchmark methodology were designed and reviewed by the team. The summary sentence is built by a fixed template. A Gemini model chooses which graph tools to run and may add notes; every fact comes from tool results.

---

## License

MIT
