#!/usr/bin/env python3
"""Call-graph spot-check script for ImpactGraph.

Picks 15 random functions from FalkorDB and prints their callers
so humans can hand-verify accuracy and quantify call-link noise.
Part of Quality Gate 1 in ORCHESTRATOR.md and Section 24 of Build Plan.
"""

from __future__ import annotations

import argparse
from pathlib import Path
import random
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from graph.client import GraphClient


def run_spotcheck(repo: str = "borgbase/vorta", sample_size: int = 15, seed: int = 42) -> List[Dict[str, Any]]:
    """Sample functions and inspect their callers in the graph."""
    graph_name = f"impact_{repo.replace('/', '_').replace('-', '_')}"
    client = GraphClient(host="localhost", port=6379, graph_name=graph_name)

    # 1. Fetch all non-test functions
    q_all = "MATCH (f:Function) WHERE NOT f:Test RETURN f.qname AS qname, f.file AS file, f.start AS start, f.end AS end"
    rows, _ = client.ro_query(q_all)
    if not rows:
        print(f"Error: No functions found in graph '{graph_name}'. Run ingestion first.", file=sys.stderr)
        return []

    print(f"Total functions in graph: {len(rows)}")
    rng = random.Random(seed)
    sampled = rng.sample(rows, min(sample_size, len(rows)))

    results = []
    print("\n" + "=" * 80)
    print(f"CALL-GRAPH SPOT-CHECK: {len(sampled)} FUNCTIONS ({repo})")
    print("=" * 80)

    for i, fn in enumerate(sampled, 1):
        qname = fn["qname"]
        file_path = fn.get("file", "unknown")
        loc = f"L{fn.get('start', '?')}-L{fn.get('end', '?')}"

        # Fetch incoming callers
        q_callers = """
        MATCH (c:Function)-[:CALLS]->(t:Function {qname: $qname})
        RETURN c.qname AS caller, c.file AS file
        LIMIT 10
        """
        caller_rows, _ = client.ro_query(q_callers, {"qname": qname})
        callers = [r.get("caller") for r in caller_rows]

        results.append({
            "index": i,
            "qname": qname,
            "file": file_path,
            "lines": loc,
            "callers": callers,
            "caller_count": len(callers),
        })

        print(f"\n[{i:02d}/15] {qname}")
        print(f"      Defined in: {file_path} ({loc})")
        if callers:
            print(f"      Direct Callers ({len(callers)}):")
            for c in callers:
                print(f"        ← {c}")
        else:
            print("      Direct Callers: None (root / entrypoint / uncalled)")

    print("\n" + "=" * 80)
    print(f"Spot-check complete. Sampled {len(results)} functions.")
    print("=" * 80)
    return results


def main() -> int:
    parser = argparse.ArgumentParser(description="Call-graph spotcheck")
    parser.add_argument("--repo", default="borgbase/vorta", help="Repository graph to audit")
    parser.add_argument("--count", type=int, default=15, help="Number of functions to check")
    parser.add_argument("--seed", type=int, default=42, help="Random seed for reproducibility")
    args = parser.parse_args()

    results = run_spotcheck(repo=args.repo, sample_size=args.count, seed=args.seed)
    return 0 if results else 1


if __name__ == "__main__":
    sys.exit(main())
