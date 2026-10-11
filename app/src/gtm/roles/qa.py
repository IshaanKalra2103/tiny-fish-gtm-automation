"""QA & Testing: Cresta-style evaluation of each draft, then revise -> re-render -> re-evaluate.

- 3 synthetic personas (from Bright Data comments) review 8 sampled frames + the transcript.
- Requirements are tagged must-have / nice-to-have; a must-have failure blocks approval.
- Deterministic compliance checks run alongside: length, cited evidence, CTA, hype words.
- Up to MAX_VERSIONS drafts; if none passes, the run is flagged for a human.
"""

import json
import re

from pydantic import BaseModel

from .. import config, llm
from ..run import Run
from . import strategy, video

ROLE = "qa"
MUST = ["Hook is readable and lands in the first 2 seconds",
        "On-screen text and captions are fully legible (not clipped, not covering the product)",
        "The product is actually shown",
        "One clear call to action",
        "Claims are credible and specific, with no hype the video doesn't back up"]
NICE = ["The pain point matches what this persona cares about", "Pacing holds attention to the end"]
HYPE = re.compile(r"\b(guarantee[ds]?|100%|never fails?|always works|revolutionary|game[- ]changer)\b", re.I)


class Check(BaseModel):
    requirement: str
    passed: bool
    note: str


class Review(BaseModel):
    checks: list[Check]
    score_1_10: int
    would_keep_watching: bool
    top_fix: str


def run(r: Run) -> str:
    history = []
    with r.timer(ROLE):
        for v in range(1, config.MAX_VERSIONS + 1):
            if not r.exists(f"script_v{v}.json"):
                strategy.write_script(r, v, feedback=_feedback(history[-1]))
            if not r.exists(f"video_v{v}.mp4"):
                video.render(r, v)
            result = evaluate(r, v)
            history.append(result)
            if result["passed"]:
                break
            r.log(ROLE, f"v{v} failed QA -> revising: {'; '.join(result['blocking'])[:200]}", version=v)
    final = history[-1]
    summary = {"final_version": final["version"], "passed": final["passed"],
               "status": "ready_for_approval" if final["passed"] else "needs_human",
               "versions": [{k: h[k] for k in ("version", "passed", "avg_score", "blocking")} for h in history]}
    r.write("qa.json", summary)
    msg = (f"QA: {len(history)} draft(s); v{final['version']} {'PASSED' if final['passed'] else 'still failing -> needs human'} "
           f"(avg {final['avg_score']}/10). " + " | ".join(f"v{h['version']}: {h['avg_score']}" for h in history))
    r.log(ROLE, msg)
    return msg


def evaluate(r: Run, v: int) -> dict:
    s = r.read(f"script_v{v}.json")
    info = r.read(f"video_v{v}.json")
    personas = r.read("personas.json")["personas"]
    frames = []
    for f in info["frames"]:
        frames += [llm.text(f"Frame at {f.split('_')[-1].removesuffix('.jpg')}"), llm.image(r.dir / f)]
    reqs = "\n".join([f"[MUST] {m}" for m in MUST] + [f"[NICE] {n}" for n in NICE])
    reviews = []
    for p in personas:
        rv = llm.parse(r, ROLE, "fast",
                       f"You are a SYNTHETIC persona reviewing a vertical short video: {json.dumps(p)}. "
                       "Judge only what is visible in the frames and audible in the transcript. Be strict and specific.",
                       frames + [llm.text(f"Video length: {info['seconds']}s.\nTranscript: {info['transcript']}\n\n"
                                          f"Evaluate each requirement exactly as written:\n{reqs}")], Review)
        reviews.append({"persona": p["name"], **rv.model_dump()})

    compliance = _compliance(r, s, info)
    must_fail = {}
    for rv in reviews:
        for c in rv["checks"]:
            req = re.sub(r"^\s*\[(MUST|NICE)\]\s*", "", c["requirement"], flags=re.I).lower()
            if not c["passed"] and any(req.startswith(m.lower()[:25]) for m in MUST):
                must_fail.setdefault(c["requirement"], []).append(f"{rv['persona']}: {c['note']}")
    blocking = [f"{req} ({len(notes)}/3 personas)" for req, notes in must_fail.items() if len(notes) >= 2]
    blocking += [f"compliance: {c['check']} - {c['note']}" for c in compliance if not c["passed"]]
    avg = round(sum(rv["score_1_10"] for rv in reviews) / len(reviews), 1)
    passed = not blocking and avg >= 7
    result = {"version": v, "passed": passed, "avg_score": avg, "blocking": blocking, "reviews": reviews,
              "compliance": compliance, "must_fail_notes": must_fail}
    r.write(f"qa_v{v}.json", result)
    r.log(ROLE, f"v{v}: avg {avg}/10, {'PASS' if passed else f'{len(blocking)} blocking issue(s)'}", version=v)
    return result


def _compliance(r: Run, s: dict, info: dict) -> list[dict]:
    allowed = {u.rstrip("/") for u in strategy.allowed_urls(r)}
    uncited = [c["claim"] for c in s["claims"] if c["evidence_url"].rstrip("/") not in allowed]
    hype = HYPE.findall(info["transcript"])
    return [
        {"check": f"length <= {config.MAX_VIDEO_SECONDS}s", "passed": info["seconds"] <= config.MAX_VIDEO_SECONDS,
         "note": f"{info['seconds']}s"},
        {"check": "every claim cites fetched evidence", "passed": not uncited, "note": "; ".join(uncited)[:300] or "ok"},
        {"check": "CTA present", "passed": bool(s["cta"].strip()), "note": s["cta"]},
        {"check": "no unsupported hype words", "passed": not hype, "note": ", ".join(hype) or "ok"},
    ]


def _feedback(result: dict) -> dict:
    return {"blocking_issues": result["blocking"],
            "persona_top_fixes": [{"persona": rv["persona"], "fix": rv["top_fix"]} for rv in result["reviews"]],
            "must_have_notes": result["must_fail_notes"]}
