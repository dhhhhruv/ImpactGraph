"""Resolve git commit-author emails to GitHub usernames via the commits API.

Writes benchmark/author_map.json: {email: {"name": ..., "github_login": ... or null}}
Only hits GitHub once per unique author (95 calls expected), using GITHUB_TOKEN.
"""

import json
import os
import time
import urllib.request
from pathlib import Path

from graph.client import GraphClient

BENCH_DIR = Path(__file__).resolve().parent
OUT_FILE = BENCH_DIR / "author_map.json"


def github_get(url, token):
    req = urllib.request.Request(url)
    req.add_header("Accept", "application/vnd.github+json")
    req.add_header("User-Agent", "ImpactGraph-Benchmark")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    with urllib.request.urlopen(req) as resp:
        return json.loads(resp.read().decode("utf-8"))


def main():
    token = os.environ.get("GITHUB_TOKEN")
    repo = os.environ.get("TARGET_REPO", "borgbase/vorta")

    client = GraphClient(host="localhost", port=6379, graph_name="impact_borgbase_vorta")
    rows, _ = client.ro_query(
        "MATCH (a:Author)-[:AUTHORED]->(c:Commit) "
        "RETURN a.email AS email, a.name AS name, c.sha AS sha LIMIT 1",
        {},
    )
    # The above LIMIT 1 is wrong for getting one-per-author; use a proper query:
    rows, _ = client.ro_query(
        "MATCH (a:Author)-[:AUTHORED]->(c:Commit) "
        "WITH a, collect(c.sha)[0] AS sha "
        "RETURN a.email AS email, a.name AS name, sha",
        {},
    )

    mapping = {}
    for i, row in enumerate(rows, 1):
        email, name, sha = row["email"], row["name"], row["sha"]
        login = None
        try:
            data = github_get(f"https://api.github.com/repos/{repo}/commits/{sha}", token)
            author = data.get("author")
            login = author.get("login") if author else None
        except Exception as e:
            print(f"[{i}/{len(rows)}] {email} -> ERROR: {e}")
        else:
            print(f"[{i}/{len(rows)}] {email} -> {login}")
        mapping[email] = {"name": name, "github_login": login}
        time.sleep(0.05)

    OUT_FILE.write_text(json.dumps(mapping, indent=2), encoding="utf-8")
    resolved = sum(1 for v in mapping.values() if v["github_login"])
    print(f"\nResolved {resolved}/{len(mapping)} authors to GitHub usernames")
    print(f"Saved to {OUT_FILE}")


if __name__ == "__main__":
    main()
