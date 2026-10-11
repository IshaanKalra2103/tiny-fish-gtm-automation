# CURRENT — work log

Read this first before doing anything. Latest entries at the top.

## 2026-10-11 13:20: Video generation agent (`./video/`, session tiny-fish-gtm-automation-78), in progress

**Owns:** `./video/` (uv package `vidgen`) and the user-scope Vizard MCP connection. No ports.

- Vizard MCP is added at user scope (`https://mcp.agent.vizard.ai/mcp`) and signed in. Its tools load in new Claude Code sessions only.
- ElevenLabs key comes from the macOS Keychain (service `ELEVENLABS_API_KEY`, account `ishaankalra`), voice `miles` from `ELEVENLABS_VOICE_MILES`. Starter tier, about 18k characters left this cycle, so keep test scripts short.
- Building: ElevenLabs TTS with word timings, Bing/DDG image acquisition, gameplay acquisition via yt-dlp, ffmpeg + Pillow renderer for brainrot / story / slideshow / listicle formats.

## 2026-10-11 13:09: Bright Data gateway (`./brightdata/`, session ishaankalra-d8)

**What it is:** `BrightDataGateway`, a uv package (`bd_gateway`) plus the CLI `bd-gateway`. It gets TikTok, Instagram Reels, YouTube and Reddit posts with views, likes, shares, saves, length, sound, hashtags and creator follower count, plus the top comments under them. It's for trend analysis and for grounding the QA personas (`docs/brightdata.md`). Full details are in `brightdata/README.md`.

**For the harness (4d):**
- Command: `uv run --project /workspace/brightdata bd-gateway sample --campaign <id> --platform tiktok|instagram|youtube|reddit --keyword|--hashtag|--from-url|--urls-file ...`
- It writes `/workspace/runs/<id>/social_<platform>.json` and prints one JSON line (`ok`, `path`, counts, medians). On failure it prints `ok: false` and exits 1.
- It needs `BRIGHTDATA_API_KEY` in `brightdata/.env`, which is gitignored and visible in the container through the `/workspace` mount.

**For app/:**
- Install with `uv add --editable ../brightdata`, then `from bd_gateway import BrightDataGateway`.
- Instagram has no keyword search in Bright Data. Pass reel URLs from TinyFish Search with `urls=`. URLs from other sites are skipped automatically.

**Status**
- 12 offline tests pass (`uv run pytest`).
- **Not run against the live API yet: there's no Bright Data key.** The search input values (Reddit `date`/`sort_by`, TikTok `search_keyword`) are taken from Bright Data's documented examples, since the docs don't list the allowed values.
- `.gitignore` now also ignores `runs/` at the root, because that's where `org.yaml` puts shared memory.

## 2026-10-11 12:58: Git repo + root README (session ishaankalra-d8)

**Done**
- The project root is now one git repo (branch `main`), pushed to a **private** GitHub repo: https://github.com/IshaanKalra2103/tiny-fish-gtm-automation
- The root `.gitignore` excludes:
  - all `.env` / `.env.*` files (`.env.example` is still allowed)
  - `.venv`, `node_modules`, `__pycache__`
  - `paperclip/` (the upstream clone; reference only)
  - `app/runs/` (to commit the frozen demo run, use `git add -f`)
  - `.claude/`
- Wrote the root `README.md`: what it does, who it's for, the primitive → job → why table, cost and limits, run commands and repo layout. Facts are checked against docs.tinyfish.ai and tinyfish.ai/pricing.
  - Sections marked *(planned)* still need updating from the real run, especially the run commands and cost per run.

**For other sessions**
- Don't `git init` inside a subfolder. Commit your own directory from the root.
- Never commit `.env`. Run `git status` first.

## 2026-10-11 12:55: Paperclip harness in Docker (`./harness/`, `./paperclip/`), session 4d

**Goal:** Run Paperclip (the "AI GTM Automation Harness" box in the diagram) in Docker, with the GTM org set up in it: agent hierarchy, tasks, approvals, budgets, shared memory. Other services are out of scope for this session.

**Done**
- Cloned `paperclipai/paperclip` to `./paperclip` (master `2223b7d`). It's reference/source only; nothing runs from it.
- The upstream image `ghcr.io/paperclipai/paperclip:latest` (1.8 GB) is unusable from here: ghcr blobs download at ~100 KB/s, and Docker Hub/npm are much faster. A source build compiles Rust (20+ min).
- So `harness/Dockerfile` is a slim image: `node:24-trixie-slim` + `npm i -g paperclipai@2026.1005.0` (latest stable) + Claude Code CLI + uv. It uses upstream's entrypoint (`harness/docker/docker-entrypoint.sh`).
- `harness/docker-compose.yml` sets up:
  - container `gtm-paperclip`, port **3100**, `authenticated/private`, bind lan
  - named volume `paperclip-data` (holds the embedded Postgres)
  - project root mounted at `/workspace`, so process-adapter agents can `uv run` `./app` (`UV_PROJECT_ENVIRONMENT` is container-local, so the host `.venv` stays untouched)

**In progress**
- Image build
- Bootstrap script to create the admin, a board API key, and the GTM company + agents via the API

**Interfaces for other sessions** (filled in once verified)
- API base: `http://localhost:3100/api`. From other containers: `http://host.docker.internal:3100/api`.

## 2026-10-11 13:10: AgentMail throwaway inboxes, usable from the harness (`./agentmail/`)

**Done**
- Signed into the AgentMail console in Dia with Google (`codingfrig12@gmail.com`; the passkey step was done by the user). Org is "Ishaan's Organization", Free Tier.
- API key `tiny-fish-gtm-automation` (org scope, full access) is in `agentmail/.env` (chmod 600, gitignored). An `AGENTMAIL_API_KEY` env var takes precedence over the file.
- Inboxes (3/3, all throwaway): **`funnyflower74@agentmail.to`**, **`eagerspring500@agentmail.to`**, **`youngmirror648@agentmail.to`**. Deleted at the user's request: `tinyfish-gtm@` and the old `furrow-hermes@`.
- **`agentmail/inbox.py`** is a uv script with inline deps plus `inbox.py.lock`. It replaces `create_inbox.py` and the uv project. Subcommands: `list`, `create`, `delete`, `messages`, `read`, `wait`, `send`. Output is JSON lines. `read` and `wait` add `codes` and `links` for sign-up verification.
  - Harness: `uv run /workspace/agentmail/inbox.py <cmd>` from any cwd. Because it's a script, uv ignores `UV_PROJECT_ENVIRONMENT=/paperclip/venvs/app` and doesn't re-sync app's venv.
  - Verified in a `node:24-trixie-slim` + uv container as uid 1000, with the repo mounted at `/workspace` and that env var set. It read `.env` through the Colima mount (shown as owned by `node`), listed inboxes, and left `/paperclip/venvs/app` untouched.
  - Verified the end-to-end `wait` flow: sent funnyflower74 → eagerspring500, and `wait --subject verify` returned the code and verify link.
- **`agentmail/SKILL.md`** (skill `throwaway-inbox`, markdown only) teaches the harness's Claude agents to use the CLI. It still needs adding to the Paperclip company library (Skills Store, local/in-app).
- SDK gotcha: `agentmail` reads `AGENTMAIL_API_KEY` when it's imported, so pass `api_key=` explicitly after `load_dotenv`.
- Paperclip also has a **native AgentMail connection** (Connectors → AgentMail, since v2026.916). Each inbox maps to one agent, incoming mail becomes tasks, and the key is held in Paperclip's vault. It's not set up. With the free tier full it can only attach existing inboxes. The CLI suits throwaway sign-ups better.

**Browser-harness note:** several sessions share Dia. Use a named daemon (`BU_NAME=<yours> browser-harness`) and only touch tabs you opened. This session uses `BU_NAME=agentmail`.

**Owns:** `./agentmail/` (changes not committed yet)

## 2026-10-11 13:00: Demo-flow spikes (app/ session)

The spike code is throwaway and lives in the session scratchpad, not the repo. Results per step:

| Step | Result |
|---|---|
| **Search** (SDK `client.search.query`, MCP) | ✅ 1–3s. Fresh, relevant results: r/AI_Agents, HN, news, YouTube Shorts. Pain points found: "agents get stuck / burn tokens / CAPTCHAs". |
| **Fetch** (`client.fetch.get_contents`) | ✅ Reddit returns full thread and comment text (no upvote counts). ❌ YouTube Shorts returns only the footer, so it needs Agent or Browser. |
| **Browser** (session + raw CDP via Node WebSocket) | ✅ About 18s for 4 vertical 1080×1920 screenshots of tinyfish.ai. Good as B-roll. The Python SDK only has `browser.sessions.create`; closing a session needs REST `DELETE`. |
| **Video** (MoviePy 2.2.1 + `say` + screenshots) | ✅ 15s 9:16 h264/aac video rendered in 48s. Two fixes needed: captions get clipped at the bottom and sit on busy backgrounds (add a caption box and margin); the hook card overlaps the site headline (add a backing panel). Homebrew ffmpeg has no `drawtext`, so text is rendered with Pillow through MoviePy. |
| **Agent**, TikTok Creative Center Top Ads (stealth + US proxy) | ⚠️ 5.6 min, 32 steps (~$0.51). Region and period filters applied fine, but Top Ads is **login-gated**: only 4 generic ads and a "Log in to access all Top Ads" wall. Fix: log in through a Browser Profile + Vault, which makes Vault a core primitive. |
| **Agent**, YouTube Shorts search | ⚠️ 3.1 min, 22 steps (~$0.35). Returned 8 Shorts with views and URLs (Fetch only gets the page footer there, so this really is an Agent-only job). Two problems: my `sp` filter param was double-encoded, so "this week" wasn't applied (every result was 10 months old, with low views); and channel names look unreliable. Fix: have Agent click Filters → This week → View count itself, and cross-check the results. |
| **LLM steps** (OpenAI) | ✅ Live Search+Fetch evidence fed `gpt-6-luna` (analysis + template, 12s), then `gpt-6.1-sol` (script with cited claims, 19s), then 3× `gpt-6-luna` persona QA on 8 frames + transcript (15s each). **All 3 personas failed v1** on caption legibility and claim credibility, which is a natural revise-loop trigger. TTS `gpt-4o-mini-tts` took 5s and `whisper-1` word timestamps 2s. The script came out at 32.6s, over its 25s ask, so enforce length. |

**OpenAI key:** source `~/Documents/work/NatCap/sentra/pipeline-1/.env` (per the user: source it, don't read or copy it) and set `OPENAI_BASE_URL=https://us.api.openai.com/v1`. Without that base URL the key returns 401 `incorrect_hostname`. The keychain key (`OPENAI_API_KEY`/`OPENAI_PERSONAL`) returns 429 `credit_balance_exhausted`.

**User decision (13:45):** TinyFish runs the main automation. Bright Data does IG Reels and TikTok sourcing and persona generation.
- TinyFish Search with `include_domains=tiktok.com|instagram.com` returns real `/video/` and `/reel/` URLs (tested). Those URLs go to `bd-gateway`.
- Agent's source is now YouTube Shorts. Creative Center + Vault is a stretch goal.
- The data flow is in `plan.md` §2.

**Paperclip contract (from 4d, 13:40):**
- **Entry point:** `uv run gtm agent <role>` must be a `[project.scripts]` entry point, because the harness spawns it without a shell.
- **Plumbing:** vendor `harness/paperclip_agent.py` into `app/gtm/`.
- **Each role must:**
  1. checkout its issue
  2. work
  3. PATCH it to `done` with a comment, or to `blocked`
- **Run id:** the root campaign issue's identifier (e.g. `GTM-1`), which sets the `runs/GTM-1/` folder.
- **Publishing:** goes through `request_board_approval`.
- I told 4d the LLM is now OpenAI (`OPENAI_API_KEY` + `OPENAI_BASE_URL`), and that the user decides how the key reaches the container.

**Bright Data:** `brightdata/` (another session) collects IG/TikTok/YouTube/Reddit posts and comments with engagement counts and writes `runs/<campaign>/social_<platform>.json` at the project root, so `app/` uses root `runs/` too. There's no `brightdata/.env` yet, so it hasn't been tested live.

**Other findings**
- The TinyFish wallet has **$28**, not $8.
- SDK `tinyfish` 0.9.0 has `search`, `fetch`, `agent` (`run`/`stream`/`queue`), `browser.sessions`, `vault`, `wallet` and `runs`.
- PyPI downloads run at about 120 KB/s on this network, so a first `uv sync` of moviepy plus playwright takes about 8 minutes.
- Agreed with the Paperclip session (4d): its process agents call `uv run gtm agent <role>`, cwd `/workspace/app`, with roles research, analysis, strategy, video, qa, publish and learn. I asked 4d to add `espeak-ng` and `fonts-dejavu-core` to the container.

## 2026-10-11 12:40: Planning done (`plan.md`)

**Done**
- Read `docs/gtm.md` (PRD) and `docs/deliverable.md` (graded brief, due **3:30 PM PDT today**).
- Researched TinyFish primitives, Paperclip, Photon, Cresta, and the video stack. Wrote `plan.md`.
- Key decisions:
  - Build one complete loop: trend → template → video → persona QA → revise → approve.
  - Target: TinyFish itself (not yet confirmed by the user).
  - Primitives: Search (discover), Fetch (bulk read), Agent (TikTok Creative Center filters), Browser (pixel capture for B-roll). Vault is a stretch goal.
  - Borrow Paperclip's concepts instead of running inside it. Stack is Python/uv, Streamlit and MoviePy.
- Environment check:
  - Installed: uv 0.8.4, Python 3.14, ffmpeg, node.
  - `TINYFISH_API_KEY` is set. `ANTHROPIC_API_KEY` is **not set**.
- Live Fetch test results:
  - Reddit works.
  - TikTok Creative Center comes back as an empty shell, so it needs Agent.
  - Meta Ad Library returns 403. LinkedIn returns 999.

**Owns:** `./app/` (Python/uv pipeline and dashboard). Ports: Streamlit 8501, FastAPI 8000. Agents will be `uv run` entrypoints so the Paperclip session can call them through its `process` adapter.

**Blocked on**
- `ANTHROPIC_API_KEY`
- The user confirming the target brand

**Next**
- Follow the timeline in `plan.md` §4. First step: scaffold `app/` with uv, then spike Agent on TikTok Creative Center and Browser over CDP.

## 2026-10-11 — Photon (Spectrum) setup

**Goal:** Set up Photon (photon.codes, Spectrum SDK) as the iMessage/WhatsApp interface for the GTM agent (see `docs/gtm.md` §8).

**Owns:** `./photon/` (TS service), port 3200 (reserved for a webhook receiver; default gRPC streaming needs no port). Paperclip session owns `./paperclip/`, `./harness/`, port 3100.

**Docs version:** Stable (https://photon.codes/docs). Key contracts:
- SDK: `spectrum-ts` (TypeScript; Node.js or Bun). Cloud iMessage provider ships inside it: `spectrum-ts/providers/imessage`.
- Credentials: `PROJECT_ID` + `PROJECT_SECRET` in `photon/.env` (the scaffold's names; the SDK also reads `SPECTRUM_PROJECT_ID`/`SPECTRUM_PROJECT_SECRET`). Never echo `.env`.
- CLI: `@photon-ai/cli` (`npx -y @photon-ai/cli@latest whoami`, `projects secret --project <id> --json`)
- REST API: `https://spectrum.photon.codes` (HTTP Basic with project ID/secret)
- `terminal` provider works without credentials, useful for local testing.

**Photon project (already exists in the user's account)**
- Name `gtm-automation`, Free plan, id `e1b0dff2-3fe4-4ffd-9867-4c4f407738bb`
- Dashboard: https://app.photon.codes/dashboard/e1b0dff2-3fe4-4ffd-9867-4c4f407738bb
- The Get started page has iMessage selected as the first platform.

**Done**
- Read the Stable quickstart and iMessage provider docs.
- Dia remote debugging is enabled (CDP port 9222). browser-harness drives Dia; the user is signed in to app.photon.codes.
- Photon CLI is logged in (device flow, profile `developer`).
- Scaffolded `photon/` with `create-spectrum-project@0.9.0` (spectrum-ts ^12.10.1, imessage provider, npm, no git). `photon/.env` holds `PROJECT_ID`/`PROJECT_SECRET` (gitignored; don't echo it).
- Fixed: the template assumes bun, which auto-loads `.env`. Under npm/tsx it doesn't, so `npm start` failed with "Cloud iMessage requires projectId and projectSecret". Scripts now use `tsx --env-file=.env`.
- `npm start` runs: "Spectrum started", provider imessage. The echo loop replies `echo: <text>`.
- CLI state: platform `imessage` is on. 0 lines and 0 users. On Free/Pro, lines come from a **shared pool**: each enrolled user is routed through a pool number, there are no groups, and the number may differ per recipient. Quotas: 5k msgs/day per server, 50 new conversations/day per line.

**AI replies (13:20)**
- `photon/src/llm.ts` uses the OpenAI Responses API (`openai` 7.32). Model is `gpt-5.6-luna` (user pick) with reasoning effort `none`, falling back to the model default if that is rejected (unverified while there are no credits). Override with `OPENAI_MODEL`.
- The key comes from `OPENAI_API_KEY` if that's set. Otherwise it's read from the macOS Keychain at startup (`security find-generic-password -s OPENAI_API_KEY -a OPENAI_PERSONAL -w`). That's temporary at the user's request; it isn't stored in `.env`.
- `photon/src/index.ts`: per-conversation history (last 30 turns, in memory). It marks the message read, shows typing, and sends up to 3 short texts. The persona is casual iMessage style; it admits being an AI if sincerely asked and won't claim GTM actions that aren't wired yet. On an OpenAI error it sends "sorry, having trouble replying right now".
- **Blocker:** the OpenAI account has **no credits** (`You have no credits remaining`). The key itself is valid (it lists GPT-5.x models). Replies fall back until the user adds credits at https://platform.openai.com/settings/organization/billing/

**Enrolled (13:05)**
- The user is enrolled as Spectrum user "Ish K" (owner, shared pool). Their texts go to the pool line **+1 (415) 225-0168**.
- Restarted the app so it picks up the enrollment. `src/index.ts` now logs `[in]`/`[out]` per message, without content or sender.
- Waiting on: the user texts the line and gets an `echo:` reply back.
- Note: browser-harness `new_tab()` in Dia opens in a different browser context that isn't logged in to Photon. Use the user's existing Photon tab (`switch_tab`) to read dashboard state.

**Next**
1. Once the phone is added: refresh Get started, text the line, confirm the `echo:` reply. `npx -y @photon-ai/cli@latest spectrum users list --project <id>` should then show the user.
2. Replace the echo loop with GTM commands (create campaign / status / approve) that forward to the Paperclip harness on :3100.

**Run:** `cd photon && npm start` (or `npm run dev` for watch mode).

**Browser:** this session now uses `BU_NAME=photon browser-harness` and only touches tabs it opened. Early on it used the default daemon, and its device-login navigation landed in the AgentMail session's tab FD14713B.
