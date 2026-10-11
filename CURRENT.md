# CURRENT — work log

Read this first before doing anything. Latest entries at the top.

## 2026-10-11 14:05: Paperclip harness LIVE on :3100 (`./harness/`), session 4d

**Status:** running and verified end to end. Container `gtm-paperclip` (healthy) runs paperclipai 2026.1005.0 in authenticated/private mode.

**Done**
- `harness/` (all mine):
  - `Dockerfile`: slim, node:24-trixie-slim + npm paperclipai + uv + espeak-ng/DejaVu
  - `docker-compose.yml`
  - `up.sh`: writes `.env` secrets, retrying build, waits for health
  - `bootstrap.py`: idempotent; sets up admin, board key, company, goal, project and 8 agents
  - `campaign.py`: new/status/approvals/approve/reject/revise
  - `paperclip_agent.py`: stdlib helper for process agents
  - `org.yaml`: org chart from the diagram, plus tools (bd-gateway, agentmail)
  - `README.md`
- Company **TinyFish GTM**, issue prefix `TIN-`. The GTM Orchestrator (CEO, claude_local) has 7 process agents reporting to it, each running `uv run gtm agent <research|analysis|strategy|video|qa|publish|learn>` with cwd `/workspace/app`.
- Smoke test passed on TIN-1. A process agent in the container went: assignment wake → uv run → found its issue via run context → checkout → comment → done. TINYFISH_API_KEY reached the child.
- `/usr/local/bin/uv` in the image is a wrapper that gives each project its own venv (`/paperclip/venvs/<project>`). Host `.venv` dirs are never touched.

**Integration (for other sessions)**
- UI/API: http://localhost:3100 (`/api`). From containers: http://host.docker.internal:3100/api.
- Admin login: `harness/state/admin.json`.
- `harness/state/integration.env` (gitignored): `PAPERCLIP_BOARD_API_KEY`, `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_BOARD_USER_ID`, `PAPERCLIP_AGENT_<ROLE>`.
- Launch a campaign: `uv run harness/campaign.py new --brand https://tinyfish.ai --niche "AI web agents"`. It creates 7 chained stage issues. Publish requests `request_board_approval`; a human approves with `campaign.py approve <approval|issue>`, in the UI, or over iMessage.

**Open**
- OPENAI_API_KEY isn't in the container yet. Waiting for the user's OK on `GTM_OPENAI_ENV_FILE=<path> ./up.sh` (reads only OPENAI_API_KEY/OPENAI_BASE_URL at launch, never copied).
- CEO (claude_local) has no Anthropic key. It needs ANTHROPIC_API_KEY, or a subscription connected under Apps → Connections, or a switch to codex_local.

**In progress: debloat (the user's request)**
- The current image is 2.96 GB. Keep-list from the other sessions:
  - adapters process, claude_local, codex_local
  - AI Connections, vault secret_ref, company skills
  - imessage-photon chat channel + chat-connectors setting
  - AgentMail channel
- Drop: other adapters (cursor/gemini/grok/kimi/hermes/openclaw/pi/opencode/http), discord/slack/teams/telegram/github chat adapters, Vercel, AWS, MCP gateway, runner/Dot, three.js, and the duplicate global Claude CLI.

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

- **Accounts (2026-10-11 13:20)**, credentials in `agentmail/.accounts.json` (gitignored, 600):
  - Instagram **`@agentlab.gtm.xhcq`** ("Agent Lab") on `funnyflower74@agentmail.to`: created. It's logged in, in a private Dia browser context.
  - TikTok on `eagerspring500@agentmail.to`: the email code was accepted, then TikTok refused the web sign-up ("continue on the TikTok app"). Finish it in the mobile app. Before the fix, TikTok's email autocomplete sent 2 codes to `eagerspring500@gmail.com` by mistake.
  - The workflow is saved as the skill **`agentmail/account-signup/SKILL.md`**, linked into `.claude/skills/account-signup`. It covers pacing, stopping at CAPTCHAs and security checks, and posting only via official APIs or a human pressing Post.
- **Open question for the user:** d8 says email should go through Paperclip's native AgentMail channel (plan.md §8). That conflicts with the inbox.py approach, and I'd already told 4d it could drop the connector. I've asked 4d to keep it until the user confirms.

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

## 2026-10-11 — Photon (Spectrum) setup (session tiny-fish-gtm-automation-4e)

**Owns:** `./photon/`. Port 3200 is no longer needed. Paperclip session owns `./paperclip/`, `./harness/` and port 3100.

**Current design (13:50, per user): the harness is the brain, and Photon is just the interface.**
- iMessage goes through **Paperclip's native `imessage-photon` chat channel**, bound to the **GTM Orchestrator** (4d agreed). It streams over gRPC, needs no public URL, and the shared allocation works on our Free project. Each conversation becomes a task for the Orchestrator, whose adapter is swappable (`claude_local`/`codex_local`). Approvals stay in Paperclip.
- `photon/connect_paperclip.py` (uv script, stdlib only, idempotent; prints one JSON line, never secrets):
  - Reads `harness/state/integration.env` (4d OK'd it) and `photon/.env`.
  - Calls: PATCH experimental `enableChatConnectors` → create endpoint → `photon/inspect` → `setup configure` (shared) → PATCH `communicationInstructions` (human iMessage style) → `setup verify`.
  - Manual step for now; 4d documents it in harness/README.
- The OpenAI code was removed from photon/ (llm.ts and the `openai` dep). `src/index.ts` is an echo smoke test only. **Stop it before connecting the channel**, or both reply.
- I gave 4d the debloat keep-list:
  - npm: `@photon-ai/advanced-imessage`, `@grpc/grpc-js`, `nice-grpc*`, `chat`, `sharp`
  - code: `services/photon/*`, chat-channels/sdk-runtime/native-runtime chat files
  - routes: chat-channels and experimental settings
  - UI: `/chat-identity/confirm` and `/apps/chat/:id/settings`
  - all migrations
- I sent all sessions model-agnostic guidance: JSON CLIs, plain-markdown SKILL.md, no vendor LLM hardcoding, tools resolve their own secrets.

**Photon project facts**
- `gtm-automation`, id `e1b0dff2-3fe4-4ffd-9867-4c4f407738bb`, Free plan (shared pool, 10 users, no groups). Dashboard: https://app.photon.codes/dashboard/e1b0dff2-3fe4-4ffd-9867-4c4f407738bb
- The user is enrolled as "Ish K" (owner). Their line is **+1 (415) 225-0168**.
- The Photon CLI is logged in. `photon/.env` holds PROJECT_ID/PROJECT_SECRET (gitignored).
- Fixed: the scaffold assumes bun, which auto-loads `.env`. Under npm the scripts now use `tsx --env-file=.env`.

**Live (14:00)**
- Paperclip channel bound: endpoint `08410dbf-0cee-47bd-bc0f-6cfda743f0d1`, `imessage-photon`, shared, assigned to the GTM Orchestrator (`ce14a59f…`). Status is `verifying`, step `test` ("Waiting for a test conversation"). The echo app is stopped.
- Gotcha: `communicationInstructions` is Slack-only (422). I sent the iMessage reply-style text to 4d for the Orchestrator's bootstrap instructions.
- Commits: e41a5f4 (native channel, OpenAI code removed), 2abe38d (script fixes).

**Next**
1. The user texts **+1 (415) 225-0168**, gets an identity-confirm link, and opens it while signed in to Paperclip (login in `harness/state/admin.json`). Then they finish the test at http://localhost:3100/apps/chat/08410dbf-0cee-47bd-bc0f-6cfda743f0d1/settings
2. The round trip needs the Orchestrator's runtime auth (claude_local → Claude connection/ANTHROPIC_API_KEY, or codex_local → Codex login). I asked 4d for its state.
3. Re-check with `uv run photon/connect_paperclip.py --status`; expect status `active` and step `complete`.

**Browser:** use `BU_NAME=photon browser-harness` and only tabs this session opened. `new_tab()` lands in a Dia context that isn't logged in to Photon, so read dashboard state from the user's own Photon tab with `switch_tab`.
