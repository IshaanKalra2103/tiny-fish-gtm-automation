"""Analysis & Insight: engagement-weighted trends, a reusable content template, and evidence-grounded personas.

Personas come from Bright Data comment clusters (weighted by likes). Without Bright Data data, they fall back to
the comment text inside the threads TinyFish Fetch read, and say so.
"""

import json

from pydantic import BaseModel, Field

from .. import config, llm
from ..run import Run
from .research import social_comments, social_posts, views_number

ROLE = "analysis"


class Theme(BaseModel):
    name: str
    pain_point: str
    weight: int = Field(description="1-10, how strongly the evidence supports it, weighting engagement")
    evidence_urls: list[str]


class Hook(BaseModel):
    text: str
    source_url: str
    why_it_works: str


class Template(BaseModel):
    name: str
    hook_pattern: str
    beats: list[str]
    length_seconds: int
    caption_style: str
    cta_pattern: str
    why: str = Field(description="which evidence (with engagement numbers) supports this template")


class Insights(BaseModel):
    themes: list[Theme]
    top_hooks: list[Hook]
    formats: list[str] = Field(description="recurring video formats seen in the top social posts")
    template: Template


class Persona(BaseModel):
    name: str
    who: str
    responds_to: list[str]
    drops_off_when: list[str]
    needs_proof_of: list[str]
    cited_comments: list[str] = Field(description="2-4 verbatim short quotes from the comments this persona is built on")


class Personas(BaseModel):
    personas: list[Persona]


def run(r: Run) -> str:
    ev = r.read("evidence.json")
    posts = social_posts(r)
    comments = social_comments(r)
    with r.timer(ROLE):
        compact = {
            "brief": ev["brief"],
            "top_social_posts": [{k: p.get(k) for k in ("platform", "url", "text", "views", "likes", "comments", "shares", "hashtags")}
                                 for p in posts[:15]],
            "youtube_shorts_this_week": ev["youtube"]["videos"][:8],
            "threads": [{"url": t["url"], "title": t["title"], "text": t["text"][:2500]} for t in ev["threads"][:8]],
            "news": [{"title": n["title"], "url": n["url"], "snippet": n["snippet"]} for n in ev["news"][:8]],
            "learnings_from_past_runs": _memory(),
        }
        insights = llm.parse(r, ROLE, "fast",
                             "You are a trend analyst and pattern miner on a growth team. Ground every claim in the "
                             "evidence and its engagement numbers. Prefer patterns that recur across platforms.",
                             [llm.text(json.dumps(compact, default=str)[:60000])], Insights)
        r.write("insights.json", insights.model_dump())

        source = "brightdata_comments" if comments else "fetched_thread_text"
        audience = ([{"text": c["text"][:300], "likes": c.get("likes"), "platform": c["platform"]} for c in comments[:120]]
                    if comments else [{"thread": t["title"], "text": t["text"][:3000]} for t in ev["threads"][:8]])
        personas = llm.parse(r, ROLE, "fast",
                             "Cluster these public audience comments into recurring wants, objections and questions, "
                             "weighted by likes. Write exactly 3 distinct SYNTHETIC personas for reviewing short-form "
                             "videos. They are simulations derived from aggregate public content, not real people. "
                             "Never use usernames.",
                             [llm.text(f"Niche: {ev['brief']['niche']}. Audience: {ev['brief']['audience']}.\n"
                                       + json.dumps(audience, default=str)[:40000])], Personas)
        r.write("personas.json", {"source": source, "label": "Synthetic personas derived from aggregate public-content "
                                  "patterns; hypotheses, not audience validation.",
                                  "personas": [p.model_dump() for p in personas.personas]})

    r.write("charts.json", _chart_data(ev, posts, insights))
    summary = (f"insights.json: {len(insights.themes)} themes, template '{insights.template.name}'; "
               f"personas.json: {len(personas.personas)} personas from {source} ({len(comments)} comments)")
    r.log(ROLE, summary)
    return summary


def _memory() -> list:
    return json.loads(config.MEMORY_FILE.read_text())[-10:] if config.MEMORY_FILE.exists() else []


def _chart_data(ev: dict, posts: list[dict], ins: Insights) -> dict:
    yt = [{"label": v.get("title", "")[:40], "value": views_number(v.get("views"))} for v in ev["youtube"]["videos"][:8]]
    return {
        "themes": [{"label": t.name, "value": t.weight} for t in ins.themes],
        "sources": {"Reddit/HN/dev.to threads": len(ev["threads"]), "News": len(ev["news"]),
                    "TikTok (Bright Data)": sum(p["platform"] == "tiktok" for p in posts),
                    "Reels (Bright Data)": sum(p["platform"] == "instagram" for p in posts),
                    "YouTube Shorts (Agent)": len(ev["youtube"]["videos"])},
        "social_top": [{"label": f"{p['platform']}: {(p.get('text') or '')[:36]}", "value": p.get("views") or 0,
                        "likes": p.get("likes") or 0, "url": p.get("url")} for p in posts[:10]],
        "youtube": yt,
    }
