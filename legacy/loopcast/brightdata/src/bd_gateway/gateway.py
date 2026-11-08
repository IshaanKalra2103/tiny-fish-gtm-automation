"""Bright Data Scraper API gateway for the GTM harness.

Pulls public posts (TikTok videos, Instagram Reels, YouTube videos, Reddit
threads) and the top comments under them, and returns them in one shape across
platforms. Two consumers in the harness:

  - trend analysis: views, engagement, length, sounds and hashtags of what's working
  - persona QA: comments become evidence for synthetic audience personas (docs/brightdata.md)

Runs alongside TinyFish: TinyFish Search finds post URLs (and is the only way to
find Instagram Reels by topic), and this gateway turns them into structured records
with engagement numbers, which TinyFish Fetch doesn't return.

Records are built from an allowlist of content and engagement fields, so commenter
identities and creator account fields (username, profile link, IDs, bio) never
leave this module, and @handles and emails inside the text are masked. Post URLs
are kept so the video can be watched and cited; on TikTok they contain the
creator's handle. The aim is to learn what works and what an audience cares
about, not to profile individual people.

API reference: https://docs.brightdata.com/api-reference/scrapers/synchronous-requests
Dataset ids and fields: https://docs.brightdata.com/scrapers/{domain}.json (checked 2026-10-11)
"""

from __future__ import annotations

import json
import os
import re
import statistics
import sys
import time
from collections import Counter
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import httpx

API = "https://api.brightdata.com/datasets/v3"
BACKOFF = (2, 4, 8, 16, 32)  # Bright Data blocks an IP after 25 429s in 5 minutes, so never retry a 429 at once
HANDLE = re.compile(r"(?<![\w/])(?:@|/?u/)[A-Za-z0-9_.-]{2,}")
EMAIL = re.compile(r"\b[\w.+-]+@[\w-]+\.[\w.-]+\b")
MAX_TEXT = 1000
NUMERIC = {"likes", "comments", "views", "shares", "saves", "replies", "creator_followers"}

Input = Callable[[str, int], dict]  # (query or url, limit) -> one Bright Data input object


@dataclass(frozen=True)
class Platform:
    """Where one platform's posts and comments come from, and which source fields to keep.

    discover maps a mode ("keyword", "hashtag", "from_url") to Bright Data's discover_by
    value and an input builder. Field maps go from our key to the source fields to try, in
    order: for "text" every field present is joined, for anything else the first one wins.
    """

    domains: tuple[str, ...]
    posts_dataset: str
    comments_dataset: str | None
    comments_input: Input
    discover: dict[str, tuple[str, Input]]
    post_fields: dict[str, tuple[str, ...]]
    comment_fields: dict[str, tuple[str, ...]]
    notes: str = field(default="")


PLATFORMS: dict[str, Platform] = {
    "tiktok": Platform(
        domains=("tiktok.com",),
        posts_dataset="gd_lu702nij2f790tmv9h",  # TikTok - Posts
        comments_dataset="gd_lkf2st302ap89utw5k",  # TikTok - Comments
        comments_input=lambda url, n: {"url": url, "num_of_comments": n},
        discover={
            "keyword": ("keyword", lambda q, n: {"search_keyword": q, "num_of_posts": n}),
            "hashtag": ("keyword", lambda q, n: {"search_keyword": "#" + q.lstrip("#"), "num_of_posts": n}),
            "from_url": ("profile_url", lambda u, n: {"url": u, "num_of_posts": n}),
        },
        post_fields={
            "url": ("url",),
            "text": ("description",),
            "views": ("play_count",),
            "likes": ("digg_count",),
            "comments": ("comment_count",),
            "shares": ("num_share_count", "share_count"),
            "saves": ("collect_count",),
            "duration_s": ("video_duration",),
            "sound": ("original_sound",),
            "hashtags": ("hashtags",),
            "creator_followers": ("profile_followers",),
            "posted_at": ("create_time",),
        },
        comment_fields={
            "post_url": ("post_url",),
            "text": ("comment_text",),
            "likes": ("num_likes",),
            "replies": ("num_replies",),
            "posted_at": ("date_created",),
        },
        notes="Post URLs and 'original sound' titles contain the creator's handle.",
    ),
    "instagram": Platform(
        domains=("instagram.com",),
        posts_dataset="gd_lyclm20il4r5helnj",  # Instagram - Reels
        comments_dataset="gd_ltppn085pokosxh13",  # Instagram - Comments (latest 15 per post)
        comments_input=lambda url, n: {"url": url},
        discover={
            # No keyword or hashtag discovery on Instagram: find reel URLs with TinyFish Search instead.
            "from_url": ("url", lambda u, n: {"url": u, "num_of_posts": n}),
        },
        post_fields={
            "url": ("url",),
            "text": ("description",),
            "views": ("views", "video_play_count"),
            "likes": ("likes",),
            "comments": ("num_comments",),
            "duration_s": ("length",),
            "sound": ("audio_url",),
            "hashtags": ("hashtags",),
            "creator_followers": ("followers",),
            "posted_at": ("date_posted",),
        },
        comment_fields={
            "post_url": ("post_url",),
            "text": ("comment",),
            "likes": ("likes_number",),
            "replies": ("replies_number",),
            "posted_at": ("comment_date",),
        },
        notes="Instagram media links expire 24 hours after collection.",
    ),
    "youtube": Platform(
        domains=("youtube.com", "youtu.be"),
        posts_dataset="gd_lk56epmy2i5g7lzu0k",  # Youtube - Videos posts
        comments_dataset="gd_lk9q0ew71spt1mxywf",  # Youtube - Comments
        comments_input=lambda url, n: {"url": url, "num_of_comments": n},
        discover={
            "keyword": ("keyword", lambda q, n: {"keyword": q, "num_of_posts": str(n)}),
            "hashtag": ("hashtag", lambda q, n: {"hashtag": q.lstrip("#"), "num_of_posts": str(n)}),
            "from_url": ("url", lambda u, n: {"url": u, "num_of_posts": n}),
        },
        post_fields={
            "url": ("url",),
            "text": ("title", "description"),
            "format": ("post_type",),  # "short" for Shorts
            "views": ("views",),
            "likes": ("likes",),
            "comments": ("num_comments",),
            "duration_s": ("video_length",),
            "hashtags": ("hashtags",),
            "creator_followers": ("subscribers",),
            "posted_at": ("date_posted",),
        },
        comment_fields={
            "post_url": ("url",),
            "text": ("comment_text",),
            "likes": ("likes",),
            "replies": ("replies",),
            "posted_at": ("date_iso", "date"),
        },
    ),
    "reddit": Platform(
        domains=("reddit.com",),
        posts_dataset="gd_lvz8ah06191smkebj4",  # Reddit - Posts
        comments_dataset="gd_lvzdpsdlw09j6t702",  # Reddit - Comments
        comments_input=lambda url, n: {"url": url, "comment_limit": n, "load_all_replies": False},
        discover={
            "keyword": ("keyword", lambda q, n: {"keyword": q, "date": "Past week", "num_of_posts": n, "sort_by": "Top"}),
            "from_url": ("subreddit_url", lambda u, n: {"url": u, "num_of_posts": n, "sort_by": "Top"}),
        },
        post_fields={
            "url": ("url",),
            "text": ("title", "description"),
            "community": ("community_name",),
            "likes": ("num_upvotes",),
            "comments": ("num_comments",),
            "posted_at": ("date_posted",),
        },
        comment_fields={
            "post_url": ("post_url",),
            "text": ("comment",),
            "likes": ("num_upvotes",),
            "replies": ("num_replies",),
            "posted_at": ("date_posted",),
        },
    ),
}


class BrightDataError(RuntimeError):
    pass


class BrightDataGateway:
    """Thin client over Bright Data's Scraper API.

    Low level: scrape(), trigger(), progress(), download(), wait().
    For the harness: posts(), comments() and sample(), which return identifier-free
    records in the same shape for every platform.
    """

    def __init__(self, api_key: str | None = None, *, poll_every: float = 10, max_wait: float = 600, log=None,
                 transport: httpx.BaseTransport | None = None):
        key = api_key or os.environ.get("BRIGHTDATA_API_KEY")
        if not key:
            raise BrightDataError("BRIGHTDATA_API_KEY is not set (get one at https://brightdata.com/cp/setting/users)")
        self.poll_every = poll_every
        self.max_wait = max_wait
        self.log = log or (lambda msg: print(f"[brightdata] {msg}", file=sys.stderr))
        # A sync /scrape holds the connection for up to 1 minute before answering 202.
        self.http = httpx.Client(base_url=API, headers={"Authorization": f"Bearer {key}"}, timeout=90,
                                 transport=transport)

    # ---- low level -------------------------------------------------------------------

    def _request(self, method: str, path: str, **kw) -> httpx.Response:
        for wait in (*BACKOFF, None):
            r = self.http.request(method, path, **kw)
            if r.status_code != 429:
                break
            if wait is None:
                raise BrightDataError(f"429 from Bright Data after {len(BACKOFF)} backoffs; slow down")
            wait = int(r.headers.get("retry-after", wait))
            self.log(f"429, waiting {wait}s")
            time.sleep(wait)
        if r.status_code >= 400:
            raise BrightDataError(f"{method} {path} -> {r.status_code}: {r.text[:500]}")
        return r

    @staticmethod
    def _params(dataset_id: str, discover_by: str | None) -> dict:
        params = {"dataset_id": dataset_id, "format": "json", "include_errors": "true"}
        if discover_by:
            params |= {"type": "discover_new", "discover_by": discover_by}
        return params

    @staticmethod
    def _body(inputs: list[dict], limit_per_input: int | None) -> Any:
        return {"input": inputs, "limit_per_input": limit_per_input} if limit_per_input else inputs

    @staticmethod
    def _rows(r: httpx.Response) -> list[dict]:
        try:
            data = r.json()
        except ValueError:  # NDJSON
            data = [json.loads(line) for line in r.text.splitlines() if line.strip()]
        return data if isinstance(data, list) else [data]

    def scrape(self, dataset_id: str, inputs: list[dict], *, discover_by: str | None = None,
               limit_per_input: int | None = None) -> list[dict]:
        """Synchronous collect. If Bright Data needs more than a minute it answers 202, and we wait on the snapshot."""
        r = self._request("POST", "/scrape", params=self._params(dataset_id, discover_by),
                          json=self._body(inputs, limit_per_input))
        if r.status_code == 202:
            snapshot = r.json()["snapshot_id"]
            self.log(f"still running after 1 min, waiting on snapshot {snapshot}")
            return self.wait(snapshot, first_wait=int(r.headers.get("retry-after", self.poll_every)))
        return self._rows(r)

    def trigger(self, dataset_id: str, inputs: list[dict], *, discover_by: str | None = None,
                limit_per_input: int | None = None) -> str:
        """Asynchronous collect for bigger batches. Returns a snapshot_id."""
        r = self._request("POST", "/trigger", params=self._params(dataset_id, discover_by),
                          json=self._body(inputs, limit_per_input))
        return r.json()["snapshot_id"]

    def progress(self, snapshot_id: str) -> str:
        """One of starting, running, ready, failed, canceled."""
        return self._request("GET", f"/progress/{snapshot_id}").json().get("status", "unknown")

    def download(self, snapshot_id: str) -> list[dict]:
        return self._rows(self._request("GET", f"/snapshot/{snapshot_id}", params={"format": "json"}))

    def wait(self, snapshot_id: str, *, first_wait: float = 0) -> list[dict]:
        time.sleep(first_wait)
        deadline = time.monotonic() + self.max_wait
        while (status := self.progress(snapshot_id)) not in ("ready", "failed", "canceled"):
            if time.monotonic() > deadline:
                raise BrightDataError(f"snapshot {snapshot_id} still {status} after {self.max_wait}s")
            time.sleep(self.poll_every)
        if status != "ready":
            raise BrightDataError(f"snapshot {snapshot_id} {status}")
        return self.download(snapshot_id)

    # ---- for the harness -------------------------------------------------------------

    def posts(self, platform: str, *, keyword: str | None = None, hashtag: str | None = None,
              from_url: str | None = None, urls: list[str] | None = None, limit: int = 10) -> tuple[list[dict], list[dict]]:
        """Posts found one of four ways. Returns (posts, errors).

        keyword / hashtag: search the platform (not Instagram).
        from_url: recent posts from a profile, channel or subreddit, e.g. a competitor's account.
        urls: specific posts, e.g. the ones TinyFish Search found. URLs from other sites are skipped.
        """
        p = _platform(platform)
        if urls:
            mine = [u for u in urls if any(d in u for d in p.domains)][:limit]
            if not mine:
                raise BrightDataError(f"{platform}: none of the {len(urls)} URLs are on {', '.join(p.domains)}")
            rows = self.scrape(p.posts_dataset, [{"url": u} for u in mine])
        else:
            mode, query = next(((m, q) for m, q in (("keyword", keyword), ("hashtag", hashtag), ("from_url", from_url)) if q),
                               (None, None))
            if mode is None:
                raise BrightDataError("pass one of keyword=, hashtag=, from_url= or urls=")
            if mode not in p.discover:
                hint = " (find reel URLs with TinyFish Search and pass urls=)" if platform == "instagram" else ""
                raise BrightDataError(f"{platform} has no {mode} search; it supports {sorted(p.discover)} or urls={hint}")
            discover_by, build = p.discover[mode]
            rows = self.scrape(p.posts_dataset, [build(query, limit)], discover_by=discover_by, limit_per_input=limit)
        good, errors = _split_errors(rows)
        return [_derive(_pick(row, p.post_fields, platform)) for row in good], errors

    def comments(self, platform: str, post_urls: list[str], *, per_post: int = 20) -> tuple[list[dict], list[dict]]:
        """Comments under each post. Returns (comments, errors)."""
        p = _platform(platform)
        if not p.comments_dataset or not post_urls:
            return [], []
        rows = self.scrape(p.comments_dataset, [p.comments_input(u, per_post) for u in post_urls])
        good, errors = _split_errors(rows)
        return [c for c in (_pick(row, p.comment_fields, platform) for row in good) if c.get("text")], errors

    def sample(self, platform: str, *, keyword: str | None = None, hashtag: str | None = None,
               from_url: str | None = None, urls: list[str] | None = None, posts: int = 10,
               comments_per_post: int = 20, comment_on_top: int = 5) -> dict:
        """Posts + comments under the top ones + summary stats, as one JSON-ready dict."""
        started = time.monotonic()
        found, post_errors = self.posts(platform, keyword=keyword, hashtag=hashtag, from_url=from_url,
                                        urls=urls, limit=posts)
        found.sort(key=lambda x: (x.get("views") or 0, x.get("likes") or 0, x.get("comments") or 0), reverse=True)
        top_urls = [x["url"] for x in found[:comment_on_top] if x.get("url")]
        said, comment_errors = self.comments(platform, top_urls, per_post=comments_per_post)
        said.sort(key=lambda x: x.get("likes") or 0, reverse=True)
        p = _platform(platform)
        return {
            "source": "brightdata",
            "platform": platform,
            "query": {"keyword": keyword, "hashtag": hashtag, "from_url": from_url, "urls": urls},
            "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "seconds": round(time.monotonic() - started, 1),
            "datasets": {"posts": p.posts_dataset, "comments": p.comments_dataset},
            "note": ("Aggregate public content for trend analysis and SYNTHETIC personas. Commenter identities and "
                     "creator account fields are not kept. Personas built from this are simulations, not real or "
                     "representative people. "
                     + p.notes).strip(),
            "stats": _stats(found, said, len(post_errors) + len(comment_errors)),
            "posts": found,
            "comments": said,
            "errors": post_errors + comment_errors,
        }


def _platform(name: str) -> Platform:
    if name not in PLATFORMS:
        raise BrightDataError(f"unknown platform {name!r}; have {sorted(PLATFORMS)}")
    return PLATFORMS[name]


def _split_errors(rows: list[dict]) -> tuple[list[dict], list[dict]]:
    good, errors = [], []
    for row in rows:
        if row.get("error") or row.get("error_code"):
            errors.append({"error": row.get("error_code") or row.get("error"), "input": row.get("input")})
        else:
            good.append(row)
    return good, errors


def _scrub(text: str) -> str:
    text = EMAIL.sub("[email]", HANDLE.sub("@user", text))
    return text if len(text) <= MAX_TEXT else text[:MAX_TEXT] + "…"


def _num(v) -> float | int | None:
    """Counts arrive as numbers or as text like "12,345" / "1.2K" / "3M"."""
    if isinstance(v, bool) or v is None:
        return None
    if isinstance(v, (int, float)):
        return v
    m = re.fullmatch(r"\s*([\d.,]+)\s*([KkMmBb]?)\s*", str(v))
    if not m:
        return None
    n = float(m.group(1).replace(",", ""))
    n *= {"": 1, "k": 1e3, "m": 1e6, "b": 1e9}[m.group(2).lower()]
    return int(n) if n == int(n) else n


def _seconds(v) -> float | None:
    """Durations arrive as seconds, or as text like "15.2" or "0:15"."""
    if isinstance(v, (int, float)) and not isinstance(v, bool):
        return float(v)
    if isinstance(v, str) and v.strip():
        try:
            parts = [float(x) for x in v.strip().split(":")]
        except ValueError:
            return None
        total = 0.0
        for x in parts:
            total = total * 60 + x
        return total
    return None


def _tags(v) -> list[str]:
    """Hashtags arrive as strings, or as objects holding the tag text and a link."""
    out = []
    for item in v if isinstance(v, list) else []:
        if isinstance(item, dict):
            item = next((x for x in item.values() if isinstance(x, str) and not x.startswith("http")), None)
        if isinstance(item, str) and item.strip():
            out.append("#" + item.strip().lstrip("#").lower())
    return out


def _pick(row: dict, fields: dict[str, tuple[str, ...]], platform: str) -> dict:
    out: dict[str, Any] = {"platform": platform}
    for key, sources in fields.items():
        if key == "text":
            parts = [str(row[s]).strip() for s in sources if row.get(s)]
            out["text"] = _scrub("\n".join(parts)) if parts else ""
            continue
        value = next((row[s] for s in sources if row.get(s) not in (None, "")), None)
        if key == "hashtags":
            out[key] = _tags(value)
        elif key == "duration_s":
            out[key] = _seconds(value)
        elif key in NUMERIC:
            out[key] = _num(value)
        elif key == "sound":
            out[key] = _scrub(str(value)) if value else None
        else:
            out[key] = value
    return out


def _derive(post: dict) -> dict:
    views = post.get("views")
    if views:
        engaged = sum(post.get(k) or 0 for k in ("likes", "comments", "shares"))
        post["engagement_rate"] = round(engaged / views, 4)
    return post


def _median(values) -> float | None:
    nums = [v for v in values if isinstance(v, (int, float))]
    return statistics.median(nums) if nums else None


def _stats(posts: list[dict], comments: list[dict], errors: int) -> dict:
    return {
        "posts": len(posts),
        "comments": len(comments),
        "errors": errors,
        "median_views": _median(p.get("views") for p in posts),
        "median_likes": _median(p.get("likes") for p in posts),
        "median_engagement_rate": _median(p.get("engagement_rate") for p in posts),
        "median_duration_s": _median(p.get("duration_s") for p in posts),
        "median_comment_likes": _median(c.get("likes") for c in comments),
        "top_hashtags": Counter(t for p in posts for t in p.get("hashtags") or []).most_common(10),
        "top_sounds": Counter(p["sound"] for p in posts if p.get("sound")).most_common(5),
    }
