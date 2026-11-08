---
name: bd-gateway
description: Collect public TikTok, Instagram Reels, YouTube or Reddit posts with engagement numbers (views, likes, shares, length, sound, hashtags) plus their top comments, through Bright Data. Use it for trend analysis of short-form video in a niche, and to gather audience comments for building synthetic QA personas. Works alongside TinyFish: pass it post URLs that TinyFish Search found.
---

# bd-gateway

A command-line tool. It writes the full sample to a file and prints one JSON line to stdout. It makes no LLM calls; the analysis and the personas are your job.

## Run it

From the harness container:

```bash
uv run --project /workspace/brightdata bd-gateway sample --campaign <campaign-id> --platform <platform> <how to find posts>
```

| Platform | How to find posts |
|---|---|
| `tiktok` | `--keyword "AI agents"` · `--hashtag aitools` · `--from-url <profile URL>` · `--urls-file <file>` |
| `instagram` (Reels) | `--from-url <profile URL>` · `--urls-file <file>` (no keyword search: get reel URLs from TinyFish Search with `include_domains=instagram.com`) |
| `youtube` | `--keyword` · `--hashtag` · `--from-url <channel URL>` · `--urls-file` |
| `reddit` | `--keyword` (past week, top) · `--from-url <subreddit URL>` · `--urls-file` |

`--urls-file` takes one URL per line. URLs from other sites are skipped, so you can pass a whole list of search results.

Optional flags:
- `--posts 10`: how many posts to collect.
- `--top 5`: read comments under this many of the top posts. `--top 0` skips comments and costs less.
- `--comments-per-post 20`

## Read the result

Stdout on success:

```json
{"ok": true, "path": "/workspace/runs/<id>/social_tiktok.json", "posts": 10, "comments": 92, "errors": 0, "median_views": 48000, "median_engagement_rate": 0.061, "seconds": 52.3}
```

On failure it prints `{"ok": false, "error": "..."}` and exits with code 1. Report the error on your task. Don't retry in a loop, because Bright Data blocks clients that hit its rate limit too often.

The file at `path` contains:
- `stats`: medians of views, likes, engagement rate and length; `top_hashtags`; `top_sounds`.
- `posts[]`: `url`, `text`, `views`, `likes`, `comments`, `shares`, `saves`, `duration_s`, `sound`, `hashtags`, `creator_followers`, `posted_at`, `engagement_rate`. Sorted by views.
- `comments[]`: `post_url`, `text`, `likes`, `replies`, `posted_at`. Sorted by likes.
- `errors[]`: inputs Bright Data couldn't collect.

## Using it well

- **Trend analysis:** compare hooks (the first line of `text`), `duration_s`, `sound` and `hashtags` across the posts with the highest `engagement_rate`, not only the highest views.
- **Personas:**
  1. Cluster `comments` into recurring wants, objections and questions, weighted by `likes`.
  2. Write at most 3 personas.
  3. Cite the 2–3 comments behind each trait.
  4. Label every persona "Synthetic persona, derived from aggregate public-content patterns". Persona scores are simulations, not audience validation.
- **Privacy:** never try to identify or profile individual commenters. The tool drops their identities on purpose.
- **Cost:** keep samples small (≤10 posts, `--top` ≤5). The key comes from the agent's environment or from `brightdata/.env`; never print it.

Other commands: `bd-gateway platforms` (dataset IDs and search modes) and `bd-gateway status <snapshot_id>`.
