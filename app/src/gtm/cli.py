"""gtm: run the growth loop locally, or as one Paperclip process agent per role.

    gtm run [--run ID] [--brand-url URL] [--niche TEXT]   full loop locally, stops at the approval gate
    gtm agent <role> [--run ID]                           one role (Paperclip mode when PAPERCLIP_* env is set)
    gtm approve <run>                                     human approval -> ready to publish (simulated)
    gtm report <run> / gtm serve [--port 8501]            static dashboard at runs/<id>/index.html
"""

import argparse
import http.server
import json
import os
import sys
import traceback
from datetime import datetime
from functools import partial

from . import config, report
from .roles import analysis, learn, publish, qa, research, strategy, video
from .run import Run
from .contract import ORDER, parse_brief
from . import workflow

ROLES = {"research": research, "analysis": analysis, "strategy": strategy, "video": video, "qa": qa,
         "publish": publish, "learn": learn}


def main() -> int:
    """stdout is exactly one JSON line ({"ok": ...}); progress goes to stderr."""
    try:
        return _main()
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 1


def _out(**data) -> int:
    print(json.dumps({"ok": True, **data}, default=str))
    return 0


def _main() -> int:
    ap = argparse.ArgumentParser(prog="gtm")
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("doctor")
    r = sub.add_parser("run")
    r.add_argument("--run")
    r.add_argument("--brand")
    r.add_argument("--brand-url")
    r.add_argument("--niche")
    r.add_argument("--from", dest="start", choices=ORDER, default="research", help="resume from this role")
    a = sub.add_parser("agent")
    a.add_argument("role", choices=ORDER)
    a.add_argument("--run")
    for name in ("approve", "report"):
        sub.add_parser(name).add_argument("run")
    s = sub.add_parser("serve")
    s.add_argument("--port", type=int, default=8501)
    args = ap.parse_args()

    if args.cmd == "doctor":
        from .doctor import inspect
        result = inspect()
        print(json.dumps(result))
        return 0 if result["ok"] else 1

    if args.cmd == "run":
        return _run_local(args)
    if args.cmd == "agent":
        return _paperclip_agent(args.role) if os.environ.get("PAPERCLIP_API_URL") and not args.run else _one(args.role, args.run)
    if args.cmd == "approve":
        run = Run(args.run)
        with run.exclusive():
            msg = publish.run(run, approved=True)
            workflow.record(run, "publish", "done", msg)
        _step(run, "learn")
        return _out(run=run.id, summary=msg, dashboard=report.build(run))
    if args.cmd == "report":
        return _out(dashboard=report.build(Run(args.run)))
    if args.cmd == "serve":
        report.index()
        handler = partial(http.server.SimpleHTTPRequestHandler, directory=str(config.RUNS_DIR))
        print(f"dashboard: http://localhost:{args.port}/  (runs in {config.RUNS_DIR})", file=sys.stderr)
        http.server.ThreadingHTTPServer(("0.0.0.0", args.port), handler).serve_forever()
    return 0


def _run_local(args) -> int:
    run = Run(args.run or "local-" + datetime.now().strftime("%Y%m%d-%H%M%S-%f"))
    if not run.exists("brief.json"):
        brief = dict(config.DEFAULT_BRIEF)
        brief.update({k: v for k, v in {"brand": args.brand, "brand_url": args.brand_url, "niche": args.niche}.items() if v})
        run.write("brief.json", brief)
    print(f"run {run.id} -> {run.dir}", file=sys.stderr)
    for role in ORDER[ORDER.index(args.start):]:
        _step(run, role)
        if run.read("workflow.json", {}).get("status") == "awaiting_approval":
            break
    return _out(run=run.id, dashboard=str(run.dir / "index.html"), status=run.read("publish.json", {}).get("status"),
                tinyfish_usd=run.read("costs.json", {}).get("tinyfish_usd"))


def _one(role: str, run_id: str | None) -> int:
    run = Run(run_id or "local")
    if not run.exists("brief.json"):
        run.write("brief.json", config.DEFAULT_BRIEF)
    return _out(run=run.id, role=role, summary=_step(run, role), dir=str(run.dir))


def _step(run: Run, role: str) -> str:
    try:
        msg = workflow.execute(run, role, ROLES[role].run)
    finally:
        try:
            report.build(run)
        except Exception as exc:
            run.log("report", f"Report failed: {exc}", level="warn")
    return msg


def _paperclip_agent(role: str) -> int:
    """Paperclip process-adapter contract: checkout the issue, do the work, comment + set status."""
    from .paperclip_agent import PaperclipRun

    pc = PaperclipRun.from_env()
    issue = pc.current_issue()
    if issue is None:
        print(json.dumps({"ok": True, "idle": True}))
        return 0
    run = Run(pc.campaign_id(issue))
    try:
        pc.checkout(issue["id"])
        if not run.exists("brief.json"):
            run.write("brief.json", _brief_from(pc.campaign_issue(issue)))
        msg = _step(run, role)
        if role == "publish" and run.read("publish.json", {}).get("status") == "awaiting_approval":
            with run.exclusive():
                pkg = run.read("publish.json")
                if not pkg.get("approval_id"):
                    # Recover an approval created before a worker crash instead of duplicating it.
                    approvals = pc.request("GET", f"/issues/{issue['id']}/approvals") or []
                    approval = next((a for a in approvals if (a.get("payload") or {}).get("artifactHash") == pkg["artifact_hash"]), None)
                    if approval is None:
                        approval = pc.request_approval(issue["id"], f"Approve {run.id} v{pkg['version']}", msg,
                            f"Review runs/{run.id}/index.html", artifact_hash=pkg["artifact_hash"])
                    pkg["approval_id"] = approval["id"]
                    run.write("publish.json", pkg)
                approval = pc.request("GET", f"/approvals/{pkg['approval_id']}")
                if approval.get("status") == "approved":
                    if (approval.get("payload") or {}).get("artifactHash") != pkg["artifact_hash"]:
                        raise ValueError("Approval does not match this artifact")
                    msg = publish.run(run, approved=True, approval={k: approval.get(k) for k in ("id", "status", "decidedByUserId", "decidedAt")})
                    workflow.record(run, role, "done", msg, approval_id=approval["id"])
                    pc.done(issue["id"], msg)
                elif approval.get("status") in ("rejected", "revision_requested"):
                    raise workflow.StageBlocked(f"Board {approval['status']}: {approval.get('decisionNote') or 'review the approval'}")
                else:
                    pc.set_status(issue["id"], "in_review", msg + f"; waiting for approval {approval['id']}")
            report.build(run)
        else:
            pc.done(issue["id"], msg)
            if role == "learn":
                pc.done(pc.campaign_issue(issue)["id"], f"Campaign {run.id} complete; approved package and learnings in runs/{run.id}/ (posting simulated)")
    except Exception as e:
        run.log(role, f"failed: {e}", level="error")
        try:
            with run.exclusive():
                workflow.record(run, role, "blocked", str(e))
        except RuntimeError:
            pass  # Do not overwrite state owned by another active worker.
        pc.blocked(issue["id"], f"{role} failed: {e}\n{traceback.format_exc()[-1500:]}")
        print(json.dumps({"ok": False, "run": run.id, "role": role, "error": str(e)}))
        return 1
    return _out(run=run.id, role=role, summary=msg, dir=str(run.dir))


def _brief_from(campaign: dict) -> dict:
    return parse_brief(campaign.get("description") or "")


if __name__ == "__main__":
    sys.exit(main())
