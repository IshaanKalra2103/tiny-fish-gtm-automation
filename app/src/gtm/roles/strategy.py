"""Template & Strategy: turn the mined template into a script. Every factual claim must cite fetched evidence.

Also used by QA for revisions: `write_script(run, version, feedback)` folds persona + compliance feedback in.
"""

import json

from pydantic import BaseModel, Field

from .. import config, llm
from ..run import Run

ROLE = "strategy"


class Scene(BaseModel):
    voiceover: str
    on_screen_text: str = Field(description="<= 5 words, shown in the top title band")
    shot: int = Field(description="index of the brand screenshot to show behind this scene")


class Claim(BaseModel):
    claim: str
    evidence_url: str


class Script(BaseModel):
    hook: str = Field(description="first line of voiceover, <= 10 words")
    scenes: list[Scene]
    cta: str
    claims: list[Claim]
    target_persona: str
    changes_from_previous: str = Field(description="for revisions: what changed and why; else 'first draft'")


def run(r: Run) -> str:
    with r.timer(ROLE):
        s = write_script(r, 1)
    return f"script_v1.json: '{s.hook}' ({len(s.scenes)} scenes, {len(s.claims)} cited claims)"


def write_script(r: Run, version: int, feedback: dict | None = None) -> Script:
    ev = r.read("evidence.json")
    ins = r.read("insights.json")
    personas = r.read("personas.json")
    shots = ev.get("shots", [])
    identity = r.read("identity/identity.json")
    allowed = sorted(allowed_urls(r))
    words = int(config.MAX_VIDEO_SECONDS * 2.3 * 0.8)  # ~2.3 spoken words/s, 20% headroom
    content = [llm.text(
        f"Brand: {ev['brief']['brand']} ({ev['brief']['brand_url']}). Goal: {ev['brief']['goal']}.\n"
        f"Brand page (the only source for product claims):\n{ev['brand_page']['text'][:4000]}\n\n"
        f"Mined template + themes:\n{json.dumps(ins)[:8000]}\n\n"
        f"Personas who will review it:\n{json.dumps(personas['personas'])[:4000]}\n\n"
        f"Allowed evidence URLs for claims: {json.dumps(allowed)}\n"
        f"Hard limits: total voiceover <= {words} words (video must be under {config.MAX_VIDEO_SECONDS}s), "
        f"4-6 scenes, hook spoken in the first 2 seconds, one clear CTA. "
        f"There are {len(shots)} screenshots (indexes 0..{max(len(shots) - 1, 0)}), shown below in order.")]
    if identity:
        content.append(llm.text("Product identity (follow its voice do/don't rules; product claims may only come from its "
                                "value_props/proof):\n" + json.dumps({k: identity.get(k) for k in (
                                    "one_liner", "what_it_really_is", "audience", "value_props", "proof", "voice")})[:6000]))
        if r.exists("identity/moodboard.png"):
            content += [llm.text("Brand moodboard (visual reference):"), llm.image(r.dir / "identity/moodboard.png", "image/png")]
    content += [llm.image(r.dir / s) for s in shots]
    if feedback:
        content.append(llm.text(f"This is revision v{version}. Fix every issue below; keep what worked.\n"
                                + json.dumps(feedback)[:8000]))
    script = llm.parse(r, ROLE, "smart",
                       "You are a creative strategist writing a vertical short-form video script for developers. "
                       "Be concrete and credible: show, don't hype. Never invent numbers or customer names.",
                       content, Script)
    r.write(f"script_v{version}.json", script.model_dump())
    r.log(ROLE, f"script_v{version}: '{script.hook}'", version=version)
    return script


def allowed_urls(r: Run) -> set[str]:
    """URLs a script claim may cite: fetched threads, news, the brand page, and identity proof (stage 0)."""
    ev = r.read("evidence.json")
    urls = {t["url"] for t in ev["threads"]} | {ev["brand_page"]["url"]} | {n["url"] for n in ev["news"]}
    identity = r.read("identity/identity.json") or {}
    urls |= {c.get("evidence_url") for c in (identity.get("value_props") or []) + (identity.get("proof") or [])
             if isinstance(c, dict) and c.get("evidence_url")}
    return urls
