Project: ImpactGraph (Python 3.11, FastAPI, FalkorDB, React). Read AGENTS.md first; it is the source of truth.
Naming: snake_case functions/variables, PascalCase classes, UPPER_SNAKE for Cypher constants (Q_BLAST, Q_TESTS).
Never change schema or query names without updating AGENTS.md and queries.cypher.
Functions under 40 lines, type hints, no new dependencies without asking.
Every tool returns compact JSON. Never return source code to the LLM.
Pass values as query parameters; only the hop limit is formatted into a query after int() validation.
Write a pytest test for each query or function you add. Output only the changed files. No secrets in the repo.

---
TASK: implement graph/client.py, graph/queries.py, graph/risk.py and mcp_server/server.py.
- Queries Q0-Q5 are in queries.cypher. Add validated-integer hop insertion for Q1.
- Log every query as evidence: cypher, params, row count, run time (ms).
- risk.py (pure Python, no LLM): s = 0.35*min(blast/50,1) + 0.25*max_pagerank_pct + 0.25*(1-covered_ratio) + 0.15*churn_norm; label low <0.33, medium <0.66, else high. Test boundaries 0.33 and 0.66 and all-zero and all-one inputs. If no test reaches the change, covered_ratio=0 and that is a finding, not an error.
- MCP tools (FastMCP): map_diff_to_functions, get_blast_radius, get_affected_tests, find_reviewers, get_risk, explain_path, get_most_central(limit <= 20). The seven compact-JSON query tools are blast_radius, affected_tests, test_proof_path, find_reviewers, centrality, recent_churn, get_most_central.
- Before an analysis query, confirm every function, test, file, and person input exists in the graph. Return unknown_name and run no analysis query for unknown names. Existence checks must use ro_query.
- All non-writing graph queries use GraphClient.ro_query. Keep writes limited to ingestion and PageRank score storage. Load CALLS with MERGE.
- explain_path and test proof paths use Cypher shortestPath with a bound and referenced relationship alias. Browser verification against CALL algo.SPpaths(...) is pending if FalkorDB Browser is unavailable.
- Add get_most_central using stored PageRank scores and compact qname/file/score rows. Cap limit at 20; test the query and outcome behavior.
- Reviewer score in Python: 0.5*(files_covered/len(files)) + 0.3*(commits/max_commits) + 0.2*recency, recency = 0.5**(age_days/180). Exclude the PR author.
- Write pytest tests against a tiny fixture graph (10 functions, 3 tests, 3 authors) with known expected results, running on a real FalkorDB container.
