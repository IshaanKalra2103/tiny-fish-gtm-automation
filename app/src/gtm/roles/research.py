"""Trend Discovery: TinyFish Search + Fetch + Agent + Browser, with Bright Data for TikTok/Reels engagement.

Order matters for wall-clock: the Agent run (3-6 min) starts first in a worker thread, Bright Data runs in
parallel subprocesses, and Search/Fetch/Browser fill the time in between.
"""

import json
import os
import re
import subprocess
from concurrent.futures import Future, ThreadPoolExecutor

from .. import config
from .. import tinyfish_tools as tf
from ..run import Run

ROLE = "research"
YT_SCHEMA = {"type": "object", "properties": {"videos": {"type": "array", "items": {"type": "object", "properties": {
    "title": {"type": "string"}, "channel": {"type": "string"}, "views": {"type": "string"},
    "uploaded": {"type": "string"}, "url": {"type": "string"}}}}}, "required": ["videos"]}


def run(r: Run) -> str:
    b = r.brief
    pmf = r.read("identity/pmf.json") or {}
    niche = pmf.get("chosen_niche") or b["niche"]  # stage 0 (identity/) picks the niche when it has run
    if pmf.get("chosen_niche"):
        r.log(ROLE, f"niche from identity/pmf.json: {niche}")
    with r.timer(ROLE), ThreadPoolExecutor(max_workers=4) as pool:
        # 1. Agent: YouTube Shorts needs real clicking (Fetch only gets the page footer there).
        yt: Future = pool.submit(tf.agent, r, f"https://www.youtube.com/results?search_query={niche.replace(' ', '+')}+%23shorts",
                                 "This is a YouTube search page. Click 'Filters', choose Upload date = 'This week', then "
                                 "Sort by = 'View count'. From the resulting list extract the top 8 videos: title, channel, "
                                 "view count, upload age and video URL. Do not open individual videos. Return JSON.",
                                 YT_SCHEMA, ROLE)

        # 2. Search: conversations, news, and social video URLs for Bright Data.
        threads = tf.search(r, f"{niche} problems failing", include_domains="reddit.com,news.ycombinator.com,dev.to",
                            recency_minutes=60 * 24 * 21)
        news = tf.search(r, f"{niche} launch", domain_type="news", recency_minutes=60 * 24 * 7)
        tiktok = tf.search(r, niche, include_domains="tiktok.com", recency_minutes=60 * 24 * 30)
        reels = tf.search(r, f"{niche} reel", include_domains="instagram.com", recency_minutes=60 * 24 * 30)
        social = {"tiktok": [h["url"] for h in tiktok if "/video/" in h["url"]],
                  "instagram": [h["url"] for h in reels if "/reel/" in h["url"]]}

        # 3. Bright Data: engagement + comments for the TikTok/Reel URLs Search found (parallel).
        bd = {p: pool.submit(_brightdata, r, p, urls) for p, urls in social.items() if urls}

        # 4. Fetch: read the threads and the brand's own site (claims must cite these).
        docs = tf.fetch(r, [h["url"] for h in threads[:8]] + [b["brand_url"]])

        # 5. Browser: vertical screenshots of the brand site for video B-roll.
        try:
            shots = [str(p.relative_to(r.dir)) for p in tf.screenshots(r, b["brand_url"], r.dir / "shots", role=ROLE)]
        except Exception as e:  # self-heal: video falls back to branded colour cards
            r.log(ROLE, f"Browser capture failed ({e}); video will use branded cards", level="warn")
            shots = []

        bd_status = {p: f.result() for p, f in bd.items()}
        youtube = _youtube(r, yt, niche)

    brand_doc = next((d for d in docs if d["url"].rstrip("/") == b["brand_url"].rstrip("/")), None)
    evidence = {
        "brief": {**b, "niche": niche},
        "threads": [{"url": d["url"], "title": d["title"], "text": d["text"][:5000]} for d in docs if d is not brand_doc],
        "brand_page": {"url": b["brand_url"], "text": (brand_doc or {}).get("text", "")[:6000]},
        "news": news,
        "social_search": {"tiktok": tiktok, "instagram": reels},
        "brightdata": bd_status,
        "youtube": youtube,
        "shots": shots,
    }
    r.write("evidence.json", evidence)
    summary = (f"evidence.json: {len(evidence['threads'])} threads, {len(news)} news, "
               f"{len(social['tiktok'])} TikToks + {len(social['instagram'])} Reels -> Bright Data "
               f"({', '.join(f'{p}: {s.get('posts', 0)} posts' if s.get('ok') else f'{p}: skipped' for p, s in bd_status.items())}), "
               f"{len(youtube['videos'])} YouTube Shorts via Agent, {len(shots)} Browser screenshots")
    r.log(ROLE, summary)
    return summary


def _brightdata(r: Run, platform: str, urls: list[str]) -> dict:
    """Run the brightdata/ gateway CLI; it writes runs/<id>/social_<platform>.json."""
    if not (config.BRIGHTDATA_DIR / "pyproject.toml").exists():
        r.log(ROLE, f"Bright Data gateway not found at {config.BRIGHTDATA_DIR}; skipping {platform}", level="warn")
        return {"ok": False, "error": "gateway missing"}
    urls_file = r.path(f"search_urls_{platform}.txt")
    urls_file.write_text("\n".join(urls) + "\n")
    r.log(ROLE, f"Bright Data: scraping {len(urls)} {platform} URLs found by TinyFish Search", primitive="brightdata")
    env = {**os.environ, "GTM_RUNS_DIR": str(config.RUNS_DIR)}
    try:
        p = subprocess.run(["uv", "run", "--project", str(config.BRIGHTDATA_DIR), "bd-gateway", "sample",
                            "--platform", platform, "--urls-file", str(urls_file), "--campaign", r.id,
                            "--posts", "10", "--top", "5", "--comments-per-post", "15"],
                           capture_output=True, text=True, timeout=900, env=env)
        line = (p.stdout.strip().splitlines() or ["{}"])[-1]
        status = json.loads(line)
    except Exception as e:
        status = {"ok": False, "error": str(e)}
    r.log(ROLE, f"Bright Data {platform}: {'ok' if status.get('ok') else 'failed: ' + str(status.get('error'))[:160]}",
          primitive="brightdata", **{k: v for k, v in status.items() if k in ("posts", "comments", "seconds")})
    return status


def _youtube(r: Run, fut: Future, niche: str) -> dict:
    try:
        res = fut.result(timeout=480)
        if res["ok"] and (res["result"] or {}).get("videos"):
            return {"source": "agent", "videos": res["result"]["videos"], "steps": res["steps"], "run_id": res["run_id"]}
        r.log(ROLE, f"Agent returned no videos ({res.get('error')}); falling back to Search", level="warn")
    except Exception as e:
        r.log(ROLE, f"Agent failed ({e}); falling back to Search", level="warn")
    # Self-healing fallback: cheaper primitive, less data (no view counts).
    hits = tf.search(r, f"{niche} shorts", include_domains="youtube.com", recency_minutes=60 * 24 * 14)
    return {"source": "search_fallback", "videos": [{"title": h["title"], "url": h["url"], "views": None} for h in hits]}


def social_posts(r: Run) -> list[dict]:
    """Bright Data posts across platforms, sorted by engagement (used by analysis)."""
    posts = []
    for platform in ("tiktok", "instagram"):
        data = r.read(f"social_{platform}.json")
        for p in (data or {}).get("posts", []):
            posts.append({**p, "platform": platform})
    key = lambda p: (p.get("views") or 0) + 10 * ((p.get("likes") or 0) + (p.get("comments") or 0))
    return sorted(posts, key=key, reverse=True)


def social_comments(r: Run) -> list[dict]:
    comments = []
    for platform in ("tiktok", "instagram"):
        data = r.read(f"social_{platform}.json")
        comments += [{**c, "platform": platform} for c in (data or {}).get("comments", [])]
    return sorted(comments, key=lambda c: c.get("likes") or 0, reverse=True)


def views_number(v) -> int:
    """'1.1K' -> 1100 for charts."""
    if isinstance(v, (int, float)):
        return int(v)
    m = re.match(r"([\d.,]+)\s*([KMB]?)", str(v or "").upper())
    if not m:
        return 0
    n = float(m.group(1).replace(",", ""))
    return int(n * {"": 1, "K": 1e3, "M": 1e6, "B": 1e9}[m.group(2)])
