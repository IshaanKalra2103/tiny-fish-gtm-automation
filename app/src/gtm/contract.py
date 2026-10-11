"""Dependency-free campaign contract shared by the control plane and workers."""

import json
import re
from urllib.parse import urlparse

STAGES = [
    ("research", "Trend discovery", "Write evidence.json and social_<platform>.json from live sources."),
    ("analysis", "Trend analysis", "Write insights.json (including template), personas.json and charts.json."),
    ("strategy", "Content strategy", "Write script_v1.json using insights and cited evidence."),
    ("video", "Render video", "Write video_v1.mp4 and video_v1.json with transcript and QA frames."),
    ("qa", "QA and revisions", "Evaluate and revise up to 3 drafts. Write qa.json and qa_vN.json. Failed QA blocks the pipeline."),
    ("publish", "Human approval", "Package final video and copy, request board approval, wait for a verified decision. Publishing is simulated."),
    ("learn", "Record learnings", "After approval, write learnings.json and update /workspace/runs/learnings.json. Scores are simulated."),
]
ORDER = [s[0] for s in STAGES]
OUTPUTS = {
    "research": ["evidence.json"],
    "analysis": ["insights.json", "personas.json", "charts.json"],
    "strategy": ["script_v1.json"],
    "video": ["video_v1.mp4", "video_v1.json"],
    "qa": ["qa.json"], "publish": ["publish.json"], "learn": ["learnings.json"],
}


def validate_brief(data: dict) -> dict:
    brief = dict(data)
    for key in ("brand_url", "niche", "audience", "goal"):
        if not isinstance(brief.get(key), str) or not brief[key].strip():
            raise ValueError(f"Campaign brief requires {key}")
    url = urlparse(brief["brand_url"])
    if url.scheme not in ("http", "https") or not url.netloc:
        raise ValueError("brand_url must be an HTTP(S) URL")
    brief.setdefault("brand", url.netloc.removeprefix("www."))
    platforms = brief.get("platforms", ["tiktok", "instagram", "youtube"])
    brief["platforms"] = [p.strip() for p in platforms.split(",") if p.strip()] if isinstance(platforms, str) else platforms
    if not isinstance(brief["platforms"], list) or not all(isinstance(p, str) for p in brief["platforms"]):
        raise ValueError("platforms must be a list of names")
    return brief


def brief_description(brief: dict) -> str:
    return "<!-- gtm-brief -->\n```json\n" + json.dumps(validate_brief(brief), indent=2) + "\n```\n<!-- /gtm-brief -->"


def parse_brief(description: str) -> dict:
    block = re.search(r"<!-- gtm-brief -->\s*```json\s*(.*?)\s*```\s*<!-- /gtm-brief -->", description, re.S)
    if block:
        return validate_brief(json.loads(block.group(1)))
    # Existing campaigns and manually authored issues remain readable.
    data = dict(re.findall(r"^\s*(brand|brand_url|niche|audience|goal|platforms)\s*:\s*(.+)$", description, re.M))
    labels = {"Brand / website": "brand_url", "Niche / theme": "niche", "Audience": "audience", "Goal": "goal", "Platforms": "platforms"}
    for label, value in re.findall(r"^- \*\*(.+?):\*\*\s*(.+)$", description, re.M):
        if label in labels:
            data.setdefault(labels[label], value.strip())
    return validate_brief(data)
