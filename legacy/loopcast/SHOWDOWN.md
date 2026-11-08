# SHOWDOWN: end-to-end demo runs over iMessage

**Date:** 2026-10-11. **Operator:** Claude Code (session 6f).

**Goal:** drive the whole TinyFish growth loop from text messages, record everything, and list every gap found along the way.

## Recording

`recordings/e2e-session-20261011-141904.mkv` covers the whole session: 1 h 22 m, 1.0 GB, full screen, 1920 px wide, 15 fps, clicks visible. The folder is gitignored.

Ready-made run-2 cuts (stream copies, same quality):
- `recordings/run2-imessage.mkv`: from text #4 to the end.
- `recordings/run2-clean.mkv`: from text #7, i.e. the clean launch → rich UI → approval.

- Offsets like `+00:13:32` below are positions in that file. The raw log with every offset is `recordings/steps.log`.
- **Run 2** (the clean iMessage run) starts at **`+00:55:16`** (text #4). The cleanest stretch starts at **`+01:06:06`** (text #7). A dedicated second recorder failed to open a second screen capture at the same time, so run 2 is cut from the main file. See "Cutting the clips".

## Demo script (the user's)

1. Send an iMessage: "Find trending AI productivity content and make a reel."
2. TinyFish finds real examples and extracts the trend, hook and format.
3. A simple chart and three proposed content ideas.
4. One vertical video with captions.
5. Persona QA flags an issue, then the revised video passes.
6. Approve and publish to Instagram, or show the final posting step.

## Setup

| Piece | How |
|---|---|
| Texting | Mac **Messages**, same Apple ID, sending from the user's linked number to the Photon line **+1 (415) 225-0168** (`osascript … send … to chat id "any;-;+14152250168"`). The iPhone was connected through `phone-harness` at the start, but it dropped to "iPhone in Use", and the user chose Mac Messages. |
| Chat to agents | Paperclip's native `imessage-photon` channel makes each conversation a task (TIN-4) for the **GTM Orchestrator** (codex_local). |
| Pipeline | The campaign issue plus 7 chained stage issues. Process agents in `gtm-paperclip` run `uv run gtm agent <role>`. |
| Watching | `scratchpad/pipemon.py` (Paperclip issues, comments, runs, plus `~/Library/Messages/chat.db` read-only) streams every change. |
| Rate limits | 8 founder texts in 68 minutes. The shortest gap was 88 s and most were 2–30 min. Relay sends are spaced 3 s apart. TinyFish stayed under its 2-concurrent limit and spent ≈ $0.60, mostly on one Agent run (minimal mode uses no Agent). Two fal clips were rendered (≈ $1.30) before the user switched to free demo video. Nothing was posted publicly. |

## Run 1: TIN-5 (text #1 → QA verdict)

| Offset | What happened |
|---|---|
| +00:00:24 | Preflight: Paperclip healthy, Photon endpoint live, phone connected. **`campaign.py doctor` failed: `gtm` wasn't installed in the container venv.** Ran `uv sync --frozen` in the container, which took about 12 min at ~0.5 MB/s. |
| +00:02:13 | **Gap fixed:** analysis produced no "three content ideas". Added `Insights.ideas` (exactly 3); strategy now produces idea #1 and the dashboard shows the ideas. |
| +00:07:06 | **Gap:** the container had no `OPENAI_API_KEY`. The user approved recreating the container with `GTM_OPENAI_ENV_FILE` (no rebuild). |
| +00:13:32 | **Text #1:** "Find trending AI productivity content and make a reel." |
| +00:14:23 | **Critical gap:** the Orchestrator failed with `401 Incorrect API key`. A container-wide `OPENAI_API_KEY` overrides Codex's ChatGPT login, and the raw failure (`ACP agent reported a terminal service failure`) was texted to the user. |
| +00:15:09 | **Fixed:** compose now passes the key as `GTM_OPENAI_API_KEY`, and `app/src/gtm/config.py` maps it to `OPENAI_*` only inside workers. |
| +00:15:49 | **Fixed:** `up.sh` parsed the env file with grep/sed and kept an inline `# comment` as part of the key (OpenAI 401). It now sources the file in a subshell and keeps only the two variables. **Text #2** sent. |
| +00:17:34 | **Gap:** the Orchestrator had no launch command, so it spent about 4 minutes rediscovering the Paperclip API, with every shell call going through Codex Guardian review. |
| +00:19:38 | **Gap:** the CEO ran `gtm doctor` inside its own sandbox and concluded the credentials were missing, a false negative. It texted the user asking them to configure keys. **Text #3** said they were already configured. The CEO replied "sorry for the false alarm". |
| +00:20:04 | **Step 1 ✓.** Campaign TIN-5 created with 7 stages. **Gap:** the niche was left at the default "AI web agents / browser automation"; "AI productivity" only reached the audience and goal fields. |
| +00:22:27 | **Severe gap fixed:** research's `uv run --project brightdata bd-gateway` inherited `UV_PROJECT_ENVIRONMENT=/paperclip/venvs/app` and **synced Bright Data's dependencies over the app's venv** mid-run. tinyfish, openai and moviepy were uninstalled, Browser capture failed (`FileNotFoundError`: certifi's CA file was gone), and the Agent SDK's HTTP client broke. `research.py` now strips those variables. |
| +00:34:00 | **Gap:** the TinyFish Agent (YouTube filters) took 11 min and 49 steps and didn't apply the filters. The SDK then started a **duplicate** paid Agent run (non-idempotent retry), and research's `ThreadPoolExecutor` exit waited on it. **Operator:** cancelled the orphaned duplicate run. |
| +00:35:35 | Research hit Paperclip's 900 s timeout. **User: "keep research minimal."** Added `GTM_RESEARCH_MODE=minimal` as the default: no Agent, YouTube via Search, Bright Data capped at 5 posts and 180 s. The user supplied the **Bright Data key** (now in `brightdata/.env`, gitignored, mode 600). Board corrected the niche to "AI productivity". |
| +00:41:36 | **Gap:** `campaign.py retry` only sets the issue to `todo`. The timed-out agent stays in `error`, and Paperclip needs "execution reconciliation", so the wakeup is skipped. **Operator:** ran `gtm agent research --run TIN-5` in the container and marked TIN-6 done. |
| +00:44:53 | **Step 2 ✓** (3 m 05 s): TinyFish Search, Fetch and Browser (4 screenshots); Bright Data Instagram, 5 posts and 17 comments; 10 Shorts via Search. |
| +00:45:29 | **Gap:** the CEO created the stages as `backlog`, and **Paperclip never wakes backlog issues** when their blocker finishes. **Operator:** set them to `todo`, after which Paperclip drove analysis → strategy → video → QA unattended. |
| +00:46:31 | **Step 3 ✓:** 3 themes; template "Contrarian workflow fix"; 3 ideas ("Measure the task shipped, not the draft generated", "The AI productivity metric developers should actually watch", "One task, one tool, one honest test"); 3 personas grounded in 17 Bright Data comments. |
| +00:48:25 | **Step 4 ✓:** `video_v1.mp4`, 22 s, 1080×1920, vidgen UGC talking-head with bold captions. 4e switched `roles/video.py` to vidgen mid-run at the user's direction. |
| +00:49:38 | **Step 5a ✓ (QA flags):** v1 scored 4.7/10. Blockers: *product not shown* (3/3), *captions covering content* (2/3), *claims not backed* (2/3). **Gap:** revisions re-rendered the same talking-head, which can never show the product. Fixed: when QA blocks on the product, the revision becomes a **product ad on the TinyFish Browser screenshot**, and it stays that way. |
| +00:54:32 | **Step 5b ✗:** v2 scored 4.0 (product now shown, but captions, CTA and claims failed) and v3 scored 4.0. QA ended `needs_human`, and **the pipeline correctly refused to publish.** The persistent blocker, 3/3 on every draft, was vidgen's caption and badge layout. 4e has since moved captions into their own band. |

## Run 2: TIN-13 (the clean iMessage run)

| Offset | What happened |
|---|---|
| +00:55:16 | **Text #4.** The fixes are live: one-shot launch, `todo` stages, verbatim niche, no CEO credential self-check, minimal research. |
| +00:58:38 | **Blocked:** the Codex CEO hit the **ChatGPT usage limit**, and the failure was texted again. The user logged Codex into another account; the container's `auth.json` is a symlink to the host's, so no restart was needed. **Text #5.** |
| +01:02:22 | **Gap:** the new plan rejects the host default `gpt-6-astra` (400). Probed models with `codex exec`; at the user's request, pinned the **`gpt-5.6-luna`** model in `org.yaml`. Video default switched to **fal** (MiniMax text-to-video) at the user's direction. **Text #6.** |
| +01:05:10 | **Gap:** on luna, the CEO **ignored the launch rule** and hand-made a "reel package" (Codex imagegen cover plus a markdown script). It skipped research, QA and approval, and texted raw markdown plus a `.md` file. Fixed with a **HARD RULE** that content requests go only through the launcher, plus iMessage style rules: plain text, images and mp4 only. |
| +01:06:06 | **Text #7:** "Now run the full pipeline on it…" |
| +01:06:57 | **Step 1 ✓ in about 50 s:** the CEO ran the one-shot `campaign.py new` (agent mode), creating TIN-13 plus TIN-14…20, all `todo`, with niche "AI productivity reel" and the chat thread recorded in the brief. The phone got: *"Campaign TIN-13 is running with TinyFish research, persona QA, and the full Instagram reel pipeline. Publishing will wait for your explicit approval…"* |
| +01:07 → +01:13 | Paperclip drove research (≈3 min, minimal), analysis, strategy and video. **Browser capture worked**, which confirms the venv fix. Bright Data Instagram returned 5 posts and 27 comments. Ideas: "Let an agent do the tab-hopping price check" / "Turn repeated invoice lookups into one browser run" / "AI does the clicks; you check the answer". |
| +01:15 | QA, 3 drafts: v1 5.3 (fal talking-head; product shown), v2 4.3, v3 4.0 (Codex face image failed, out of credits → free product ad). **User: "don't focus on QA, demo results are fine."** QA became **advisory**: the best draft (v1) goes to approval with its flags. |
| +01:11 → +01:21 | **iMessage became the dashboard.** First as PNG cards; then, at the user's request (*"why aren't you using rich ui"*), as **native iMessage UI**. See below. |
| +01:21:55 | **Text #8: "APPROVE".** About 6 s later the relay recorded Paperclip approval `705623b3` for the founder and sent **confetti**: *"Approved. The reel is queued for Instagram (posting is simulated in this demo)."* Publish went to `ready_to_publish`, learning recorded 3 failure types, and **TIN-13 closed with all 8 issues done**. The CEO's own reply: *"Approved — the TinyFish reel is queued for posting (simulated)."* |

**Demo script vs run 2:**

| Step | Result |
|---|---|
| 1 | ✅ A text launched the campaign (one-shot launcher, about 50 s) and got a plain-text ack. |
| 2 | ✅ TinyFish Search, Fetch and Browser plus Bright Data. A rich link preview showed the top trending reel. |
| 3 | ✅ Trend/template plus **3 ideas as a native iMessage poll**. The chart lives in the card and dashboard. |
| 4 | ✅ A 22 s 1080×1920 captioned reel, **playable inline** in the thread. |
| 5 | ⚠️ QA flagged each draft and revisions ran, but no draft reached a pass score. Advisory mode moved the best draft forward, as the user asked. |
| 6 | ✅ An "Approve / Request changes" poll; an **APPROVE text → real Paperclip board approval → confetti**. Instagram posting is simulated (no Graph API account). |

## iMessage as the dashboard (native UI)

The user didn't want a web dashboard, so each stage now shows up in the chat thread as native iMessage UI:

| Stage done | What arrives on the phone |
|---|---|
| research | an **app-card bubble** (chart: top posts by likes; "Trend research", "8 threads · 20 posts · 10 Shorts", trailing "TinyFish"), plus a **rich link preview** of the top post |
| analysis | an **app card** (chart: theme strength; the winning pattern, "3 themes"), plus a **native Apple Poll** of the 3 ideas |
| video | "Draft vN (22s, vertical):" plus the **mp4 inline** |
| QA | an **app-card scorecard** per draft: persona score chart, overlay "5.3 / 10 · 3 synthetic personas", trailing **5.3/10**, subcaption with the flags (red bars below 7) |
| publish | the final caption plus a **poll: "Post it to Instagram?" Approve / Request changes** |
| approval | an APPROVE reply → Paperclip board approval → a **confetti** confirmation |

App cards are iMessage extension balloons (`customizedMiniApp`). Photon only allows its own Spectrum extension identity (`P8XT6232SL` / `codes.photon.Spectrum.MessagesExtension`), so the cards render through it. Chart images come from `gtm.cards.chart_*` as 1200×800 JPEGs in the same paper/ink style.

How it's built:
- **`photon/send_rich.mjs`** is a send-only Spectrum script supporting `--card card.json` (app-card bubble: caption, subcaption, trailing caption, image plus overlay), `--text [--effect confetti]`, `--link` (rich link), `--file` (inline media) and `--poll --option …` (native Apple Polls).
- **`harness/chat_relay.py`** is board-side and stdlib only; run a single instance with `python3 harness/chat_relay.py`. When a stage's card appears in `runs/<id>/cards/` (rendered by workers with `gtm.cards`), it sends that stage's native message to the number on the campaign's chat issue (`brief.chat_issue`, recorded by `campaign.py new` in agent mode). It also bridges an APPROVE reply into the board approval.
- **Why not Paperclip comments?**
  - Stage agents get 403 attaching files to the chat issue.
  - Paperclip only projects the chat-bound agent's comments; publishing anyone else's needs a board user.
  - A board publication delivered the text without the image.
  - Every comment on the chat issue wakes the Orchestrator, which costs Codex quota and adds an extra reply.
- **Earlier iterations**, all visible in the recording: PNG cards were sent through Paperclip (text only), then through Photon (worked, but the user found them too dashboard-like). Then a minimal paper/ink restyle. Then native UI.

## Gaps: status

| # | Gap | Status |
|---|---|---|
| 1 | Worker venv missing in the container after it was recreated | Fixed by sync; `up.sh` does it, but a manual `docker compose up` doesn't |
| 2 | No OpenAI key in the container | Fixed (`GTM_OPENAI_*`, user-approved) |
| 3 | Container-wide `OPENAI_API_KEY` breaks the codex_local CEO | **Fixed** |
| 4 | `up.sh` kept an inline `# comment` in the key | **Fixed** |
| 5 | CEO has no one-shot launch, so ~4 min per request | **Fixed**: `campaign.py new` in agent mode; ~50 s in run 2 |
| 6 | CEO credential self-check gives false negatives and texts the user | **Fixed** (instructions) |
| 7 | Niche not taken from the text | **Fixed** (instructions: verbatim `--niche`) |
| 8 | bd-gateway synced over the app venv | **Fixed** |
| 9 | Agent slow (11 min), duplicate paid run, executor blocks on it | Avoided by minimal mode. **Open** in full mode: cancel abandoned futures, idempotent Agent retry |
| 10 | Stages created as `backlog` are never woken | **Fixed** (`status: todo` in the launcher) |
| 11 | `retry` can't recover a timed-out stage (agent error plus execution reconciliation) | **Open**: needs clear-error plus Paperclip's reconciliation flow |
| 12 | Revisions can't change format, so "product not shown" can't be fixed | **Fixed** (product ad on revision, and it stays product) |
| 13 | vidgen captions and badge overlap the content (3/3 blocker on every draft) | Still flagged on run 2 (2/3); QA is now advisory |
| 14 | Raw adapter failures are texted to the user | **Open**: Paperclip posts them; needs a friendly-error filter on chat projection |
| 15 | Board approvals aren't bridged to iMessage, so you can't "approve" by text | **Fixed**: `chat_relay.py` turns APPROVE into the board approval |
| 19 | Stage agents can't attach to or publish in the chat thread; board publications drop images; chat-issue comments wake the CEO | **Fixed**: native UI via a board-side relay plus Photon |
| 20 | Killing `uv run` orphans its Python child, which caused duplicate relay sends | Run the relay with `python3` directly; stop with `pkill -f chat_relay.py` |
| 21 | Poll votes aren't read back yet (the APPROVE text works; the ideas poll is informational) | **Open** |
| 16 | Weaker CEO model ignores its instructions | Mitigated with a HARD RULE |
| 17 | Codex usage limit, and the model allowlist differs per ChatGPT plan | External; model pinned in `org.yaml` |
| 18 | Instagram publishing is simulated, with no Graph API | **Open**: the final step is shown as the approval-gated package |

## Files changed in this session

- `app/src/gtm/`:
  - `config.py`: key mapping, `RESEARCH_MODE`, `QA_GATE` / `qa_ok`
  - `roles/research.py`: minimal mode, uv env strip, Bright Data caps
  - `roles/analysis.py` and `strategy.py`: 3 ideas
  - `roles/qa.py`: `summarize`, advisory gate
  - `roles/publish.py` and `workflow.py`: advisory gate
  - `report.py`: ideas section
  - `roles/video.py`: revision format logic; demo mode default
  - **`cards.py`** (new): minimal stage cards, used as relay triggers
  - `cli.py`: renders cards per stage
  - `tests/test_harness.py`: the strict-gate test pins `QA_GATE=strict`
- `photon/send_rich.mjs` (new)
- `harness/`:
  - `docker-compose.yml`: `GTM_OPENAI_*`
  - `up.sh`: env sourcing
  - `campaign.py`: agent mode, `todo` stages, `chat_issue`
  - `bootstrap.py`: CEO launch, HARD RULE, iMessage style, APPROVE handling
  - `org.yaml`: CEO model `gpt-5.6-luna`
  - **`chat_relay.py`** (new)
- `.gitignore`: `recordings/`. `brightdata/.env`: Bright Data key (gitignored).

## Cutting more clips

```sh
# any span, as a stream copy (instant). Example: just the approval moment
ffmpeg -ss 01:21:30 -to 01:22:30 -i recordings/e2e-session-20261011-141904.mkv -c copy recordings/approve.mkv
```
