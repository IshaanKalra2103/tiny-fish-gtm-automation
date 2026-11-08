# brightdata: social data gateway (TikTok, Instagram Reels, YouTube, Reddit)

A small gateway over Bright Data's [Scraper API](https://docs.brightdata.com/api-reference/scrapers/synchronous-requests). It pulls public posts, plus the top comments under the best of them, and returns them in one shape across platforms. The output is written to the run folder the harness agents share. It feeds two steps:

- **Trend analysis:** views, engagement rate, video length, sounds and hashtags of what's working in the niche.
- **Persona QA:** comments become the evidence for three **synthetic** audience personas that critique the video (the idea in `docs/brightdata.md`).

## How it fits with TinyFish

| Job | Tool |
|---|---|
| Find which posts and threads matter this week | TinyFish **Search** |
| Read pages as text | TinyFish **Fetch** |
| Filter TikTok Creative Center's Top Ads | TinyFish **Agent** |
| Get structured records with views, likes, shares, length and sound, plus comments | **Bright Data** (this gateway) |

- **TinyFish Fetch doesn't return the numbers.** It reads Reddit threads but returns no upvote counts, and it gets only the footer of a YouTube Shorts page (see `CURRENT.md`).
- **Instagram can't be searched by keyword in Bright Data.** Use TinyFish Search to find reel URLs (`include_domains=instagram.com`), then pass them in with `--urls-file`. The gateway skips any URL that isn't on the chosen platform, so you can hand it a whole list of search results.

## What it gets per platform

| Platform | Find posts by | Fields kept per post | Comments |
|---|---|---|---|
| `tiktok` | keyword, hashtag, profile URL, post URLs | views, likes, comments, shares, saves, length, sound, hashtags, creator follower count | up to `--comments-per-post` |
| `instagram` (Reels) | profile URL, reel URLs (no keyword search) | views, likes, comments, length, audio link, hashtags, creator follower count | latest 15 per reel |
| `youtube` | keyword, hashtag, channel URL, video URLs | views, likes, comments, length, Short or regular video, hashtags, subscriber count | up to `--comments-per-post` |
| `reddit` | keyword (past week, top), subreddit URL, post URLs | upvotes, comment count, subreddit | up to `--comments-per-post` |

**Derived:** each post with views gets `engagement_rate = (likes + comments + shares) / views`.

**Summary per sample:** medians of views, likes, engagement rate, length and comment likes, plus the top 10 hashtags and top 5 sounds.

The dataset IDs and field names come from `docs.brightdata.com/scrapers/{domain}.json`, checked on Oct 11 2026. Run `bd-gateway platforms` to list them.

## Privacy and terms

- **Commenters and creator accounts are dropped.** Records are built from an allowlist of fields, so commenter identities and creator account fields (username, profile link, IDs, bio) never come out. Handles and emails inside text are replaced with `@user` and `[email]`.
- **Post URLs are kept**, so you can watch and cite the video. On TikTok those URLs contain the creator's handle, and so do "original sound" titles.
- **Known gap:** a profile URL pasted inside a comment isn't masked.
- **Platform terms:** `docs/brightdata.md` notes that TikTok's US terms restrict automated extraction unless you're authorized, and that Meta has its own rules on automated collection. Keep samples small, and check those terms and Bright Data's permitted-use conditions before you rely on this for anything beyond a demo.
- **Instagram media links** in the records expire 24 hours after collection.

## Setup

```bash
cd brightdata
cp .env.example .env        # add BRIGHTDATA_API_KEY (free tier: 5,000 credits/month)
uv sync
uv run pytest               # 12 offline tests against a fake API; no key needed
```

## Use it from the harness

Paperclip's process agents run inside the container, with the project mounted at `/workspace`:

```bash
uv run --project /workspace/brightdata bd-gateway sample --campaign <id> --platform tiktok --keyword "AI agents"
# writes /workspace/runs/<id>/social_tiktok.json and prints one JSON line:
# {"ok": true, "path": "...", "posts": 10, "comments": 92, "errors": 0, "median_views": 48000, "median_engagement_rate": 0.061, "seconds": 52.3}
```

```bash
bd-gateway sample --campaign <id> --platform tiktok --hashtag aitools
bd-gateway sample --campaign <id> --platform instagram --from-url https://www.instagram.com/<competitor>/
bd-gateway sample --campaign <id> --platform instagram --urls-file runs/<id>/search_urls.txt   # from TinyFish Search
bd-gateway sample --out sample.json --platform youtube --keyword "browser agent" --posts 5 --top 3
bd-gateway platforms                       # dataset ids and search modes per platform
bd-gateway status <snapshot_id>            # check a long-running Bright Data job
```

`--top 0` collects posts only, with no comments, which costs fewer Bright Data records. When something fails, stdout gets `{"ok": false, "error": ...}` and the exit code is 1, so the calling agent can post the error on its Paperclip issue.

## Use it from Python (`app/`)

```bash
cd app && uv add --editable ../brightdata
```

```python
from bd_gateway import BrightDataGateway

gw = BrightDataGateway()                                   # reads BRIGHTDATA_API_KEY
tiktok = gw.sample("tiktok", keyword="AI agents", posts=10)
reels = gw.sample("instagram", urls=tinyfish_result_urls)   # non-Instagram URLs are skipped
posts, errors = gw.posts("youtube", hashtag="aitools")      # posts only
rows = gw.scrape("gd_...", [{"url": "..."}])                # any Bright Data scraper, raw records
```

## Output (`runs/<campaign>/social_<platform>.json`)

```json
{
  "source": "brightdata", "platform": "tiktok",
  "query": {"keyword": "AI agents", "hashtag": null, "from_url": null, "urls": null},
  "collected_at": "2026-10-11T20:15:02+00:00", "seconds": 52.3,
  "datasets": {"posts": "gd_lu702nij2f790tmv9h", "comments": "gd_lkf2st302ap89utw5k"},
  "note": "Aggregate public content for trend analysis and SYNTHETIC personas. ...",
  "stats": {"posts": 10, "comments": 92, "errors": 0, "median_views": 48000, "median_likes": 2100,
            "median_engagement_rate": 0.061, "median_duration_s": 24.0, "median_comment_likes": 14,
            "top_hashtags": [["#ai", 7], ["#aitools", 4]], "top_sounds": [["Espresso", 2]]},
  "posts": [{"platform": "tiktok", "url": "...", "text": "...", "views": 200000, "likes": 15000, "comments": 300,
             "shares": 700, "saves": 900, "duration_s": 21.0, "sound": "...", "hashtags": ["#ai"],
             "creator_followers": 50000, "posted_at": "...", "engagement_rate": 0.08}],
  "comments": [{"platform": "tiktok", "post_url": "...", "text": "show it actually working first",
                "likes": 400, "replies": 12, "posted_at": "..."}],
  "errors": [{"error": "dead_page", "input": {"url": "..."}}]
}
```

Posts are sorted by views, then likes. Comments are sorted by likes. Comments are only read under the top `--top` posts, to keep record counts, and cost, low.

## How the persona step should use it

1. Cluster the comments into recurring wants, objections and questions, weighted by `likes`.
2. Write three personas from those clusters. For each, record what they respond to, what makes them scroll past, and what proof they need. Each trait cites the two or three comments it came from.
3. Label every persona *"Synthetic persona, derived from aggregate public-content patterns"*. Treat its scores as hypotheses to check against real engagement later, not as audience validation.

## How it calls Bright Data

- **Request:** every call is a synchronous `POST /datasets/v3/scrape`. Searches add `type=discover_new&discover_by=…` and `limit_per_input`.
- **Slow jobs:** Bright Data holds that request for up to 1 minute. If the job takes longer, it answers 202 with a `snapshot_id`. The gateway then polls `/progress/{id}` and downloads `/snapshot/{id}` once the job is ready, giving up after 10 minutes.
- **Rate limits:** on a 429, it waits for `Retry-After`, or backs off 2, 4, 8, 16 and 32 seconds, then stops. It never retries straight away, because Bright Data blocks an IP after 25 429s in 5 minutes.
- **Failed records:** anything Bright Data marks as failed (e.g. `dead_page`) goes into `errors`.

**Not yet verified against the live API:** we have no Bright Data key yet. The things a first live run could trip on are the search input values, where Bright Data's docs give examples but no list of allowed values:

- Reddit `date: "Past week"` and `sort_by: "Top"`
- TikTok `search_keyword`
- YouTube's `num_of_posts` as text

If one gets rejected, the 400 response names the field.
