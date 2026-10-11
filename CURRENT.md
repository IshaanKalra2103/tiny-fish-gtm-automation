# CURRENT — work log

Read this first before doing anything. Latest entries at the top.

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

## 2026-10-11 12:40: AgentMail inbox automation (`./agentmail/`)

**Done**
- Signed into the AgentMail console in Dia with Google (`codingfrig12@gmail.com`; the passkey step was done by the user). Org is "Ishaan's Organization", Free Tier.
- Created API key `tiny-fish-gtm-automation` (org scope, full access). It's in `agentmail/.env` (chmod 600, gitignored).
- Built `agentmail/create_inbox.py` (uv project). Run `uv run create_inbox.py -u <name> -n "<Display>"`, or `--count N`, or `--list`.
- Created **`tinyfish-gtm@agentmail.to`** ("TinyFish GTM"). The org now has 2/3 inboxes; the other is the existing `furrow-hermes@agentmail.to`.
- SDK gotcha: `agentmail` reads `AGENTMAIL_API_KEY` when it's imported, so `load_dotenv()` after the import leaves it unset and requests go out without auth (401). Fix: pass `api_key=` explicitly.

**Browser-harness note:** several sessions share Dia. Use a named daemon (`BU_NAME=<yours> browser-harness`) and only touch tabs you opened. With the default daemon, sessions hijack each other's current tab. This session uses `BU_NAME=agentmail`.

**Owns:** `./agentmail/`

**Next**
- Only 1 free inbox slot is left. Upgrade or add a custom domain before scaling.
- Wire inbox send/receive into the GTM pipeline if needed (webhooks or websockets).

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

**Blocked on (user)**
- Add a phone number to the Photon account (avatar menu, top right). The dashboard shows `account_phone_missing`, and Spectrum can't enroll the user or show the number to text until one is added. After that, Get started step 03 shows the line.

**Next**
1. Once the phone is added: refresh Get started, text the line, confirm the `echo:` reply. `npx -y @photon-ai/cli@latest spectrum users list --project <id>` should then show the user.
2. Replace the echo loop with GTM commands (create campaign / status / approve) that forward to the Paperclip harness on :3100.

**Run:** `cd photon && npm start` (or `npm run dev` for watch mode).

**Browser:** this session now uses `BU_NAME=photon browser-harness` and only touches tabs it opened. Early on it used the default daemon, and its device-login navigation landed in the AgentMail session's tab FD14713B.
