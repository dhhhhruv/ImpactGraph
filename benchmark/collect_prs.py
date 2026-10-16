"""GitHub PR collector for ImpactGraph benchmark.

Strictly follows benchmark/SELECTION_RULE.md:
- Target: 40 most recent closed & merged PRs that touched at least one .py file and have >=1 human review.
- Excludes bot authors and PRs with no .py changes.
- Saves raw responses to benchmark/raw_cache/ so GitHub is NEVER called again during benchmarking.
- Outputs benchmark/prs.json.
"""

import json
import os
import sys
import time
import urllib.request
from typing import Any, Dict, List, Optional, Tuple

BOT_SUFFIXES = ("[bot]", "-bot", "dependabot", "renovate", "codecov")


def is_bot(username: str) -> bool:
    """Check if a username belongs to an automated bot account."""
    lower = username.lower()
    return any(lower.endswith(s) or lower.startswith(s) for s in BOT_SUFFIXES)


def github_get(url: str, token: Optional[str] = None) -> Tuple[Any, Dict[str, str]]:
    """Perform GET request to GitHub API with rate limit monitoring."""
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "ImpactGraph-Benchmark")
    if token:
        req.add_header("Authorization", f"Bearer {token}")

    try:
        with urllib.request.urlopen(req) as resp:
            headers = dict(resp.headers)
            rem = int(headers.get("x-ratelimit-remaining", 60))
            if rem < 5:
                reset_ts = int(headers.get("x-ratelimit-reset", time.time() + 60))
                sleep_sec = max(reset_ts - int(time.time()) + 2, 2)
                time.sleep(sleep_sec)
            body = resp.read().decode("utf-8")
            return json.loads(body), headers
    except urllib.error.HTTPError as e:
        if e.code == 403 and "rate limit" in str(e).lower():
            reset_ts = int(e.headers.get("x-ratelimit-reset", time.time() + 60))
            time.sleep(max(reset_ts - int(time.time()) + 2, 5))
            return github_get(url, token)
        raise


def fetch_pr_files(repo: str, pr_num: int, token: Optional[str]) -> List[Dict[str, Any]]:
    """Fetch all files touched by a PR."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}/files?per_page=100"
    files, _ = github_get(url, token)
    return files if isinstance(files, list) else []


def fetch_pr_reviews(repo: str, pr_num: int, token: Optional[str]) -> List[str]:
    """Fetch human reviewers for a PR excluding bots."""
    url = f"https://api.github.com/repos/{repo}/pulls/{pr_num}/reviews?per_page=100"
    reviews, _ = github_get(url, token)
    if not isinstance(reviews, list):
        return []

    reviewers = set()
    for rev in reviews:
        user = rev.get("user", {}).get("login", "")
        if user and not is_bot(user):
            reviewers.add(user)
    return sorted(list(reviewers))


def process_pr(
    repo: str, pr: Dict[str, Any], token: Optional[str], cache_dir: str
) -> Optional[Dict[str, Any]]:
    """Evaluate PR against selection rules and cache raw data."""
    if not pr.get("merged_at"):
        return None
    author = pr.get("user", {}).get("login", "")
    if not author or is_bot(author):
        return None

    pr_num = pr["number"]
    files = fetch_pr_files(repo, pr_num, token)
    py_files = [f["filename"] for f in files if f["filename"].endswith(".py")]
    if not py_files:
        return None

    reviewers = fetch_pr_reviews(repo, pr_num, token)
    human_reviewers = [r for r in reviewers if r != author]
    if not human_reviewers:
        return None

    test_files = [f for f in py_files if "test" in f.lower()]

    cache_path = os.path.join(cache_dir, f"{pr_num}.json")
    with open(cache_path, "w") as f:
        json.dump({"pr": pr, "files": files, "reviewers": human_reviewers}, f, indent=2)

    return {
        "number": pr_num,
        "title": pr.get("title", ""),
        "author": author,
        "base_sha": pr.get("base", {}).get("sha", ""),
        "head_sha": pr.get("head", {}).get("sha", ""),
        "merged_at": pr.get("merged_at"),
        "changed_py_files": py_files,
        "ground_truth_reviewers": human_reviewers,
        "ground_truth_tests": test_files,
        "has_test_changes": len(test_files) > 0,
    }


def collect_prs(repo: str, target_count: int = 40) -> List[Dict[str, Any]]:
    """Collect target count PRs matching SELECTION_RULE.md."""
    token = os.environ.get("GITHUB_TOKEN")
    base_dir = os.path.dirname(os.path.abspath(__file__))
    cache_dir = os.path.join(base_dir, "raw_cache")
    os.makedirs(cache_dir, exist_ok=True)

    collected: List[Dict[str, Any]] = []
    page = 1

    while len(collected) < target_count and page <= 15:
        url = f"https://api.github.com/repos/{repo}/pulls?state=closed&per_page=50&page={page}"
        prs, _ = github_get(url, token)
        if not prs:
            break

        for pr in prs:
            item = process_pr(repo, pr, token, cache_dir)
            if item:
                collected.append(item)
                print(f"[{len(collected)}/{target_count}] Selected PR #{item['number']}: {item['title'][:50]}")
                if len(collected) >= target_count:
                    break
        page += 1

    out_file = os.path.join(base_dir, "prs.json")
    with open(out_file, "w") as f:
        json.dump(collected, f, indent=2)

    print(f"\nSaved {len(collected)} PRs to {out_file}")
    print(f"Raw API responses cached in {cache_dir}")
    return collected


if __name__ == "__main__":
    target_repo = os.environ.get("TARGET_REPO", "borgbase/vorta")
    collect_prs(target_repo, target_count=40)
