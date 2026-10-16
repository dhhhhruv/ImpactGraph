"""Git history extractor using pydriller for ImpactGraph."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Dict, List, Set

BOT_SUBSTRINGS = ("[bot]", "-bot", "dependabot", "renovate", "codecov")


def is_bot(name: str, email: str) -> bool:
    """Detect bot author based on common username or email patterns."""
    combined = f"{name} {email}".lower()
    return any(b in combined for b in BOT_SUBSTRINGS)


def extract_history(repo_path: Path, max_commits: int = 1500) -> Dict[str, Any]:
    """Extract commits, authors, and touched files using pydriller."""
    if not (repo_path / ".git").exists() and not (repo_path.parent / ".git").exists():
        return {"authors": [], "commits": [], "authored": [], "touched": []}

    try:
        from pydriller import Repository
    except ImportError:
        return {"authors": [], "commits": [], "authored": [], "touched": []}

    authors_set: Set[str] = set()
    authors: List[Dict[str, str]] = []
    commits: List[Dict[str, Any]] = []
    authored: List[Dict[str, str]] = []
    touched: List[Dict[str, Any]] = []

    try:
        count = 0
        for commit in Repository(str(repo_path), order="reverse").traverse_commits():
            if commit.merge:
                continue
            author_name = commit.author.name or "Unknown"
            author_email = commit.author.email or f"{author_name}@unknown.local"

            if is_bot(author_name, author_email):
                continue

            if author_email not in authors_set:
                authors_set.add(author_email)
                authors.append({"email": author_email, "name": author_name})

            ts = int(commit.committer_date.timestamp())
            msg = (commit.msg or "").split("\n")[0][:120]

            commits.append({"sha": commit.hash, "ts": ts, "msg": msg})
            authored.append({"email": author_email, "sha": commit.hash})

            for mod in commit.modified_files:
                rel_path = mod.new_path or mod.old_path
                if rel_path and rel_path.endswith(".py"):
                    touched.append({
                        "sha": commit.hash,
                        "path": rel_path,
                        "added": mod.added_lines,
                        "deleted": mod.deleted_lines,
                    })

            count += 1
            if count >= max_commits:
                break
    except Exception:
        pass

    return {
        "authors": authors,
        "commits": commits,
        "authored": authored,
        "touched": touched,
    }
