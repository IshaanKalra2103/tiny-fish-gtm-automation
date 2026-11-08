"""Market research per niche with TinyFish Search (+ Fetch on the top community threads). Collects signals;
the harness agent judges them and writes pmf.json."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path

from . import tf

DAY = 1440  # minutes


def queries(term: str, category: str | None, days: int) -> dict[str, dict]:
    """One search per signal type. Recency keeps it about *now*, not evergreen listicles."""
    recent = {"recency_minutes": days * DAY}
    return {
        "news": {"query": f"{term} trends", "domain_type": "news", **recent},
        "community": {"query": term, "include_domains": "reddit.com,news.ycombinator.com", **recent},
        "pains": {"query": f"{term} problems frustrating", "include_domains": "reddit.com,news.ycombinator.com",
                  "recency_minutes": days * 3 * DAY},
        "competitors": {"query": f"best {category} for {term}" if category else f"best tools for {term}"},
        "short_video": {"query": term, "include_domains": "tiktok.com,instagram.com,youtube.com", **recent},
    }


def slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:40]


UNITS = {"minute": 1 / 1440, "hour": 1 / 24, "day": 1, "week": 7, "month": 30, "year": 365}


def age_days(date: str | None) -> float | None:
    """Search dates come as "3 days ago", "Sep 29, 2026" or ISO. None when missing or unparseable."""
    if not date:
        return None
    m = re.match(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", date.strip(), re.I)
    if m:
        return int(m.group(1)) * UNITS[m.group(2).lower()]
    for fmt in ("%b %d, %Y", "%B %d, %Y", "%Y-%m-%d"):
        try:
            d = datetime.strptime(date.strip(), fmt)
            return (datetime.now() - d).total_seconds() / 86400
        except ValueError:
            pass
    try:
        d = datetime.fromisoformat(date.replace("Z", "+00:00"))
        return (datetime.now(timezone.utc) - (d if d.tzinfo else d.replace(tzinfo=timezone.utc))).total_seconds() / 86400
    except ValueError:
        return None


def fresh(hits: list[dict], days: int) -> tuple[int, int]:
    """(results dated within the window, results with any date)."""
    ages = [a for a in (age_days(h.get("date")) for h in hits) if a is not None]
    return sum(a <= days for a in ages), len(ages)


def scan(niches: list[dict], out_dir: Path, *, category: str | None = None, days: int = 30, read: int = 3) -> dict:
    """niches: [{"name": ..., "search_terms": [...]}]. Writes social URL lists for bd-gateway alongside."""
    out_dir.mkdir(parents=True, exist_ok=True)
    results = []
    for niche in niches:
        term = (niche.get("search_terms") or [niche["name"]])[0]
        buckets = {}
        for bucket, q in queries(term, category, days).items():
            buckets[bucket] = tf.search(**q)
            for h in buckets[bucket]:
                age = age_days(h.get("date"))
                h["age_days"] = round(age, 1) if age is not None else None
            tf.log(f"{niche['name']}: {bucket} -> {len(buckets[bucket])}")
        threads = []
        if read and buckets["community"] + buckets["pains"]:
            urls = list(dict.fromkeys(h["url"] for h in buckets["pains"] + buckets["community"]))[:read]
            pages, _ = tf.fetch(urls)
            threads = [{"url": p["url"], "title": p["title"], "excerpt": p["text"][:1500]} for p in pages]
        video_urls = [h["url"] for h in buckets["short_video"]]
        urls_file = None
        if video_urls:
            urls_file = out_dir / f"social_urls_{slug(niche['name'])}.txt"
            urls_file.write_text("\n".join(video_urls) + "\n")
        all_hits = [h for hits in buckets.values() for h in hits]
        results.append({
            "name": niche["name"],
            "term": term,
            "signals": {
                **{f"{b}_results": len(h) for b, h in buckets.items()},
                "fresh_results": fresh(all_hits, days)[0],
                "dated_results": fresh(all_hits, days)[1],
                "distinct_sites": len({h.get("site") for h in all_hits if h.get("site")}),
            },
            "buckets": buckets,
            "threads": threads,
            "social_urls_file": urls_file.name if urls_file else None,
        })
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "window_days": days,
        "category": category,
        "niches": results,
        "note": "Raw signals only. Counts are search results, not market size; judge them in pmf.json.",
    }
