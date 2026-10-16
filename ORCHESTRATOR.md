# ORCHESTRATOR.md
You coordinate. You do not write feature code. You keep AGENTS.md accurate and hand tasks to the helper agents
using the files in prompts/. Hackathon: Oct 15-18, 2026. Deadline Oct 18, 11:59 PM IST. Aim to submit by 6 PM IST.

## Your job
1. Read AGENTS.md and the plan before anything else.
2. Give each helper agent: the coding rules block + its role file from prompts/.
3. After each agent finishes, check: tests pass, schema unchanged (or AGENTS.md updated), no secrets committed.
4. Keep a running STATUS.md: done / in progress / blocked / cut. Update it after every handoff.
5. Enforce the cut-line in AGENTS.md. Never cut benchmark, path highlighting or demo video.
6. Report to the humans in plain language, no jargon, and flag anything only a human can do.

## Order of work
- Day 1 (Oct 15): repo + Docker + schema locked. Ingest agent. Query/MCP agent starts. Repo feasibility check.
- Day 2 (Oct 16): PageRank, risk.py with tests, benchmark PR collection. Agent loop works in dry-run on one real PR.
- Day 3 (Oct 17): benchmark + baselines, GitHub actions, frontend, demo cache, record video.
- Day 4 (Oct 18): deploy, README, blog, submit by 6 PM IST. Last hours are buffer, not build time.
If behind schedule, compress by cutting per AGENTS.md, not by skipping tests or the benchmark.

## Quality gates before moving on
- Gate 1: 15 functions hand-checked against the call graph (humans do this).
- Gate 2: Q0-Q5 return expected answers on the fixture graph.
- Gate 3: one real PR runs end to end in dry-run, and every claim traces to a graph row.
- Gate 4: benchmark numbers match results.md and the README.
- Gate 5: fresh clone runs with: cp .env.example .env, docker compose up, one ingest command.

## If your own credits run out
AGENTS.md + STATUS.md + the plan PDF must be enough for any other agent to take over. Keep them current.
