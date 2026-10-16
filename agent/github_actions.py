"""GitHub Actions integration for ImpactGraph PR change-impact analysis."""

from __future__ import annotations

import argparse
import os
import sys
from typing import Any, Dict, List, Optional, Tuple

from agent.comment import MARKER, format_pr_comment
from agent.loop import run_impact_agent
from graph.client import GraphClient


def get_github_client(token: Optional[str]) -> Any:
    """Initialize PyGithub Github client."""
    if not token:
        return None
    try:
        from github import Github
        return Github(token)
    except ImportError:
        return None


def fetch_pr_diff_hunks(pr: Any) -> List[Dict[str, Any]]:
    """Extract patch line ranges as diff hunks from PyGithub PR files."""
    hunks: List[Dict[str, Any]] = []
    for file in pr.get_files():
        filename = file.filename
        if not filename.endswith(".py"):
            continue
        patch = file.patch or ""
        # Simple hunk parsing for @@ -start,len +start,len @@
        start_line = 1
        end_line = file.additions + file.deletions or 100
        for line in patch.splitlines():
            if line.startswith("@@"):
                try:
                    parts = line.split("+")[1].split("@@")[0].strip().split(",")
                    start_line = int(parts[0])
                    length = int(parts[1]) if len(parts) > 1 else 1
                    end_line = start_line + length
                    break
                except Exception:
                    pass
        hunks.append({"path": filename, "start": start_line, "end": end_line})
    return hunks


def find_existing_comment(pr: Any) -> Optional[Any]:
    """Find previous ImpactGraph comment containing the hidden marker."""
    for comment in pr.get_issue_comments():
        if MARKER in (comment.body or ""):
            return comment
    return None


def post_or_update_comment(pr: Any, comment_body: str, dry_run: bool = False) -> str:
    """Idempotently post or update PR comment using hidden marker."""
    if dry_run or pr is None:
        return "dry_run_comment_skipped"

    existing = find_existing_comment(pr)
    if existing:
        existing.edit(comment_body)
        return f"updated_comment_{existing.id}"
    else:
        created = pr.create_issue_comment(comment_body)
        return f"created_comment_{created.id}"


def apply_risk_label(pr: Any, risk_label: str, dry_run: bool = False) -> str:
    """Apply risk:low | risk:medium | risk:high label to PR."""
    label_name = f"risk:{risk_label.lower()}"
    if dry_run or pr is None:
        return f"dry_run_label_{label_name}"

    try:
        pr.as_issue().add_to_labels(label_name)
        return f"applied_{label_name}"
    except Exception as e:
        return f"failed_label_{label_name}_{e}"


def request_reviewers(
    pr: Any,
    repo_obj: Any,
    reviewers: List[Dict[str, Any]],
    dry_run: bool = False,
) -> List[str]:
    """Request review from top reviewers if they are collaborators."""
    if dry_run or pr is None or repo_obj is None:
        return [str(r.get("author")) for r in reviewers[:2]]

    candidates = [str(r.get("author")) for r in reviewers if r.get("author")]
    requested = []
    for cand in candidates[:3]:
        try:
            if repo_obj.has_in_collaborators(cand):
                pr.create_review_request(reviewers=[cand])
                requested.append(cand)
        except Exception:
            pass
    return requested


def generate_pytest_command(affected_tests: List[Dict[str, Any]]) -> str:
    """Format exact pytest command targeting affected test files."""
    test_files = sorted(list({t.get("file") for t in affected_tests if t.get("file")}))
    if not test_files:
        return "# Finding: No test reaches this change"
    return f"pytest {' '.join(test_files)}"


def run_github_action(
    repo_name: str,
    pr_number: int,
    token: Optional[str] = None,
    dry_run: bool = True,
    client: Optional[GraphClient] = None,
) -> Dict[str, Any]:
    """Coordinate full GitHub Action execution flow."""
    token = token or os.environ.get("GITHUB_TOKEN")
    is_dry = dry_run or os.environ.get("DRY_RUN", "false").lower() == "true"

    graph_name = f"impact_{repo_name.replace('/', '_').replace('-', '_')}"
    host = os.environ.get("FALKOR_HOST", "localhost")
    port = int(os.environ.get("FALKOR_PORT", 6379))
    g_client = client or GraphClient(host=host, port=port, graph_name=graph_name)

    gh = get_github_client(token)
    pr_obj = None
    repo_obj = None
    diff_hunks = []
    head_sha = "HEAD"
    pr_author = None

    if gh and not is_dry:
        try:
            repo_obj = gh.get_repo(repo_name)
            pr_obj = repo_obj.get_pull(pr_number)
            diff_hunks = fetch_pr_diff_hunks(pr_obj)
            head_sha = pr_obj.head.sha
            pr_author = pr_obj.user.login
        except Exception as e:
            print(f"Warning: GitHub API error, falling back to mock: {e}", file=sys.stderr)

    if not diff_hunks:
        diff_hunks = [{"path": "src/vorta/scheduler/execution.py", "start": 5, "end": 25}]

    decision = run_impact_agent(
        client=g_client,
        diff_hunks=diff_hunks,
        head_sha=head_sha,
        pr_author=pr_author,
    )

    comment_text = format_pr_comment(decision)
    comment_status = post_or_update_comment(pr_obj, comment_text, dry_run=is_dry)

    risk_label = decision.get("risk", {}).get("label", "low")
    label_status = apply_risk_label(pr_obj, risk_label, dry_run=is_dry)

    requested = request_reviewers(pr_obj, repo_obj, decision.get("reviewers", []), dry_run=is_dry)
    test_cmd = generate_pytest_command(decision.get("affected_tests", []))

    result = {
        "repo": repo_name,
        "pr_number": pr_number,
        "dry_run": is_dry,
        "risk_label": risk_label,
        "risk_score": decision.get("risk", {}).get("score", 0.0),
        "comment_status": comment_status,
        "label_status": label_status,
        "requested_reviewers": requested,
        "pytest_command": test_cmd,
        "decision": decision,
    }
    return result


def main() -> int:
    """CLI entrypoint for running GitHub Action integration."""
    parser = argparse.ArgumentParser(description="ImpactGraph GitHub Action runner")
    parser.add_argument("--repo", default="borgbase/vorta", help="Target repository (e.g. owner/repo)")
    parser.add_argument("--pr", type=int, default=1, help="Pull request number")
    parser.add_argument("--token", default=None, help="GitHub token (defaults to GITHUB_TOKEN env var)")
    parser.add_argument("--dry-run", action="store_true", help="Execute without modifying GitHub")
    args = parser.parse_args()

    res = run_github_action(
        repo_name=args.repo,
        pr_number=args.pr,
        token=args.token,
        dry_run=args.dry_run,
    )
    print(f"ImpactGraph finished for {res['repo']} PR #{res['pr_number']}")
    print(f"Risk: {res['risk_label'].upper()} ({res['risk_score']})")
    print(f"Action: {res['comment_status']} | Label: {res['label_status']}")
    print(f"Suggested test command: {res['pytest_command']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
