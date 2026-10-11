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
| **Search** | Find this week's conversations and competitor content in the niche (Reddit, HN, X, YouTube, news; `recency_minutes`, `domain_type=news`), plus **TikTok `/video/` and IG `/reel/` URLs** (`include_domains`) to hand to Bright Data | It's the only primitive that discovers URLs we don't already have. Free, 1–3s. **Tested:** returns real TikTok and Reel URLs from the past 30 days, including a creator video about TinyFish. |
| **Fetch** | Bulk-read the ~30 URLs Search found as clean Markdown for the analyst | Known URLs with no interaction needed. Free, 10 URLs per call. The cheapest way to read at volume. |
| **Agent** | Work **YouTube Shorts search**: click Filters → This week → Sort by view count, then return the top Shorts as JSON (title, channel, views, age, URL) | Fetch gets only the page footer there (we tested it), and finding these needs goal-driven clicking. **Spike:** 3 min, $0.35. Runs take 3–6 min, so start them first and run them async. *Stretch:* TikTok Creative Center Top Ads through Vault/Profile login (it's login-gated, with only 4 ads visible without logging in). |
| **Browser** | Run a scripted Playwright session over CDP to capture screenshots and scroll-clips of the brand's product pages (video B-roll) and of reference content (evidence wall) | It's the only primitive that returns pixels, and it's deterministic at $0.002/min. Agent returns JSON and costs $0.016 per step. |
| **Vault** *(stretch)* | After approval, Publisher logs into the brand's own scheduler and saves a **draft** | It's the only way to give an agent a login without the credentials touching our code or the LLM. |

**Division of labor (user decision, 13:45):** TinyFish runs the main automation. **Bright Data** handles two things: sourcing IG Reels and TikTok, and generating personas.

**Data flow:**
```
STAGE 0  Product identity + PMF (user decision, 14:05)
  TinyFish Fetch + Browser ─► brand site: copy, real fonts/colors, screenshots ─► agent: identity.json ─► moodboard.png
  TinyFish Search + Fetch  ─► each candidate niche: news, Reddit/HN, pains, competitors, short videos
                           ─► agent: pmf.json (scored niches, hypothesis) ─► chosen_niche ─┐
                                                                                             ▼
TinyFish Search ─┬─ threads/news/blogs ──► TinyFish Fetch ──► pain points
                 └─ TikTok + Reel URLs ──► Bright Data ──► engagement + captions + top comments
TinyFish Agent (YouTube Shorts) ─────────────────────────► views and titles
                                    ↓
              Analyst: hooks and formats, weighted by engagement
              Personas: Bright Data comment clusters
                                    ↓
TinyFish Browser ──► brand B-roll ──► video ──► persona QA ──► revise ──► approve
```

**Escalation ladder (the README story):** Search → Fetch → Agent → Browser, cheapest first. If Agent gets blocked (CAPTCHA, empty result), the orchestrator falls back to Search with `include_domains` and Fetch, logs the failure, and keeps going. That is the PRD's "self-healing" requirement.

## 3. Architecture

Python with **uv**.

**Harness: Paperclip drives everything** (`./harness`, Docker, port 3100). It doesn't depend on one AI runtime: an agent can run on Claude Code or Codex. There are two kinds of agents:
- **Reasoning agents** run on Paperclip's `claude_local` (Claude Code) or `codex_local` (Codex) adapter.
  - Each agent's model is chosen in Paperclip, in its adapter `model` setting.
  - Credentials come from Paperclip **AI Connections**: an API key, or a Claude or ChatGPT subscription.
  - Switching models is a harness setting, not a code change.
- **Tool steps** run as Paperclip `process` agents (`uv run gtm agent <role>`, cwd `/workspace/app`), or as CLIs that the reasoning agents call.
  - The adapter injects `PAPERCLIP_API_URL` and `PAPERCLIP_API_KEY`.
  - A per-agent `env` can reference Paperclip vault secrets (`secret_ref`), so the TinyFish and Bright Data keys live in the harness instead of in `.env` files.
- Agents are configured through the API (`harness/bootstrap.py`), not the UI.

**Fallback:** `gtm/harness.py`, an in-process orchestrator with the same concepts, so the demo still runs if the Paperclip integration slips. It provides:

- **Org chart:** each agent has a role and a boss.
- **Tickets:** one owner each, with a lock.
- **Budgets per agent:** TinyFish $ plus LLM tokens. Warning at 80%, hard stop at 100%.
- **Approval gate** before publishing: `pending → approved | rejected | revise`.
- **Activity log:** JSONL, streamed to the dashboard.

**Models: chosen in the harness, not in code** (user decision, 13:50). This replaces the earlier "LLM: OpenAI" setup.
- **No hardcoded vendor or model.** No tool in `app/`, `brightdata/` or `video/` hardcodes an LLM vendor or model. The reasoning (analysis, pattern mining, strategy and scripts, persona QA, compliance) happens in the harness agents, on whatever model each agent is set to.
- **Tools are CLIs.** Inputs come in as flags. Big outputs go to `runs/<campaign>/`, and stdout gets one JSON line. Usage is documented in a plain-markdown `SKILL.md` that works on Claude Code and Codex, with no slash commands and no MCP-only paths. `brightdata/` already works this way.
- **Structured output.** The Pydantic schemas stay in `app/` as validators. Reasoning agents write the JSON files (`script_vN.json`, `qa_vN.json`, ...), and a tool step validates each one before the next stage.
- **If a Python step truly needs an LLM call,** it goes through one small adapter selected by `GTM_LLM_PROVIDER` + `GTM_LLM_MODEL`. Those are set in that agent's `env` in Paperclip, and the key comes from a vault `secret_ref`.
- **The borrowed key goes away.** We stop using the OpenAI key from the work project; a Claude or ChatGPT subscription can be signed in through AI Connections instead.
- **Runtime support.** The harness image ships the Claude Code CLI. `codex_local` needs the Codex CLI added to the image (harness session).

**Reels + TikTok sourcing and personas: Bright Data** (`brightdata/`, built by another session). It scrapes the TikTok and Reel URLs that TinyFish Search found, returning views, likes, shares, captions, durations and top comments. Those engagement numbers rank the hooks and formats. The comments, clustered and weighted by likes, generate the 3 synthetic personas, and each persona trait cites its source comments.
- Call: `bd-gateway sample --campaign <id> --platform tiktok|instagram --urls-file runs/<id>/search_urls.txt`
- Output: `runs/<id>/social_<platform>.json`
- **Positioning:** Bright Data competes with TinyFish on web data. It's a supporting data source here: the TinyFish primitives keep their unique jobs, and the launch post doesn't lean on it.

**Agents** (each one is a Paperclip agent; **R** = reasoning agent on Claude Code or Codex, **T** = tool step with no LLM inside):

1. **Orchestrator (R):** plans the run, assigns tickets, enforces budgets.
1b. **Product Identity & PMF (R + `identity/` tools):** runs first. `identity collect` reads the brand site with TinyFish Fetch + Browser. The agent writes `identity.json` (what it really is, audience, voice, visual), and `identity moodboard` renders `moodboard.png`. Then `identity market` scans each candidate niche with Search + Fetch, and the agent writes `pmf.json` (scored niches, chosen niche, hypothesis). Research uses `chosen_niche`, and strategy uses the voice, audience and cited claims. The procedure is in `identity/SKILL.md`.
2. **Trend Researcher (T):** Search + Fetch + Agent → `evidence.json`. It also passes the TikTok and Reel URLs to Bright Data (`bd-gateway`), which writes `social_<platform>.json`.
3. **Trend Analyst (R):** clusters topics, hooks and formats. A tool renders the charts.
4. **Pattern Miner (R):** produces a template (hook pattern, beats, length, caption style, CTA), with each element citing evidence.
5. **Creative Strategist (R):** picks the concept, audience and message, then writes `script_vN.json`. Every claim must cite either fetched evidence or a brand page.
6. **Video Creator (T):** Browser captures + TTS + MoviePy → `video_vN.mp4`.
7. **Persona QA ×3 + Compliance Reviewer (R):** run Cresta-style must-have/nice-to-have pass/fail checks on sampled frames plus the transcript, using the agent's own model for the images.
8. **Publisher (T):** simulated. Produces the post copy, video and suggested slot, then marks it "ready to publish".
9. **Self-Improvement (R):** writes failure types and winning hooks to `memory/learnings.json`, which gets injected into the next run.

**Video stack:**
- **Compositing:** MoviePy 2.x (pinned; v2 changed its API), 1080×1920, ≤30s.
- **Visuals:** Browser screenshots with a slow pan, a hook title card, and burned-in 3-word captions.
- **Voiceover:** the provider is chosen by `GTM_TTS_PROVIDER` (`openai` / `elevenlabs` / `say`), set in the Video agent's `env` in Paperclip. The `openai` option uses `gpt-4o-mini-tts`, with `whisper-1` word timestamps driving caption sync. Offline fallback: macOS `say`, with caption timing proportional to word length.
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
- **LLM:** billed to whichever AI Connection each agent uses (a subscription or an API key). Spike latencies on OpenAI: analysis 12s, script 19s, each persona review 15s, TTS 5s, word timestamps 2s.
- **Bright Data:** free tier is 5,000 credits/month. Keep samples small.

## 7. Risks

| Risk | Mitigation |
|---|---|
| Agent blocked on Creative Center (CAPTCHAs can't be solved) | Spike it first. The fallback source is already chosen, and the escalation ladder handles it at runtime. |
| The script runs longer than the target (the spike's VO came out at 32.6s against a 25s ask) | Compliance gives length a hard must-have, measured on the real TTS duration. |
| Platform terms (TikTok/Meta restrict automated extraction) | Keep samples small and public. Reddit is the default. Note this in the README. |
| The iMessage channel is experimental, and the Photon Free plan may not support DMs | Demo the same approve flow over the AgentMail channel or the Paperclip UI. |
| No time for polish | Cut list, in order: Vault, AI B-roll, Monitors, extra personas, dashboard styling. |
| Flaky live run during recording | Record from the frozen successful run. The dashboard can replay `runs/<id>`. |

## 8. Parallel track and out of scope

- **Channels: Paperclip's built-in connectors, not separate services** (user decision, 13:55). Messages reach the harness agents directly, so there's no bridge and no LLM loop of our own.
  - **iMessage:** Paperclip's `imessage-photon` channel binds the Photon project to a harness agent (the orchestrator by default). Each conversation becomes a Paperclip task, answered by that agent on its configured model.
    - `photon/` is now only the setup script (`connect_paperclip.py`). Its own OpenAI reply code is gone.
    - The channel is experimental: it needs the chat-connectors setting turned on.
    - Paperclip's docs name Photon's Pro plan for DMs, and the project is on Free.
  - **Email:** Paperclip's built-in AgentMail channel. Paperclip creates the inbox, stores the key in its vault, and turns each email thread into a task. The scripts in `agentmail/` aren't needed at runtime.

**Ports and directories** (to avoid stepping on the parallel sessions):

| Owner | Directories | Ports |
|---|---|---|
| This plan | `app/` | Streamlit 8501, FastAPI 8000 |
| Paperclip session | `paperclip/`, `harness/` | 3100 |
| Photon session | `photon/` (setup script for the harness channel only) | none |
| Bright Data session | `brightdata/` (CLI + `SKILL.md`) | none |
| Video session | `video/` | none |

**Out of scope today (roadmap in the README):**
- Real publishing and engagement ingestion
- Growth Analyst on real metrics
- TinyFish Search Monitors for a daily trend feed

## 9. Need from you

1. Confirm the target: **TinyFish** (recommended) or another brand.
2. A `BRIGHTDATA_API_KEY` in `brightdata/.env`.
3. Vault: do you have a TikTok for Business login (for Creative Center) and a 1Password service account? If not, Vault stays on the roadmap and Agent uses YouTube.
4. In Paperclip, connect a model account for the reasoning agents: a Claude or ChatGPT subscription, or an API key (Connectors → AI).
5. An AgentMail API key, entered in Paperclip's AgentMail connector rather than a `.env` file.
6. Photon: add the phone number, and check whether the Free plan works with Paperclip's iMessage channel (otherwise upgrade to Pro, or demo over email).
