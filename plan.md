# Plan: TinyFish Agent-Led Growth App

**Due:** today, Oct 11 2026, 3:30 PM PDT (~3h from 12:25). **Ship:** `tinyfish-growth-app.zip`.
**Source docs:** `docs/gtm.md` (PRD, the long-term vision), `docs/deliverable.md` (what gets graded).

## 1. Scope decision

The PRD describes a full GTM company. The deliverable grades four things: at least 3 TinyFish primitives, each doing a job only it can do; a real marketer workflow; a real target; and an end-to-end run. **We build one complete loop from the PRD and nothing more:**

> Brand URL + niche → find what's trending → learn the winning format → render a short video → 3 AI personas + compliance QA it → auto-revise → human approves → "ready to publish" → learnings saved for the next run.

**Target (recommended): TinyFish itself, niche "AI web agents / browser automation".** It's a real brand with live trends, and the output doubles as launch content Sky can actually use, which makes the strongest "wait, you can DO that?" story. *(Confirm, or name another brand.)*

## 2. Primitive → job → why only it

| Primitive | Job in the workflow | Why no other primitive fits |
|---|---|---|
| **Search** | Find this week's conversations and competitor content in the niche (Reddit, HN, X, YouTube, news; `recency_minutes`, `domain_type=news`) | It's the only primitive that discovers URLs we don't already have. Free, 1–3s. |
| **Fetch** | Bulk-read the ~30 URLs Search found as clean Markdown for the analyst | Known URLs with no interaction needed. Free, 10 URLs per call. The cheapest way to read at volume. |
| **Agent** | Work **TikTok Creative Center → Top Ads**: set region, industry and period filters, open ads, return JSON of hooks, formats, CTAs and lengths | Fetch only gets an empty page shell there (we tested it). The page needs goal-driven clicking and filtering. **Spike:** filters work, but the results are login-gated (4 ads without login), so this step needs Vault/Profile. **Fallback:** YouTube Shorts search, with Agent clicking Filters → This week → View count (also tested: Fetch gets only the page footer there; Agent took 3 min and $0.35). Agent runs take 3–6 min, so start them first and run them async alongside Search/Fetch/Browser. |
| **Browser** | Run a scripted Playwright session over CDP to capture screenshots and scroll-clips of the brand's product pages (video B-roll) and of reference content (evidence wall) | It's the only primitive that returns pixels, and it's deterministic at $0.002/min. Agent returns JSON and costs $0.016 per step. |
| **Vault** *(stretch)* | After approval, Publisher logs into the brand's own scheduler and saves a **draft** | It's the only way to give an agent a login without the credentials touching our code or the LLM. |

**Escalation ladder (the README story):** Search → Fetch → Agent → Browser, cheapest first. If Agent gets blocked (CAPTCHA, empty result), the orchestrator falls back to Search with `include_domains` and Fetch, logs the failure, and keeps going. That is the PRD's "self-healing" requirement.

## 3. Architecture

Python with **uv**.

**Harness: Paperclip.** A parallel session is running Paperclip in Docker (`./paperclip`, `./harness`, port 3100). Each of our agents is a standalone `uv run` entrypoint, so Paperclip's `process` adapter can call it. That adapter injects `PAPERCLIP_API_URL` and `PAPERCLIP_API_KEY`, and the adapter has to be configured through the API, not the UI.

**Fallback:** `gtm/harness.py`, an in-process orchestrator with the same concepts, so the demo still runs if the Paperclip integration slips. It provides:

- **Org chart:** each agent has a role and a boss.
- **Tickets:** one owner each, with a lock.
- **Budgets per agent:** TinyFish $ plus LLM tokens. Warning at 80%, hard stop at 100%.
- **Approval gate** before publishing: `pending → approved | rejected | revise`.
- **Activity log:** JSONL, streamed to the dashboard.

**LLM: OpenAI.** The key is sourced from `~/Documents/work/NatCap/sentra/pipeline-1/.env` (never read or copied). It's a US-residency project, so set `OPENAI_BASE_URL=https://us.api.openai.com/v1`. The keychain key (`OPENAI_API_KEY`/`OPENAI_PERSONAL`) has no credits.
- `gpt-6.1-sol` for strategy and scripts.
- `gpt-6-luna` for analysis and persona QA. It takes image input and is much cheaper.
- Structured output goes through `client.responses.parse(text_format=PydanticModel)`.

**Audience data: Bright Data** (`brightdata/`, built by another session). It returns public IG, TikTok, YouTube and Reddit posts plus top comments, *with engagement counts*. That data grounds the 3 personas in real audience reactions and ranks the trends. Search finds the URLs, then `bd-gateway` scrapes them.
- **Positioning:** Bright Data competes with TinyFish on web data. It's a supporting data source here: the TinyFish primitives keep their unique jobs, and the launch post doesn't lean on it.

**Agents (each a function plus an LLM prompt with a Pydantic schema):**

1. **Orchestrator:** plans the run, assigns tickets, enforces budgets.
2. **Trend Researcher:** Search + Fetch + Agent → `evidence.json`.
3. **Trend Analyst:** clusters topics, hooks and formats → charts.
4. **Pattern Miner:** produces a template (hook pattern, beats, length, caption style, CTA), with each element citing evidence.
5. **Creative Strategist:** picks the concept, audience and message, then writes `script.json`. Every claim must cite either fetched evidence or a brand page.
6. **Video Creator:** Browser captures + TTS + MoviePy → `video_vN.mp4`.
7. **Persona QA ×3 + Compliance Reviewer:** run Cresta-style must-have/nice-to-have pass/fail checks.
8. **Publisher:** simulated. Produces the post copy, video and suggested slot, then marks it "ready to publish".
9. **Self-Improvement:** writes failure types and winning hooks to `memory/learnings.json`, which gets injected into the next run.

**Video stack:**
- **Compositing:** MoviePy 2.x (pinned; v2 changed its API), 1080×1920, ≤30s.
- **Visuals:** Browser screenshots with a slow pan, a hook title card, and burned-in 3-word captions.
- **Voiceover:** OpenAI `gpt-4o-mini-tts`, with `whisper-1` word timestamps driving caption sync. Offline fallback: macOS `say`, with caption timing proportional to word length.
- **AI B-roll** (Gemini Omni Flash) is optional and off by default.
- **Avoid** Sora (API shut down Sep 24) and Veo 3.1 preview (shuts down Oct 22).

**QA:**
- Each check gets 8–12 sampled frames plus the transcript (image input, not video).
- Personas are built from the Bright Data comment clusters, weighted by likes, and each persona trait cites its source comments.
- **Must-haves:**
  - hook lands in the first 2s
  - CTA is present
  - every claim is supported by evidence
  - captions are legible
  - length is ≤30s
- **Pass rule:** every must-have passes for all personas, and the average score is ≥7.
- **If it fails:** send the feedback to the Strategist, re-render, and re-QA, at most twice. If it still fails, ask a human.
- Persona scores are labeled **simulated**, not real audience validation (PRD guardrail).

**UI:** Streamlit dashboard showing:
- run launcher
- trend charts (Plotly)
- evidence wall
- template card
- v1 → v2 video previews with QA scorecards
- activity log
- budget meters
- **Approve** button

**Layout (`app/`, which becomes `app.zip`):**
```
README.md  pyproject.toml  .env.example  dashboard.py
gtm/  tinyfish.py (wrappers + cost meter)  harness.py (org/tickets/budgets/approvals/log)
      agents/  video.py  qa.py  memory.py  cli.py
```
**Shared run folder:** `runs/<run_id>/` at the **project root**. It's shared with `brightdata/` and the Paperclip harness, and `GTM_RUNS_DIR` overrides the location. Each run folder holds:
```
evidence.json  social_<platform>.json  charts/  shots/  script_vN.json  video_vN.mp4  qa_vN.json  activity.jsonl
```
**Run:**
```
uv sync
uv run gtm run --brand https://tinyfish.ai --niche "AI web agents"
uv run streamlit run dashboard.py
```

## 4. Timeline (PDT)

| Time | Work |
|---|---|
| 12:30–12:50 | uv scaffold and TinyFish wrappers. **Spike: Agent on TikTok Creative Center** (if it's blocked, switch to YouTube Shorts search or Product Hunt). Spike: Browser CDP screenshot. Get the Anthropic key. |
| 12:50–13:50 | Pipeline end-to-end on the CLI: research → analyze → template → script → render → QA → revise → approve. |
| 13:50–14:25 | Dashboard, activity log, budget meters. |
| 14:25–14:45 | Full run on the target. Fix issues, then freeze that run's artifacts for the demo. |
| 14:45–15:10 | `README.md`, `launch-post.md`, record `demo-video.mp4` (same target, same run). |
| 15:10–15:20 | Package the zip. Test the run instructions from a clean unzip. |
| 15:20–15:30 | Buffer. |

## 5. Deliverables checklist

- [ ] `app.zip`: runnable, with run instructions in the README at the root, and `.env.example` (no secrets).
- [ ] `README.md`: what it does, who it's for, the primitive → job → why table, the escalation ladder, cost per run, and limits.
- [ ] `demo-video.mp4`: under 3 min. Shows each primitive firing, the v1 QA failure, v2 passing, and approval.
- [ ] `launch-post.md`: X or LinkedIn post in Sky's voice, using real numbers from the run (sources read, $ spent, minutes). Links carry **UTM tags** so Sky gets a first signup and activation baseline.
- [ ] `tinyfish-growth-app.zip` containing all four.

## 6. Budget and limits

- **TinyFish:** wallet has $28. Spikes so far cost about $0.87.
  - Search and Fetch are free: 30 req/min and 1,000 URLs/day.
  - Agent costs $0.016/step, with 2 runs at once.
  - Browser costs $0.002/min, with 5 sessions at once.
  - Cap: **$1 per run**. Total spend: under $5.
- **OpenAI:** expect under $1 per run. Spike step latencies: analysis 12s, script 19s, each persona review 15s, TTS 5s, word timestamps 2s.
- **Bright Data:** free tier is 5,000 credits/month. Keep samples small.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Agent blocked on Creative Center (CAPTCHAs can't be solved) | Spike it first. The fallback source is already chosen, and the escalation ladder handles it at runtime. |
| The script runs longer than the target (the spike's VO came out at 32.6s against a 25s ask) | Compliance gives length a hard must-have, measured on the real TTS duration. |
| Platform terms (TikTok/Meta restrict automated extraction) | Keep samples small and public. Reddit is the default. Note this in the README. |
| No time for polish | Cut list, in order: Vault, AI B-roll, Monitors, extra personas, dashboard styling. |
| Flaky live run during recording | Record from the frozen successful run. The dashboard can replay `runs/<id>`. |

## 8. Parallel track and out of scope

- **Photon iMessage (parallel track, see `CURRENT.md`).** The SDK is TypeScript only, so the plan is a small `bridge.ts` running `spectrum-ts` that POSTs to a FastAPI `/chat` endpoint. Supported commands: start a run, check status, approve. It only gets wired in if the core loop is done by 14:25.

**Ports and directories** (to avoid stepping on the parallel sessions):

| Owner | Directories | Ports |
|---|---|---|
| This plan | `app/` | Streamlit 8501, FastAPI 8000 |
| Paperclip session | `paperclip/`, `harness/` | 3100 |
| Photon session | `photon/` | 3200 |

**Out of scope today (roadmap in the README):**
- Real publishing and engagement ingestion
- Growth Analyst on real metrics
- TinyFish Search Monitors for a daily trend feed

## 9. Need from you

1. Confirm the target: **TinyFish** (recommended) or another brand.
2. A `BRIGHTDATA_API_KEY` in `brightdata/.env`.
3. Vault: do you have a TikTok for Business login (for Creative Center) and a 1Password service account? If not, Vault stays on the roadmap and Agent uses YouTube.
