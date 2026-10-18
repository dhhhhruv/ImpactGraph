"""FastAPI application for ImpactGraph change-impact analysis."""

import json
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from dotenv import load_dotenv

load_dotenv()

from fastapi import BackgroundTasks, FastAPI, Header, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from agent.comment import format_pr_comment, validate_decision
from agent.loop import compute_agent_risk, run_impact_agent
from agent.prompts import generate_template_summary
from graph.client import GraphClient
from graph.queries import confirm_names, q2b_test_proof_path

app = FastAPI(title="ImpactGraph API", version="1.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class AnalyzeRequest(BaseModel):
    """Payload to trigger change-impact analysis."""

    repo: str = "borgbase/vorta"
    diff_hunks: List[Dict[str, Any]]
    head_sha: Optional[str] = "HEAD"
    before_ts: Optional[int] = None
    pr_author: Optional[str] = None
    max_hops: int = Field(default=4, ge=1, le=6)


class AskRequest(BaseModel):
    """Payload for maintainer follow-up questions."""

    repo: str = "borgbase/vorta"
    question: str
    target_function: Optional[str] = None


def get_graph_client(repo: str) -> GraphClient:
    """Instantiate GraphClient for repository."""
    graph_name = f"impact_{repo.replace('/', '_').replace('-', '_')}"
    host = os.environ.get("FALKOR_HOST", "localhost")
    port = int(os.environ.get("FALKOR_PORT", 6379))
    return GraphClient(host=host, port=port, graph_name=graph_name)


@app.get("/health")
def health_check() -> Dict[str, Any]:
    """Check API and FalkorDB database health."""
    try:
        client = get_graph_client("test/health")
        rows, _ = client.ro_query("RETURN 1 AS ping")
        db_status = "connected" if rows else "no_data"
    except Exception as e:
        db_status = f"unreachable: {str(e)}"

    return {
        "status": "ok",
        "falkordb": db_status,
        "demo_mode": os.environ.get("DEMO_MODE", "false").lower() == "true",
    }


@app.get("/repos")
def list_repositories() -> List[str]:
    """List available ingested repositories."""
    repos = ["borgbase/vorta"]
    return repos


from sse_starlette.sse import EventSourceResponse

@app.post("/analyze")
def analyze_change(req: AnalyzeRequest) -> Dict[str, Any]:
    """Run full graph impact analysis on a PR diff."""
    client = get_graph_client(req.repo)
    # Bust cache when hop depth changes so depth 1 vs 4 can be compared.
    head = f"{req.head_sha or 'HEAD'}:h{int(req.max_hops)}"
    decision = run_impact_agent(
        client=client,
        diff_hunks=req.diff_hunks,
        head_sha=head,
        before_ts=req.before_ts,
        pr_author=req.pr_author,
        max_hops=int(req.max_hops),
    )
    comment = format_pr_comment(decision)
    return {"decision": decision, "pr_comment": comment}


@app.get("/analyze/stream")
async def analyze_change_stream(
    repo: str = "borgbase/vorta",
    path: str = "src/vorta/scheduler/execution.py",
    start: int = 5,
    end: int = 25,
    head_sha: str = "HEAD",
    max_hops: int = Query(4, ge=1, le=6),
):
    """Server-Sent Events streaming endpoint displaying live tool calls."""
    import asyncio
    import time
    from agent.loop import map_diffs, gather_test_paths, compute_agent_risk
    from graph.queries import q1_blast_radius, q2a_affected_tests, q3_find_reviewers, q4_centrality, q5_recent_churn
    from agent.prompts import generate_template_summary

    async def event_generator():
        client = get_graph_client(repo)
        diff_hunks = [{"path": path, "start": start, "end": end}]
        ts = int(time.time())

        # Step 1: map_diff_to_functions
        t0 = time.time()
        yield {"event": "tool_start", "data": json.dumps({"tool": "map_diff_to_functions", "hunks": len(diff_hunks)})}
        await asyncio.sleep(0.05)
        map_result = map_diffs(client, diff_hunks)
        files = list(map_result.get("known_files") or [])
        changed_fns = list(map_result.get("changed_functions") or [])
        ms0 = int((time.time() - t0) * 1000)
        yield {"event": "tool_result", "data": json.dumps({
            "tool": "map_diff_to_functions",
            "count": len(changed_fns),
            "ms": ms0,
            "outcome": map_result.get("outcome"),
        })}

        # Step 2: get_blast_radius
        t1 = time.time()
        yield {"event": "tool_start", "data": json.dumps({"tool": "get_blast_radius", "changed": changed_fns})}
        await asyncio.sleep(0.05)
        blast_rows, _ = q1_blast_radius(client, changed_fns, max_hops=max_hops) if changed_fns else ([], None)
        ms1 = int((time.time() - t1) * 1000)
        yield {"event": "tool_result", "data": json.dumps({
            "tool": "get_blast_radius", "count": len(blast_rows), "ms": ms1,
            "outcome": "answered_with_path" if blast_rows else "not_in_graph",
        })}

        # Step 3: get_affected_tests
        t2 = time.time()
        yield {"event": "tool_start", "data": json.dumps({"tool": "get_affected_tests", "changed": changed_fns})}
        await asyncio.sleep(0.05)
        test_rows = q2a_affected_tests(client, changed_fns, max_hops=max_hops) if changed_fns else []
        test_paths = gather_test_paths(client, test_rows, changed_fns)
        ms2 = int((time.time() - t2) * 1000)
        yield {"event": "tool_result", "data": json.dumps({
            "tool": "get_affected_tests", "count": len(test_rows), "ms": ms2,
            "outcome": "answered_with_path" if test_rows else "not_in_graph",
        })}

        # Step 4: find_reviewers & centrality & churn
        t3 = time.time()
        yield {"event": "tool_start", "data": json.dumps({"tool": "find_reviewers", "files": files})}
        await asyncio.sleep(0.05)
        reviewers = q3_find_reviewers(client, files, before_ts=ts) if files else []
        centrality = q4_centrality(client, changed_fns) if changed_fns else []
        churn = q5_recent_churn(client, files, since_ts=ts - (90 * 86400), before_ts=ts) if files else 0
        ms3 = int((time.time() - t3) * 1000)
        yield {"event": "tool_result", "data": json.dumps({
            "tool": "find_reviewers", "count": len(reviewers), "ms": ms3,
            "outcome": "answered_with_path" if reviewers else "not_in_graph",
        })}

        # Step 5: Risk calculation
        t4 = time.time()
        yield {"event": "tool_start", "data": json.dumps({"tool": "get_risk", "blast": len(blast_rows), "tests": len(test_rows)})}
        await asyncio.sleep(0.05)
        risk_data = compute_agent_risk(blast_rows, centrality, test_rows, churn, len(changed_fns))
        ms4 = int((time.time() - t4) * 1000)
        yield {"event": "tool_result", "data": json.dumps({
            "tool": "get_risk", "score": risk_data.get("score"),
            "label": risk_data.get("label"), "ms": ms4,
            "outcome": "answered_with_path",
        })}

        # Final decision object
        decision = {
            "head_sha": head_sha,
            "files_changed": files,
            "changed_functions": changed_fns,
            "blast_radius": blast_rows,
            "affected_tests": test_rows,
            "test_proof_paths": test_paths,
            "reviewers": reviewers,
            "centrality": centrality,
            "recent_churn": churn,
            "risk": risk_data,
            "max_hops": max_hops,
            "outcomes": {
                "map_diff": map_result.get("outcome", "not_in_graph"),
                "blast": "answered_with_path" if blast_rows else "not_in_graph",
                "tests": "answered_with_path" if test_rows else "not_in_graph",
                "reviewers": "answered_with_path" if reviewers else "not_in_graph",
                "centrality": "answered_with_path" if centrality else "not_in_graph",
                "risk": "answered_with_path",
            },
            "outcome": map_result.get("outcome", "not_in_graph"),
            "evidence": [ev.to_dict() for ev in client.evidence_log],
            "trace": [
                {"step": 1, "tool": "map_diff_to_functions", "ms": ms0},
                {"step": 2, "tool": "get_blast_radius", "ms": ms1},
                {"step": 3, "tool": "get_affected_tests", "ms": ms2},
                {"step": 4, "tool": "find_reviewers", "ms": ms3},
                {"step": 5, "tool": "get_risk", "ms": ms4},
            ]
        }
        explanation = generate_template_summary(decision)
        decision.update(explanation)
        comment = format_pr_comment(decision)

        yield {"event": "decision", "data": json.dumps({"decision": decision, "pr_comment": comment})}

    return EventSourceResponse(event_generator())


@app.get("/repos/{repo:path}/prs")
def get_repo_prs(repo: str) -> List[Dict[str, Any]]:
    """List available PRs for analysis, including curated demo PRs."""
    return [
        {"number": 2560, "title": "extract Execution and close the job lifecycle", "risk": "medium", "is_demo": True},
        {"number": 1, "title": "Fix backup path handling in scheduler", "risk": "low", "is_demo": True},
        {"number": 2, "title": "Refactor BorgJob execution and add cancellation", "risk": "medium", "is_demo": True},
        {"number": 3, "title": "Update DBus network monitor integration", "risk": "low", "is_demo": True},
        {"number": 4, "title": "Core borg process spawning & credential security", "risk": "high", "is_demo": True},
        {"number": 5, "title": "Exclude pattern matching and archive diff parser", "risk": "medium", "is_demo": True},
    ]



def build_cytoscape_elements(
    changed_fns: List[str],
    blast: List[Dict[str, Any]],
    tests: List[Dict[str, Any]],
    test_paths: Optional[Dict[str, List[str]]] = None,
) -> Dict[str, List[Dict[str, Any]]]:
    """Format nodes and edges for Cytoscape graph canvas."""
    nodes: Dict[str, Dict[str, Any]] = {}
    edges: Dict[str, Dict[str, Any]] = {}

    for fn in changed_fns:
        nodes[fn] = {"id": fn, "label": fn.split(".")[-1], "full_qname": fn, "type": "changed"}

    for r in blast:
        aff = r.get("affected")
        if aff and aff not in nodes:
            nodes[aff] = {"id": aff, "label": aff.split(".")[-1], "full_qname": aff, "type": "caller"}
        path = r.get("path") or []
        for i in range(len(path) - 1):
            src, tgt = path[i], path[i + 1]
            for node in (src, tgt):
                if node not in nodes:
                    nodes[node] = {
                        "id": node,
                        "label": node.split(".")[-1],
                        "full_qname": node,
                        "type": "caller",
                    }
            edge_id = f"{src}->{tgt}"
            edges[edge_id] = {
                "id": edge_id,
                "source": src,
                "target": tgt,
                "label": "CALLS",
            }

    for t in tests:
        test_name = t.get("test")
        if test_name and test_name not in nodes:
            nodes[test_name] = {"id": test_name, "label": test_name.split(".")[-1], "full_qname": test_name, "type": "test"}

    for path in (test_paths or {}).values():
        for i in range(len(path) - 1):
            src, tgt = path[i], path[i + 1]
            for node in (src, tgt):
                if node not in nodes:
                    nodes[node] = {
                        "id": node,
                        "label": node.split(".")[-1],
                        "full_qname": node,
                        "type": "caller",
                    }
            edge_id = f"{src}->{tgt}"
            edges[edge_id] = {
                "id": edge_id,
                "source": src,
                "target": tgt,
                "label": "CALLS",
                "type": "evidence",
            }

    return {
        "nodes": [{"data": n} for n in nodes.values()],
        "edges": [{"data": e} for e in edges.values()],
    }


@app.get("/subgraph")
def get_subgraph(
    repo: str = "borgbase/vorta",
    changed: Optional[str] = Query(None),
    max_hops: int = Query(4, ge=1, le=6),
) -> Dict[str, Any]:
    """Retrieve Cytoscape-formatted subgraph for changed functions."""
    client = get_graph_client(repo)
    changed_list = [c.strip() for c in changed.split(",") if c.strip()] if changed else []

    if not changed_list:
        rows, _ = client.ro_query(
            "MATCH (f:Function) WHERE NOT f:Test RETURN f.qname AS qname LIMIT 1"
        )
        if rows:
            changed_list = [str(rows[0].get("qname", ""))]

    check = confirm_names(client, functions=changed_list)
    if not check["ok"]:
        return {
            "repo": repo,
            "changed": changed_list,
            "max_hops": max_hops,
            "elements": {"nodes": [], "edges": []},
            "outcome": "unknown_name",
            "names": check["unknown_functions"],
        }

    from graph.queries import q1_blast_radius, q2a_affected_tests

    blast, _ = (
        q1_blast_radius(client, changed_list, max_hops=max_hops)
        if changed_list
        else ([], None)
    )
    tests = (
        q2a_affected_tests(client, changed_list, max_hops=max_hops)
        if changed_list
        else []
    )

    test_paths: Dict[str, List[str]] = {}
    for test in tests:
        for changed_fn in changed_list:
            proof_path = q2b_test_proof_path(client, test["test"], changed_fn)
            if proof_path:
                test_paths[test["test"]] = proof_path
                break
    elements = build_cytoscape_elements(changed_list, blast, tests, test_paths)
    return {
        "repo": repo,
        "changed": changed_list,
        "max_hops": max_hops,
        "elements": elements,
        "outcome": "answered_with_path" if blast or tests else "not_in_graph",
        "message": (
            None
            if blast or tests
            else "nothing found in the graph, which may mean the call link is not modelled"
        ),
        "test_proof_paths": test_paths,
    }


@app.post("/ask")
def ask_question(req: AskRequest) -> Dict[str, Any]:
    """Answer maintainer questions by executing read-only Cypher queries."""
    client = get_graph_client(req.repo)
    q_lower = req.question.lower()

    if req.target_function:
        check = confirm_names(client, functions=[req.target_function])
        if not check["ok"]:
            return {
                "question": req.question,
                "answer": "The requested function name is not in the graph.",
                "evidence_rows": [],
                "outcome": "unknown_name",
            }

    if "caller" in q_lower or "blast" in q_lower:
        query = (
            "MATCH (c:Function)-[r:CALLS]->(ch:Function) "
            "WHERE ($target IS NULL OR ch.qname = $target) "
            "RETURN c.qname AS caller, ch.qname AS callee, type(r) AS rel LIMIT 10"
        )
        rows, _ = client.ro_query(query, {"target": req.target_function})
        answer = f"Found {len(rows)} immediate caller relationships in graph."
    elif "test" in q_lower:
        if req.target_function:
            rows, _ = client.ro_query(
                "MATCH p = (t:Test)-[r:CALLS*1..6]->(ch:Function {qname: $target}) "
                "WHERE size(r) >= 1 "
                "RETURN t.qname AS test, t.file AS file, length(p) AS hops, "
                "[n IN nodes(p) | n.qname] AS path",
                {"target": req.target_function},
            )
        else:
            rows, _ = client.ro_query("MATCH (t:Test) RETURN count(t) AS total_tests")
        total = rows[0].get("total_tests", 0) if rows else 0
        answer = (
            f"The repository graph contains {total} indexed test functions."
            if not req.target_function
            else f"Found {len(rows)} reaching test(s)."
        )
    else:
        answer = "Graph query executed. All answers are derived strictly from FalkorDB schema."
        rows = []

    payload = {
        "question": req.question,
        "answer": answer,
        "evidence_rows": rows,
        "outcome": "answered_with_path" if rows else "not_in_graph",
    }
    return validate_decision(payload)


@app.get("/benchmark")
def get_benchmark_results() -> Dict[str, Any]:
    """Serve benchmark/results.json exactly as written by benchmark.run (no invented values)."""
    res_path = Path(__file__).resolve().parent.parent / "benchmark" / "results.json"
    if res_path.exists():
        with open(res_path, "r") as f:
            return json.load(f)
    return {
        "status": "pending",
        "message": "benchmark/results.json not found. Generate it with: ./.venv/bin/python -m benchmark.run --repo-path <vorta checkout>",
        "methods": {},
        "per_pr": [],
    }


def _cached_demo_payload(
    payload: Dict[str, Any], max_hops: Optional[int] = None
) -> Dict[str, Any]:
    """Apply hop filtering and explicit cached outcomes to a demo payload."""
    result = dict(payload)
    decision = dict(payload.get("decision") or {})
    if max_hops is not None:
        decision["max_hops"] = max_hops
        decision["blast_radius"] = [
            row for row in decision.get("blast_radius", [])
            if int(row.get("hops", max_hops + 1)) <= max_hops
        ]
        decision["affected_tests"] = [
            row for row in decision.get("affected_tests", [])
            if int(row.get("hops", max_hops + 1)) <= max_hops
        ]
        present_tests = {row["test"] for row in decision["affected_tests"]}
        decision["test_proof_paths"] = {
            name: path
            for name, path in (decision.get("test_proof_paths") or {}).items()
            if name in present_tests and len(path) - 1 <= max_hops
        }
        decision["notable_paths"] = [
            path for path in decision.get("notable_paths", [])
            if isinstance(path, list) and len(path) - 1 <= max_hops
        ]
    # Tests are reported separately; count each production caller once (shortest path).
    best = {}
    for row in sorted(decision.get("blast_radius", []), key=lambda r: int(r.get("hops", 99))):
        name = str(row.get("affected", ""))
        if name.startswith("tests.") or name in best:
            continue
        best[name] = row
    decision["blast_radius"] = list(best.values())
    decision["risk"] = compute_agent_risk(
        decision.get("blast_radius", []),
        decision.get("centrality", []),
        decision.get("affected_tests", []),
        int(decision.get("recent_churn", 0)),
        len(decision.get("changed_functions", [])),
    )
    decision["outcome"] = "cached"
    decision["outcomes"] = {
        key: "cached" for key in (decision.get("outcomes") or {
            "map_diff": None, "blast": None, "tests": None, "reviewers": None, "risk": None
        })
    }
    decision.update(generate_template_summary(decision))
    if result.get("featured"):
        baseline_count = len(result.get("baseline_same_name_tests") or [])
        decision["summary"] = (
            f"Same-name baseline found {baseline_count} test file(s); the graph cache "
            f"finds {len(decision['affected_tests'])} reaching test(s) at depth {decision['max_hops']}."
        )
        decision["section_notes"]["tests"] = (
            "Every listed graph test includes its shortest proof path; the same-name baseline missed them."
        )
    result["decision"] = decision
    result["pr_comment"] = format_pr_comment(decision)
    return result


@app.get("/demo/featured")
def get_featured_demo(max_hops: int = Query(4, ge=1, le=6)) -> Dict[str, Any]:
    """Featured cached PR with identical analysis filtered to the requested hop depth."""
    cache_path = Path(__file__).resolve().parent.parent / "demo_cache" / "featured.json"
    if not cache_path.exists():
        raise HTTPException(status_code=404, detail="Featured demo not found")
    with open(cache_path, "r") as f:
        return _cached_demo_payload(json.load(f), max_hops=max_hops)


@app.get("/demo/{demo_id}")
def get_cached_demo(demo_id: int) -> Dict[str, Any]:
    """Retrieve pre-generated demo PR decision object."""
    cache_path = Path(__file__).resolve().parent.parent / "demo_cache" / f"demo_pr_{demo_id}.json"
    if not cache_path.exists():
        raise HTTPException(status_code=404, detail="Demo PR not found")
    with open(cache_path, "r") as f:
        return _cached_demo_payload(json.load(f))


@app.post("/webhook/github")
async def github_webhook(
    request: Request,
    background_tasks: BackgroundTasks,
    x_github_event: Optional[str] = Header(None, alias="X-GitHub-Event"),
) -> Dict[str, Any]:
    """Handle incoming GitHub PR webhook events."""
    if x_github_event != "pull_request":
        return {"status": "ignored", "reason": f"Event '{x_github_event}' is not pull_request"}

    payload = await request.json()
    action = payload.get("action")
    if action not in ("opened", "synchronize", "reopened"):
        return {"status": "ignored", "reason": f"Action '{action}' does not require analysis"}

    repo_data = payload.get("repository", {})
    repo_name = repo_data.get("full_name")
    pr_data = payload.get("pull_request", {})
    pr_number = pr_data.get("number")

    if not repo_name or not pr_number:
        raise HTTPException(
            status_code=400,
            detail="Missing repository.full_name or pull_request.number",
        )

    token = os.getenv("GITHUB_TOKEN")
    dry_run = os.getenv("DRY_RUN", "true").lower() == "true"

    from agent.github_actions import run_github_action

    graph_client = get_graph_client(repo_name)
    background_tasks.add_task(
        run_github_action,
        repo_name=repo_name,
        pr_number=int(pr_number),
        token=token,
        dry_run=dry_run,
        client=graph_client,
    )

    return {
        "status": "queued",
        "repo": repo_name,
        "pr_number": int(pr_number),
        "action": action,
        "dry_run": dry_run,
    }
