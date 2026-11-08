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
Shared memory: /workspace/runs/<campaign>/ + /workspace/runs/learnings.json (= ../runs on the host)
```

## Run it

```sh
cd harness
./up.sh                         # builds the image (retries on flaky network), writes .env secrets, starts, waits for health
uv run bootstrap.py             # claims the instance, mints a board API key, creates company + 8 agents, syncs skills/ (idempotent)
uv run campaign.py doctor       # checks server, worker configuration and container credentials
uv run campaign.py new --brand https://tinyfish.ai --niche "AI web agents / browser automation"
uv run campaign.py status <ISSUE>   # e.g. TIN-1
```

Open http://localhost:3100. The admin login is in `state/admin.json` (generated, gitignored).

**Provider keys:**
- `TINYFISH_API_KEY`, `BRIGHTDATA_API_KEY` and `AGENTMAIL_API_KEY` go in `.env`. `up.sh` copies them from your shell if they're set there.
- Campaign workers default to `GTM_LLM_PROVIDER=codex` (compose): every LLM call is a `codex exec` on the Codex CLI's ChatGPT login (`~/.codex/auth.json`, mounted as `/host-codex`), no API key needed. Models: `gpt-5.6-terra` (smart) and `gpt-6-luna` (fast); ChatGPT accounts reject `gpt-6-sol`/`astra`. Calls use a private `CODEX_HOME` (`~/.cache/gtm-codex` in the container) that only links `auth.json`, so worker sessions and sqlite state never land in your own `~/.codex`. To go back to the API key, run `GTM_LLM_PROVIDER=openai ./up.sh`. Voiceover TTS still needs the OpenAI key; without it, it falls back to `espeak-ng`.
- The OpenAI key is never written to `.env`. Either `export OPENAI_API_KEY=...` before `./up.sh`, or run `GTM_OPENAI_ENV_FILE=/path/to/.env ./up.sh`, which reads only `OPENAI_API_KEY` and `OPENAI_BASE_URL` from that file at launch. `OPENAI_BASE_URL` defaults to `https://us.api.openai.com/v1` (US-residency key).
- The CEO (`claude_local`) needs `ANTHROPIC_API_KEY`, or a Claude subscription connected in the UI under **Apps → Connections**. Without one, use campaign `--mode pipeline` (the default), which needs no LLM to orchestrate.

## How a campaign flows (`--mode pipeline`)

`campaign.py new` runs readiness checks, serializes a validated campaign brief, and creates seven dependent stage issues using the shared contract in `app/src/gtm/contract.py`:

```
research → analysis → strategy → video → qa → publish [human approval] → learn
```

The same execution engine (`app/src/gtm/workflow.py`) runs every stage locally and under Paperclip. Each campaign has a `runs/<id>/workflow.json` manifest. Workers check prerequisites and outputs, record failures, and skip completed stages on redelivery. A process lock prevents concurrent workers from modifying one campaign; JSON writes are atomic.

- QA owns the bounded draft/review loop. Exhausted QA blocks its issue and prevents publishing.
- Publish prepares the package, creates one recoverable board approval, and waits in `in_review`. Approval binds the video, script, and QA hashes. Workers read the actual approval record before marking a package ready; a wake reason alone is insufficient.
- Use `uv run campaign.py approvals`, then `uv run campaign.py approve <approval-id|publish-issue>`. This calls the approval API, not an issue-status shortcut. Posting remains simulated.
- Rejection/revision leaves the campaign requiring intervention; it never silently publishes. The current automated revision loop covers QA feedback; human-requested creative revisions still require a revised package and new approval.
- After resolving a stage failure, use `uv run campaign.py retry <blocked-stage-issue> -m "what was fixed"`. Completed stages are retained. A stale publish package requires deliberate regeneration rather than approving changed media under an old decision.
- Learning runs only after approval, then closes the parent campaign. `status <campaign>` combines Paperclip issue status with the local execution manifest and artifact location.
- `--mode ceo` remains an advanced planning path and requires the CEO's own runtime authentication. The deterministic pipeline does not need CEO model credentials.

Offline regression checks (from repository root):

```sh
uv run --frozen --project app python -m unittest discover -s app/tests -v
uv run --frozen --project brightdata pytest brightdata/tests -q
```

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
- `paperclip_agent.py` (stdlib only) wraps all of this: `current_issue()`, `checkout()`, `campaign_id()`, `done()`, `blocked()`, `request_approval()`. The implementation lives in `app/src/gtm/paperclip_agent.py`; the harness module is a compatibility import.
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
