Project: ImpactGraph (Python 3.11, FastAPI, FalkorDB, React). Read AGENTS.md first; it is the source of truth.
Naming: snake_case functions/variables, PascalCase classes, UPPER_SNAKE for Cypher constants (Q_BLAST, Q_TESTS).
Never change schema or query names without updating AGENTS.md and queries.cypher.
Functions under 40 lines, type hints, no new dependencies without asking.
Every tool returns compact JSON. Never return source code to the LLM.
Pass values as query parameters; only the hop limit is formatted into a query after int() validation.
Write a pytest test for each query or function you add. Output only the changed files. No secrets in the repo.

---
TASK: implement agent/loop.py, prompts.py, comment.py, github_actions.py and api/main.py (endpoints in the plan: /health /repos /analyze /analyze/stream /subgraph /benchmark /webhook/github, plus POST /ask).
- Use prompts/AGENT_RUNTIME_PROMPT.md as the system prompt. Max 6 tool calls, temperature 0.
- Guard: must call map_diff_to_functions first and must have blast radius, tests, reviewers and risk before finishing; force any missing call.
- Cache every tool result per PR head SHA.
- llm_call() is ONE swappable function with a fallback chain: primary model, then backup account/model, then template-only output.
- LLM role (about 40 percent): chooses next tool, digs deeper on odd results, picks between close reviewer candidates, writes a short why-it-matters per section, and answers follow-ups via POST /ask which queries the graph again. Never computes numbers.
- comment.py: template-rendered comment starting with hidden marker <!-- impactgraph -->; update existing comment, do not repost. validate_decision(decision) drops any LLM text that mentions a function, test, file or person not present in the evidence.
- github_actions.py: post/update comment, request top reviewers (collaborators only; otherwise name them), add label risk:low|medium|high, print the exact pytest command. --dry-run and DRY_RUN=true never touch GitHub.
- DEMO_MODE=true serves cached decision objects from demo_cache/.
- Tests: a fake LLM that skips tools must still end with all four required tools called; validate_decision rejects a made-up function name.
