# ImpactGraph Benchmark Results

Graph queries run directly in Python (no LLM). All authorship uses `c.ts < merged_at` (no future leakage).

## Summary

| Method | Hit@3 | Hit@5 | MRR | Test recall@5 (with tests) | Avg tests (with) | Avg tests (without) |
| --- | ---: | ---: | ---: | ---: | ---: | ---: |
| graph | 0.8000 | 0.8750 | 0.7473 | 0.5139 | 17.7667 | 13.6000 |
| most_recent_committer | 0.2250 | 0.2250 | 0.2250 | 0.0000 | 0.0000 | 0.0000 |
| flat_commit_count | 0.8000 | 0.8750 | 0.7419 | 0.0000 | 0.0000 | 0.0000 |
| same_name_test | 0.0000 | 0.0000 | 0.0000 | 0.4597 | 1.0333 | 0.8000 |
| grep_imports | 0.0000 | 0.0000 | 0.0000 | 0.5736 | 8.4000 | 6.3000 |
| llm_only | 0.0000 | 0.0000 | 0.0000 | 0.0000 | 0.9667 | 1.0000 |

## Method

- **graph**: Q3 reviewers + Q2a tests via call graph.
- **most_recent_committer**: latest author on changed files.
- **flat_commit_count**: authors ranked by raw commit count.
- **same_name_test**: `tests/test_<stem>.py` naming heuristic.
- **grep_imports**: `tests/` files importing changed modules.
- **llm_only**: title/@mention heuristic, no graph.

## Limits

- Reviewers may be assigned for non-expertise reasons.
- A PR without test edits does not mean no test was needed.
- Call graph links are name-based and approximate.
