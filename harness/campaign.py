# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Launch and drive GTM campaigns in the Paperclip harness (run after bootstrap.py).

    uv run harness/campaign.py new --brand https://tinyfish.ai --niche "AI web agents" \\
        --platforms tiktok,instagram,youtube [--mode pipeline|ceo] [--brief "..."]
    uv run harness/campaign.py status <CAMPAIGN-ISSUE>               # e.g. TIN-1
    uv run harness/campaign.py approvals                             # pending human approvals
    uv run harness/campaign.py approve <APPROVAL-ID|ISSUE> [-m "ship it"]
    uv run harness/campaign.py reject  <APPROVAL-ID|ISSUE> -m "why"
    uv run harness/campaign.py revise  <APPROVAL-ID|ISSUE> -m "shorter hook"

Modes:
  pipeline (default)  deterministic issue tree, no LLM needed to orchestrate:
                      research -> analysis -> strategy -> video -> qa -> publish -> learn,
                      chained with blockedByIssueIds, so Paperclip wakes each agent only
                      once its upstream stage is done. QA runs its own revise loop (up to 3
                      drafts). Publish files a `request_board_approval` and waits; the human
                      approves (UI / this CLI / iMessage) and Paperclip re-wakes publish.
  ceo                 a single campaign issue assigned to the GTM Orchestrator, which plans
                      and delegates the same tree itself.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import subprocess
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent / "app" / "src"))
from gtm.contract import STAGES, brief_description

STATE = {}
TOKEN = API = CID = ""
A = {}


# Inside a Paperclip agent run (e.g. the Orchestrator answering an iMessage) the run's own token is used,
# so the CEO launches campaigns with one command instead of rediscovering the API.
AGENT_RUN = bool(os.environ.get("PAPERCLIP_RUN_ID") and os.environ.get("PAPERCLIP_API_KEY"))


def configure():
    global STATE, TOKEN, API, CID, A
    try:
        STATE = json.loads((HERE / "state" / "paperclip.json").read_text())
        if AGENT_RUN:
            TOKEN = os.environ["PAPERCLIP_API_KEY"]
        else:
            TOKEN = json.loads((HERE / "state" / "board.json").read_text())["token"]
    except FileNotFoundError:
        raise RuntimeError("Harness not bootstrapped. Run ./harness/up.sh, then uv run harness/bootstrap.py")
    API, CID, A = STATE["apiUrl"], STATE["companyId"], STATE["agents"]
    if AGENT_RUN and os.environ.get("PAPERCLIP_API_URL"):
        API = os.environ["PAPERCLIP_API_URL"].rstrip("/").removesuffix("/api") + "/api"


def call(method: str, path: str, body=None):
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
    if AGENT_RUN:
        headers["X-Paperclip-Run-Id"] = os.environ["PAPERCLIP_RUN_ID"]
    data = None
    if body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=60) as r:
            raw = r.read()
    except urllib.error.HTTPError as e:
        sys.exit(f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')[:800]}")
    return json.loads(raw) if raw else None


def chat_issue() -> str | None:
    """The chat-origin issue this agent run is answering (iMessage thread), so stages can post cards back to it."""
    if not AGENT_RUN:
        return None
    try:
        snap = call("GET", f"/heartbeat-runs/{os.environ['PAPERCLIP_RUN_ID']}").get("contextSnapshot") or {}
        issue = call("GET", f"/issues/{snap['issueId']}") if snap.get("issueId") else {}
        return issue.get("id") if issue.get("originKind") == "chat_channel" else None
    except (SystemExit, KeyError, AttributeError):
        return None


def brief_md(a) -> str:
    return brief_description({
        "brand_url": a.brand, "niche": a.niche, "platforms": a.platforms,
        "audience": a.audience, "goal": a.goal, "voice": a.voice,
        "competitors": a.competitors, "cadence": a.cadence, "notes": a.brief,
        **({"chat_issue": ci} if (ci := chat_issue()) else {}),
    })


def cmd_new(a) -> None:
    description = brief_md(a)
    # Check the real container, not the host shell, before scheduling paid work.
    # The host doctor needs docker; inside an agent run the workers' credentials aren't visible anyway.
    if a.mode == "pipeline" and not AGENT_RUN:
        cmd_doctor(a)
    missing = [key for key, _, _ in STAGES if not A.get(key)]
    if missing:
        raise RuntimeError(f"Missing agents: {missing}; rerun bootstrap.py")
    root = call("POST", f"/companies/{CID}/issues", {
        "title": f"Campaign: {a.niche} for {a.brand}",
        "description": description,
        "projectId": STATE["projectId"], "goalId": STATE["goalId"], "priority": "high",
        **({"assigneeAgentId": A["orchestrator"]} if a.mode == "ceo" else {}),
    })
    ident = root.get("identifier") or root["id"]
    print(f"campaign {ident}  ({STATE['publicUrl']}/issues/{ident})")
    if a.mode == "ceo":
        print("assigned to GTM Orchestrator; it will plan and delegate the stages.")
        return

    prev = None
    for key, title, desc in STAGES:
        body = {
            "title": f"[{ident}] {title}",
            "description": f"{desc}\n\nCampaign brief: see parent issue {ident}. "
                           f"Write outputs to `/workspace/runs/{ident}/`.",
            "parentId": root["id"], "projectId": STATE["projectId"], "goalId": STATE["goalId"],
            "assigneeAgentId": A[key], "priority": "high", "status": "todo",  # backlog issues are never woken
            "blockedByIssueIds": [prev["id"]] if prev else [],
        }
        prev = call("POST", f"/companies/{CID}/issues", body)
        print(f"  {prev.get('identifier')}  {key:9s} -> {title}")
    print("pipeline queued: research starts now; each stage wakes when the previous one is done.")


def find_issue(ref: str) -> dict:
    return call("GET", f"/issues/{ref}")


def cmd_status(a) -> None:
    root = find_issue(a.issue)
    kids = call("GET", f"/companies/{CID}/issues?parentId={root['id']}") or []
    if isinstance(kids, dict):
        kids = kids.get("items") or kids.get("issues") or []
    print(f"{root.get('identifier')}  {root['status']:12s} {root['title']}")
    for k in sorted(kids, key=lambda i: i.get("createdAt", "")):
        ex = (k.get("executionState") or {})
        stage = f"  [{ex.get('currentStageType')} {ex.get('status')}]" if ex.get("currentStageType") else ""
        print(f"  {k.get('identifier')}  {k['status']:12s} {k['title']}{stage}")
    ident = root.get("identifier") or root["id"]
    path = HERE.parent / "runs" / ident / "workflow.json"
    if path.is_file():
        state = json.loads(path.read_text())
        print(f"worker: {state['status']} at {state['current_stage']}")
        for role, entry in state["stages"].items():
            print(f"  {role:10s} {entry['status']:18s} {entry.get('summary', '')}")
    print(f"artifacts: {HERE.parent / 'runs' / ident}")


def cmd_doctor(a) -> None:
    checks = []
    health = call("GET", "/health")
    checks.append({"name": "paperclip", "ok": bool(health)})
    agents = call("GET", f"/companies/{CID}/agents")
    by_id = {agent["id"]: agent for agent in agents}
    for role, _, _ in STAGES:
        agent = by_id.get(A.get(role), {})
        cfg = agent.get("adapterConfig") or {}
        checks.append({"name": role, "ok": agent.get("adapterType") == "process"
                       and cfg.get("args") == ["run", "gtm", "agent", role]
                       and cfg.get("cwd") == "/workspace/app"
                       and agent.get("status") not in ("paused", "terminated"),
                       "fix": "Run uv run harness/bootstrap.py to reconcile workers"})
    try:
        result = subprocess.run(["docker", "exec", "--user", "node", "-w", "/workspace/app", "gtm-paperclip",
                                 "uv", "run", "--no-sync", "gtm", "doctor"], capture_output=True, text=True, timeout=30)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise RuntimeError("Cannot inspect worker runtime; ensure Docker is running and run ./harness/up.sh") from exc
    try:
        worker = json.loads(result.stdout.strip().splitlines()[-1])
    except (ValueError, IndexError):
        worker = {"ok": False, "exit_code": result.returncode,
                  "error": "Worker runtime is unavailable",
                  "fix": "Run docker exec --user node -w /workspace/app gtm-paperclip uv sync --frozen, then retry doctor"}
    checks.append({"name": "worker_runtime", **worker})
    ok = all(c["ok"] for c in checks)
    print(json.dumps({"ok": ok, "checks": checks}, indent=2))
    if not ok:
        raise SystemExit(1)


def pending_approvals() -> list[dict]:
    res = call("GET", f"/companies/{CID}/approvals?status=pending") or []
    return res.get("items", res) if isinstance(res, dict) else res


def resolve_approval(ref: str) -> dict:
    """Accept an approval id, or an issue identifier/id linked to a pending approval."""
    pend = pending_approvals()
    for ap in pend:
        if ap["id"] == ref:
            return ap
    issue = find_issue(ref)
    for ap in pend:
        linked = {i["id"] for i in call("GET", f"/approvals/{ap['id']}/issues") or []}
        if issue["id"] in linked:
            return ap
    sys.exit(f"no pending approval for {ref}; pending: {[p['id'] for p in pend]}")


def cmd_approvals(a) -> None:
    for ap in pending_approvals():
        pl = ap.get("payload") or {}
        print(f"{ap['id']}  {ap.get('type')}  {pl.get('title', '')}  issues={ap.get('issueIds')}")


def _decide(a, action: str, default_note: str) -> None:
    ap = resolve_approval(a.ref)
    call("POST", f"/approvals/{ap['id']}/{action}", {"decisionNote": a.message or default_note})
    if action in ("reject", "request-revision"):
        # Paperclip's revision endpoint records the decision but does not wake the worker.
        for issue in call("GET", f"/approvals/{ap['id']}/issues") or []:
            call("PATCH", f"/issues/{issue['id']}", {"status": "blocked",
                 "comment": f"Board {action}: {a.message or default_note}. Revise the package before requesting a new approval."})
    print(f"{action} -> approval {ap['id']}")


def cmd_approve(a) -> None:
    _decide(a, "approve", "Approved by board.")


def cmd_reject(a) -> None:
    _decide(a, "reject", "Rejected by board.")


def cmd_revise(a) -> None:
    _decide(a, "request-revision", "Please revise.")


def cmd_retry(a) -> None:
    issue = find_issue(a.issue)
    if issue["status"] != "blocked":
        raise ValueError("Only blocked stage issues can be retried; use approvals for a pending human gate")
    if not issue.get("parentId"):
        raise ValueError("Retry the blocked stage issue, not the campaign parent")
    call("PATCH", f"/issues/{issue['id']}", {"status": "todo", "comment": a.message or "Retry after resolving the blocker"})
    print(f"queued retry for {issue.get('identifier', issue['id'])}")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--brand", required=True)
    n.add_argument("--niche", required=True)
    n.add_argument("--platforms", default="tiktok,instagram,youtube")
    n.add_argument("--audience", default="developers building with AI agents (B2B)")
    n.add_argument("--goal", default="awareness and signups")
    n.add_argument("--voice", default="technical, concrete, a little playful; no hype")
    n.add_argument("--competitors", default="")
    n.add_argument("--cadence", default="1 short-form video per run, budget-capped")
    n.add_argument("--brief", default="")
    n.add_argument("--mode", choices=["pipeline", "ceo"], default="pipeline")
    n.set_defaults(fn=cmd_new)
    s = sub.add_parser("status"); s.add_argument("issue"); s.set_defaults(fn=cmd_status)
    sub.add_parser("approvals").set_defaults(fn=cmd_approvals)
    sub.add_parser("doctor").set_defaults(fn=cmd_doctor)
    retry = sub.add_parser("retry")
    retry.add_argument("issue")
    retry.add_argument("-m", "--message")
    retry.set_defaults(fn=cmd_retry)
    for name, fn, req in (("approve", cmd_approve, False), ("reject", cmd_reject, True), ("revise", cmd_revise, True)):
        sp = sub.add_parser(name); sp.add_argument("ref"); sp.add_argument("-m", "--message", required=req)
        sp.set_defaults(fn=fn)
    a = p.parse_args()
    try:
        configure()
        a.fn(a)
    except (RuntimeError, ValueError, urllib.error.URLError) as exc:
        print(json.dumps({"ok": False, "error": str(exc)}), file=sys.stderr)
        raise SystemExit(1)


if __name__ == "__main__":
    main()
