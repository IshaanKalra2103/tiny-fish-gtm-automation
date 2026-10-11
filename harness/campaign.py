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
import sys
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE = json.loads((HERE / "state" / "paperclip.json").read_text())
TOKEN = json.loads((HERE / "state" / "board.json").read_text())["token"]
API = STATE["apiUrl"]
CID = STATE["companyId"]
A = STATE["agents"]


def call(method: str, path: str, body=None):
    headers = {"Authorization": f"Bearer {TOKEN}", "Accept": "application/json"}
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


def brief_md(a) -> str:
    # app/ agents parse the `brand_url:` / `niche:` lines.
    return f"""brand_url: {a.brand}
niche: {a.niche}
platforms: {a.platforms}

## Product context
- **Brand / website:** {a.brand}
- **Niche / theme:** {a.niche}
- **Audience:** {a.audience}
- **Goal:** {a.goal}
- **Brand voice:** {a.voice}
- **Competitors:** {a.competitors or "(discover them)"}

## Campaign settings
- **Platforms:** {a.platforms}
- **Budget / cadence:** {a.cadence}
- **Approval:** human approval required before anything is published

{a.brief or ""}

Shared memory for this campaign: `/workspace/runs/<this issue's identifier>/`
"""


STAGES = [
    ("research", "Trend discovery",
     "Find what's trending in the niche across the campaign platforms (TinyFish Search/Fetch/Agent/Browser, "
     "Bright Data social samples). Write `evidence.json` and `social_<platform>.json` with source links."),
    ("analysis", "Trend analysis & insights",
     "Cluster topics, hooks, formats and engagement patterns from the evidence. Write `analysis.json` "
     "and charts that show what works and why, plus opportunity areas."),
    ("strategy", "Content template & strategy",
     "Extract a reusable template (hook pattern, beats, length, caption style, CTA), each element citing "
     "evidence, and pick concept, audience and message. Write `template_vN.json` and `script_vN.json`. "
     "Read `/workspace/memory/learnings.json` first."),
    ("video", "Generate short-form video",
     "Render the video from the script (voiceover, visuals, burned-in captions, 9:16, 30s or less). Write "
     "`video_vN.mp4` plus captions/thumbnail."),
    ("qa", "QA: personas + compliance",
     "Score the draft with simulated personas (grounded in Bright Data comment evidence) and compliance "
     "checks (hook in 2s, CTA, every claim supported, legible captions, 30s or less). Revise up to 3 drafts. "
     "Write `qa_vN.json`. Persona scores are SIMULATED."),
    ("publish", "Approval & publish",
     "File a `request_board_approval` with the final video + post copy and wait (issue in_review). Only "
     "after the board approves (wakeReason=approval_approved): produce platform-specific copy, schedule "
     "and status in `publish.json`. Real posting requires explicit board authorization (guardrail)."),
    ("learn", "Learnings & next iteration",
     "Compare outcome and QA history with the initial trends. Update `/workspace/memory/learnings.json` "
     "(winning hooks, recurring QA failures) and write the next-iteration plan."),
]


def cmd_new(a) -> None:
    root = call("POST", f"/companies/{CID}/issues", {
        "title": f"Campaign: {a.niche} for {a.brand}",
        "description": brief_md(a),
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
            "assigneeAgentId": A[key], "priority": "high",
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
        linked = {i if isinstance(i, str) else i.get("id") for i in (ap.get("issueIds") or ap.get("issues") or [])}
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
    print(f"{action} -> approval {ap['id']}")


def cmd_approve(a) -> None:
    _decide(a, "approve", "Approved by board.")


def cmd_reject(a) -> None:
    _decide(a, "reject", "Rejected by board.")


def cmd_revise(a) -> None:
    _decide(a, "request-revision", "Please revise.")


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("new")
    n.add_argument("--brand", required=True)
    n.add_argument("--niche", required=True)
    n.add_argument("--platforms", default="tiktok,instagram,youtube,x")
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
    for name, fn, req in (("approve", cmd_approve, False), ("reject", cmd_reject, True), ("revise", cmd_revise, True)):
        sp = sub.add_parser(name); sp.add_argument("ref"); sp.add_argument("-m", "--message", required=req)
        sp.set_defaults(fn=fn)
    a = p.parse_args()
    a.fn(a)


if __name__ == "__main__":
    main()
