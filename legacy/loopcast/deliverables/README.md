# Loopcast

You give it a brand URL and a niche. It:

1. finds what's being said and posted about that niche this week
2. works out the short-video format that's winning
3. renders a 9:16 video about your brand in that format
4. has three synthetic audience personas plus a compliance check critique it
5. rewrites and re-renders until the draft passes
6. stops at a human approval gate (posting is simulated)

What it learned is saved for the next run.

All of the web work runs on **live TinyFish primitives**: Search, Fetch, Agent and Browser. Each one handles the part of the job only it's suited for.

**Real target used in the demo:** [tinyfish.ai](https://www.tinyfish.ai/), niche "AI browser agents". The demo video shows this exact run.

## Who it's for

- **Growth marketers and content leads** who research trends by hand today (scrolling TikTok, Reels, Reddit and HN, then guessing at a format). This does the research, drafts the video and shows its evidence. A human still approves.
- **Developers** at hackathons and accelerators who want TinyFish primitives combined into a real job they can fork for their own brand.

## Which primitive does which job, and why

| Primitive | Job in this workflow | Why only this one fits |
|---|---|---|
| **Search** | Finds this week's threads (Reddit, HN, dev.to), news, and **TikTok `/video/` and Instagram `/reel/` URLs** in the niche, using `recency_minutes`, `domain_type=news` and `include_domains`. | It's the only primitive that discovers URLs you don't already have. Free, 1–3s per query. |
| **Fetch** | Reads the threads and the brand's own site as clean Markdown. Script claims may only cite these pages. | The URLs are already known and need no clicking. 10 URLs per call, JS rendered, free. It's the cheapest way to read a lot of pages. |
| **Agent** | Opens YouTube search, clicks **Filters → This week → Sort by view count**, and returns this week's top Shorts as JSON. | Fetch on YouTube returns only the page footer (tested). The data appears only after clicking, so it needs a goal-driven agent, not a reader. |
| **Browser** | Drives a remote browser over CDP and captures phone-sized (1080×1920) screenshots of the brand site as the video's B-roll. | We need exact, repeatable pixels, not an agent's JSON. That takes scripted control at $0.002/min instead of $0.016 per Agent step. |

**Bright Data** sits alongside TinyFish. It takes the TikTok and Reel URLs that TinyFish Search found and returns views, likes and top comments. The comments, weighted by likes, become the three QA personas. Without a Bright Data key, the personas are built from the threads Fetch read instead, and the dashboard says so.

**Cheapest tool first, self-healing:**
- Search and Fetch are free. Agent only runs where clicking is required. Browser only runs for pixels.
- If Agent comes back blocked or empty (TinyFish's `COMPLETED` only means the browser didn't crash), the run falls back to Search with `include_domains` and keeps going.
- If Browser fails, the video uses branded cards.

## What one run does

```
Search ─┬─ threads/news ───────► Fetch ──► pain points + citable sources
        └─ TikTok/Reel URLs ───► Bright Data ──► engagement + comments ──► 3 synthetic personas
Agent (YouTube filters) ─────────────────────► this week's top Shorts
        ▼
analysis: themes, hooks, reusable template ──► strategy: script with cited claims
Browser (brand screenshots) ──► video: TTS + word-timed captions + MoviePy ──► 9:16 MP4
        ▼
QA: 3 personas review 8 frames + transcript (must-have / nice-to-have)
    + compliance (≤30s, every claim cited, CTA, no hype words)
    ── fail ──► revise script ──► re-render  (up to 3 drafts, then a human)
    ── pass ──► publish package (captions + UTM links) ──► human approval ──► learnings for next run
```

## Run it

```bash
cp .env.example .env      # TINYFISH_API_KEY + an LLM key (GTM_LLM_PROVIDER=openai|anthropic)
uv sync
uv run gtm run --brand-url https://www.tinyfish.ai/ --niche "AI browser agents"
uv run gtm serve          # dashboard: http://localhost:8501/
uv run gtm approve <run-id>
```

**Notes:**
- `app.zip` includes `sample-run/`, the exact run shown in the demo. Open `sample-run/<id>/index.html` to see it without running anything.
- `brightdata/` is bundled. Add `BRIGHTDATA_API_KEY` to `brightdata/.env` to turn it on.
- Each role is also its own CLI (`uv run gtm agent research|analysis|strategy|video|qa|publish|learn`). That's how the Paperclip agent harness drives it. See `SKILL.md`.
- Every command prints one JSON line to stdout, and progress goes to stderr.

## This run's numbers (tinyfish-demo-1)

| | |
|---|---|
| Target | https://www.tinyfish.ai/ · niche "AI browser agents" |
| TinyFish Search | 4 queries → 8 threads, 10 news, 20 TikTok/Reel URLs |
| TinyFish Fetch | 1 batch call(s), 9 pages read as Markdown |
| TinyFish Agent | 8 YouTube Shorts via agent (16 steps, $0.26) |
| TinyFish Browser | 4 phone-framed screenshots ($0.015) |
| Bright Data | tiktok: not configured (personas fell back to Fetch threads), instagram: not configured (personas fell back to Fetch threads) |
| QA path | v1 5.3/10 → v2 5.7/10 → v3 5.7/10 (never passed, so it stopped at `needs_human`) |
| TinyFish spend | $0.27 |
| Wall-clock | 16.9 min (research 431s, analysis 91s, strategy 24s, video 60s, qa 410s) |

## Costs and limits

| | Price | Limit |
|---|---|---|
| Search, Fetch | free | Search 30 req/min. Fetch 150 URLs/min and 1,000/day. |
| Agent | $0.016 / step | 2 concurrent runs. A YouTube filter run takes 3–5 min. |
| Browser | $0.002 / min | 5 concurrent sessions |

- Each run is capped by `GTM_TINYFISH_BUDGET_USD` (default $1.50). Spend is logged per primitive, with a warning at 80% and a hard stop at 100%.
- LLM calls (analysis, script, persona QA, captions) are billed by your provider.

## Guardrails and honest limits

- **Nothing posts automatically.** Publishing is simulated and gated on a human.
- **Persona scores are simulations.** They come from aggregate public comments and are hypotheses, not audience validation. No usernames are kept.
- **Every script claim must cite a fetched page,** and compliance blocks any claim that doesn't.
- **Platform terms are respected.** Where a site blocks access (Meta Ad Library 403, LinkedIn 999), we use another source. TikTok Creative Center's Top Ads is login-gated (4 ads without login), so a Vault + Browser Profile login is on the roadmap rather than a workaround.
- **Known issue:** Playwright's `new_context` on a TinyFish Browser session gets closed by the remote browser, so we drive the session's own page over raw CDP (`cdp_shots.mjs`). One live re-capture today stalled during the CDP handshake, and the demo run reuses screenshots that the same TinyFish Browser code captured earlier the same day (logged in the run).
