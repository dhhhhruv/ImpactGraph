# PR selection rule (written BEFORE any benchmark run - do not edit after seeing results)
- Source: closed PRs of the target repo that were merged.
- Take the most recent 40 that: changed at least one .py file, and have at least one human review.
- Exclude bot-authored PRs and PRs with no changed lines in .py files.
- Ground truth reviewers: humans who reviewed or approved, minus the PR author and bots.
- Ground truth tests: test files the PR added or changed. Report PRs with and without test changes separately.
- Save the final list in prs.json and cache raw GitHub responses as JSON. Never call GitHub again afterwards.
- Hand-check about 10 PRs manually and report that separately.
- Limits to state in README: reviewers are sometimes assigned for non-expertise reasons; a PR that did not touch a test does not mean no test was needed; call graph is name-based.
