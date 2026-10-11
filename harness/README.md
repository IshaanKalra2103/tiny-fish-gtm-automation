# GTM harness: Paperclip in Docker

This runs the **"AI GTM Automation Harness"** box from the architecture diagram: [Paperclip](https://github.com/paperclipai/paperclip) (the agent-company OS) in a Docker container. Inside it is the TinyFish GTM company:
- an agent hierarchy with roles
- task planning and execution as Paperclip issues
- budgets
- human approval gates
- an activity log and cost observability

The pipeline steps themselves live in `../app` (Python/uv) and run inside the container through Paperclip's `process` adapter.

```
Founder / marketing team (board)  ──►  Paperclip :3100 (container gtm-paperclip)
                                        │  company "TinyFish GTM", budget $20/mo
                                        └─ GTM Orchestrator (CEO, claude_local)
                                            ├─ Trend Discovery Agent      uv run gtm agent research
                                            ├─ Analysis & Insight Agent   uv run gtm agent analysis
                                            ├─ Template & Strategy Agent  uv run gtm agent strategy
                                            ├─ Content Generation Agent   uv run gtm agent video
                                            ├─ QA & Testing Agent         uv run gtm agent qa
                                            ├─ Publishing Agent           uv run gtm agent publish
                                            └─ Analytics & Learning Agent uv run gtm agent learn
Shared memory: /workspace/runs/<campaign>/ + /workspace/memory/learnings.json (= ../runs, ../memory on the host)
```

## Run it

```sh
cd harness
./up.sh                         # builds the image (retries on flaky network), writes .env secrets, starts, waits for health
uv run bootstrap.py             # claims the instance, mints a board API key, creates company + 8 agents (idempotent)
uv run campaign.py new --brand https://tinyfish.ai --niche "AI web agents / browser automation"
uv run campaign.py status <ISSUE>   # e.g. TIN-1
```

Open http://localhost:3100. The admin login is in `state/admin.json` (generated, gitignored).

**Provider keys:**
- `TINYFISH_API_KEY`, `BRIGHTDATA_API_KEY` and `AGENTMAIL_API_KEY` go in `.env`. `up.sh` copies them from your shell if they're set there.
- The OpenAI key is never written to `.env`. Either `export OPENAI_API_KEY=...` before `./up.sh`, or run `GTM_OPENAI_ENV_FILE=/path/to/.env ./up.sh`, which reads only `OPENAI_API_KEY` and `OPENAI_BASE_URL` from that file at launch. `OPENAI_BASE_URL` defaults to `https://us.api.openai.com/v1` (US-residency key).
- The CEO (`claude_local`) needs `ANTHROPIC_API_KEY`, or a Claude subscription connected in the UI under **Apps → Connections**. Without one, use campaign `--mode pipeline` (the default), which needs no LLM to orchestrate.

## How a campaign flows (`--mode pipeline`)

`campaign.py new` creates a campaign issue with 6 child issues. Each child is chained to the previous one with `blockedByIssueIds`, and Paperclip only wakes an agent once its blocker is `done`:

```
research → analysis → strategy → video ──(review: QA agent)──(approval: human)──► publish → learn
                                   ▲              │ changes requested
                                   └──────────────┘ (revision loop)
```

- **QA review:** when the video agent marks its issue done, Paperclip turns it into `in_review` and hands it to the **QA agent**. If QA sets it to `in_progress` (with a comment), it goes back to the video agent for revision. If QA sets it to `done`, it moves to the approval stage.
- **Human approval:** the board user approves in the UI (**Inbox → Approve**), or with `uv run campaign.py approve <ISSUE>`, or over iMessage via the Photon bridge. All three are the same API call:

  ```
  PATCH /api/issues/<id>  {"status":"done","comment":"Approved"}
  ```

  Requesting changes is `{"status":"in_progress","comment":"..."}`. Publishing cannot start before this approval.
- `--mode ceo` assigns the campaign issue to the GTM Orchestrator, which plans and delegates the same tree itself.

## Contract for `process` agents (`../app`)

Paperclip spawns `uv run gtm agent <role>` with cwd `/workspace/app`, no shell, and a 900s timeout. It injects:

| Var | Meaning |
|---|---|
| `PAPERCLIP_API_URL` | Server base URL (no `/api`) |
| `PAPERCLIP_API_KEY` | Run token (Bearer) |
| `PAPERCLIP_RUN_ID` | Send as `X-Paperclip-Run-Id` on mutations |
| `PAPERCLIP_AGENT_ID` / `PAPERCLIP_COMPANY_ID` | Agent and company ids |

- The issue id is **not** injected. Read it from `GET /api/heartbeat-runs/$PAPERCLIP_RUN_ID` → `contextSnapshot.issueId`.
- Stdout is not posted. **Every run must comment on its issue**, or Paperclip re-wakes the agent with `missing_issue_comment`.
- `paperclip_agent.py` (stdlib only) wraps all of this: `current_issue()`, `checkout()`, `campaign_id()`, `done()`, `blocked()`, `request_approval()`. The app vendors it.
- Container-only details:
  - `/usr/local/bin/uv` is a wrapper that gives each uv project its own venv at `/paperclip/venvs/<project>`, so the host's macOS `.venv` dirs are never touched.
  - `espeak-ng` and DejaVu fonts are installed for the video step.

## Integration for other services

After `bootstrap.py`, `state/integration.env` holds `PAPERCLIP_API_URL`, `PAPERCLIP_BOARD_API_KEY`, `PAPERCLIP_COMPANY_ID`, `PAPERCLIP_BOARD_USER_ID` and `PAPERCLIP_AGENT_<ROLE>` ids.
- Use `Authorization: Bearer $PAPERCLIP_BOARD_API_KEY`.
- From other containers, use `http://host.docker.internal:3100/api`. That hostname is already allowed.

Useful calls:
- `GET /api/companies/:cid/issues?parentId=...`: campaign status
- `GET /api/companies/:cid/approvals?status=pending`
- `GET /api/companies/:cid/org`
- `GET /api/companies/:cid/budgets/overview`
- `POST /api/issues/:id/comments {"body": ...}`

## Why a custom image instead of `ghcr.io/paperclipai/paperclip`

- The upstream image is about 1.8 GB, and GHCR serves blobs to this network at about 100 KB/s.
- A source build compiles a Rust runner and takes 20+ minutes cold.
- This image is `node:24-trixie-slim`, the same base as upstream, plus the published `paperclipai@2026.1005.0` npm release, Claude Code and uv. It reuses upstream's entrypoint (UID remap, chown of the data volume, gosu to `node`).
- Data lives in the named volume `gtm-harness_paperclip-data`, which holds the embedded Postgres. `docker compose down -v` wipes it.
- `../paperclip` is the upstream source checkout, kept for reference only.
