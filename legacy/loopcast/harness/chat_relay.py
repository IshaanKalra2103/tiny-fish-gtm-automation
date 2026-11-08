# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Relay: the founder's iMessage thread is the campaign dashboard, in native iMessage UI.

When a stage finishes (its card appears in runs/<campaign>/cards/), this relay sends that stage's update into
the thread the campaign came from through Photon (photon/send_rich.mjs), as native UI rather than images:
research -> text + rich link preview of the top trending post; analysis -> a native poll of the 3 ideas;
video -> the clip inline; QA -> one line of scores; publish -> caption + an Approve / Request changes poll.
An APPROVE reply (or approve vote) is recorded as the Paperclip board approval, confirmed with confetti.

    python3 harness/chat_relay.py            # loop (every 5 s); Ctrl-C to stop
    python3 harness/chat_relay.py --once     # one pass
"""

import argparse
import json
import re
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path

HERE = Path(__file__).resolve().parent
STATE, RUNS = HERE / "state", HERE.parent / "runs"
SENT = STATE / "chat_relay_sent.json"
ROOT = HERE.parent
def short(t: str, n: int) -> str:
    t = " ".join(str(t).split())
    return t if len(t) <= n else t[: n - 1].rstrip() + "…"


def rich(run: Path, stem: str, v: int | None) -> dict:
    """send_rich.mjs arguments for one stage update."""
    read = lambda name: json.loads((run / name).read_text())
    cards = run / "cards"
    fn = {"1_research": "chart_research(r)", "2_analysis": "chart_analysis(r)", "4_qa": f"chart_qa(r, {v})"}.get(stem)
    if fn:  # chart image for the app card, rendered with the app's env (Pillow); no chart -> card without image
        subprocess.run(["uv", "run", "--frozen", "--project", str(ROOT / "app"), "python", "-c",
                        f"from gtm.run import Run; from gtm import cards; r = Run({run.name!r}); cards.{fn}"],
                       capture_output=True, timeout=120)
    if stem == "1_research":
        ev, charts = read("evidence.json"), read("charts.json") if (run / "charts.json").exists() else {}
        top = (charts.get("social_top") or [{}])[0].get("url") or next(
            (x["url"] for x in ev["social_search"].get("instagram", []) + ev["youtube"]["videos"] if x.get("url")), None)
        posts = sum(len(x) for x in ev.get("social_search", {}).values())
        card = {"caption": "Trend research", "subcaption": f"{len(ev['threads'])} threads · {posts} posts · "
                f"{len(ev['youtube']['videos'])} Shorts", "trailingCaption": "TinyFish", "imageTitle": "Top posts by likes",
                "image": str(cards / "chart_research.jpg"), "url": top or ev["brief"]["brand_url"],
                "summary": f"Research: {posts} trending posts"}
        return {"card": card, "text": "Top trending post right now:", "link": top}
    if stem == "2_analysis":
        ins = read("insights.json")
        card = {"caption": short(ins["template"]["name"], 40), "subcaption": "the pattern that's working",
                "trailingCaption": f"{len(ins['themes'])} themes", "imageTitle": "Theme strength",
                "image": str(cards / "chart_analysis.jpg"), "summary": f"Trend: {ins['template']['name']}"}
        return {"card": card, "text": "3 reel ideas from it. I'm making #1; vote to steer the next one.",
                "poll": "Which reel idea?", "options": [short(i["title"], 60) for i in ins.get("ideas", [])[:3]]}
    if stem == "3_video":
        info = read(f"video_v{v}.json")
        return {"text": f"Draft v{v} ({info['seconds']:.0f}s, vertical):", "files": [str(run / f"video_v{v}.mp4")]}
    if stem == "4_qa":
        q = read(f"qa_v{v}.json")
        problems = {"on-screen text": "captions hard to read", "the product is actually shown": "product not shown",
                    "claims are credible": "claims not backed on screen", "hook is readable": "weak hook",
                    "one clear call to action": "unclear call to action", "compliance": "compliance check"}
        def problem(b: str) -> str:
            b = b.replace("[MUST] ", "").lower()
            return next((v for k, v in problems.items() if b.startswith(k)), short(b.split(" (")[0], 40))
        fixes = ", ".join(problem(b) for b in q["blocking"][:3])
        return {"card": {"caption": f"Persona QA · draft v{v}", "subcaption": "passed" if q["passed"] else short(fixes, 44),
                         "trailingCaption": f"{q['avg_score']}/10", "imageTitle": f"{q['avg_score']} / 10",
                         "imageSubtitle": "3 synthetic personas", "image": str(cards / f"chart_qa_v{v}.jpg"),
                         "summary": f"Persona QA v{v}: {q['avg_score']}/10"}}
    if stem == "5_publish":
        pub = read("publish.json")
        if pub.get("status") != "awaiting_approval":
            return {}  # already decided (the approval itself is confirmed with confetti)
        cap = (pub.get("copy") or {}).get("reels_caption", "") if isinstance(pub.get("copy"), dict) else ""
        return {"text": f"Final reel (v{pub['version']}) is ready. Caption: {short(cap, 220)}",
                "poll": "Post it to Instagram?", "options": ["Approve", "Request changes"]}
    return {"text": "Update."}


APPROVE = re.compile(r"(^\s*(yes|ship it|post it|lgtm)\b)|\bapprove[ds]?\b", re.I)


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--once", action="store_true")
    a = p.parse_args()
    cfg = json.loads((STATE / "paperclip.json").read_text())
    token = json.loads((STATE / "board.json").read_text())["token"]
    api, cid = cfg["apiUrl"], cfg["companyId"]

    def call(method: str, path: str, body=None, raw: bytes | None = None, ctype: str = "application/json"):
        data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
        req = urllib.request.Request(api + path, data=data, method=method,
                                     headers={"Authorization": f"Bearer {token}", "Content-Type": ctype})
        with urllib.request.urlopen(req, timeout=60) as r:
            out = r.read()
        return json.loads(out) if out else None

    def send(issue: dict, spec: dict) -> None:
        number = re.search(r"\+\d{8,15}", issue.get("description") or "")  # "Started from iMessage Photon: +1..."
        if not number:
            raise ValueError(f"no phone number on chat issue {issue.get('identifier')}")
        cmd = ["node", f"--env-file={ROOT / 'photon' / '.env'}", str(ROOT / "photon" / "send_rich.mjs"), "--to", number.group(0)]
        for key in ("text", "effect", "link", "poll"):
            if spec.get(key):
                cmd += [f"--{key}", spec[key]]
        cmd += [x for f in spec.get("files", []) for x in ("--file", f)]
        cmd += [x for o in spec.get("options", []) for x in ("--option", o)]
        if spec.get("card"):
            card = dict(spec["card"])
            if card.get("image") and not Path(card["image"]).exists():
                card.pop("image"); card.pop("imageTitle", None); card.pop("imageSubtitle", None)
            card_file = STATE / "relay_card.json"
            card_file.write_text(json.dumps(card))
            cmd += ["--card", str(card_file)]
        out = subprocess.run(cmd, capture_output=True, text=True, timeout=180)
        if out.returncode:
            raise ValueError((out.stdout or out.stderr).strip()[-200:])

    def bridge_approval(run_id: str, issue: dict) -> None:
        """The founder replying APPROVE in the thread approves that campaign's pending board approval."""
        pending = call("GET", f"/companies/{cid}/approvals?status=pending") or []
        pending = pending.get("items", pending) if isinstance(pending, dict) else pending
        ap = next((x for x in pending if f"Approve {run_id} " in ((x.get("payload") or {}).get("title") or "")), None)
        if not ap:
            return
        replies = [c for c in call("GET", f"/issues/{issue['id']}/comments") or []
                   if c.get("authorUserId") and not c.get("authorAgentId") and c.get("createdAt", "") > ap.get("createdAt", "")]
        yes = next((c for c in replies if APPROVE.match(c.get("body") or "")), None)
        if yes:
            call("POST", f"/approvals/{ap['id']}/approve", {"decisionNote": f"Approved by the founder over iMessage: {yes['body'][:200]}"})
            send(issue, {"text": "Approved. The reel is queued for Instagram (posting is simulated in this demo).",
                         "effect": "confetti"})
            print(json.dumps({"approved": ap["id"], "run": run_id}), flush=True)

    sent = set(json.loads(SENT.read_text())) if SENT.exists() else set()
    while True:
        for brief_file in RUNS.glob("*/brief.json"):
            try:
                chat_issue = json.loads(brief_file.read_text()).get("chat_issue")
                if not chat_issue:
                    continue
                issue = call("GET", f"/issues/{chat_issue}")
                bridge_approval(brief_file.parent.name, issue)
                for png in sorted((brief_file.parent / "cards").glob("*.png"), key=lambda q: q.stat().st_mtime):
                    key = f"{brief_file.parent.name}/{png.name}/{int(png.stat().st_mtime)}"
                    if key in sent:
                        continue
                    stem = re.sub(r"_v\d+$", "", png.stem)
                    version = re.search(r"_v(\d+)$", png.stem)
                    spec = rich(brief_file.parent, stem, int(version.group(1)) if version else None)
                    if spec:
                        send(issue, spec)
                    text = spec.get("text", "")
                    sent.add(key)
                    SENT.write_text(json.dumps(sorted(sent)))
                    print(json.dumps({"sent": key, "text": text}), flush=True)
                    time.sleep(3)  # keep the thread readable and well under rate limits
            except (urllib.error.URLError, KeyError, ValueError, OSError, subprocess.TimeoutExpired) as e:
                print(json.dumps({"ok": False, "run": brief_file.parent.name, "error": str(e)[:200]}), flush=True)
        if a.once:
            return
        time.sleep(5)


if __name__ == "__main__":
    main()
