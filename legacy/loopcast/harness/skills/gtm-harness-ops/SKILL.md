---
name: gtm-harness-ops
description: Operator runbook for the GTM Paperclip harness (Docker container gtm-paperclip on :3100). Covers bring-up, keys and Orchestrator auth, the iMessage relay, how to unstick a campaign (stuck, blocked or timed-out stages, venv clobbering, Orchestrator errors), the process-agent contract, and the rules for adding tools any model can drive. Use when starting, fixing or extending the harness, or when a campaign is stuck. Not for the Orchestrator itself; it has no Docker access.
---

# Harness operations

## Before you touch anything

- **Read `CURRENT.md`.** Several sessions work on this repo at once. It says who owns what and whether a live run is in progress. Log what you did there afterwards.
- **Never `./up.sh`, rebuild or recreate the container during a live run.** It restarts Paperclip and kills in-flight agents. `docker compose exec` is safe.

## Bring-up (all steps are idempotent)

```sh
cd harness && GTM_OPENAI_ENV_FILE=<path to an env file holding OPENAI_API_KEY> ./up.sh   # build, start, wait for health, uv sync workers
uv run harness/bootstrap.py          # company, 8 agents, budgets, Orchestrator AGENTS.md, then sync_skills.py
uv run harness/campaign.py doctor    # server, the 7 process agents, container runtime and credentials
python3 harness/chat_relay.py        # host loop, ONE instance: stage updates to the founder's iMessage as native UI; APPROVE replies become board approvals
```

- **A bare `docker compose up -d` skips the worker install.** Afterwards run `docker compose exec -T --user node -w /workspace/app paperclip uv sync --frozen`. A first sync takes about 12 min on this network. Without it, `doctor` fails with "gtm not installed".
- **Stopping the relay:** use `pkill -f chat_relay.py`. Killing a `uv run` parent orphans the child, and two relays send everything twice.
- **UI login:** http://localhost:3100, with the credentials in `harness/state/admin.json`. The board API key is in `state/board.json`, and the ids for other services are in `state/integration.env`.

## Keys and auth

- **OpenAI.** Source the key from the external env file through `GTM_OPENAI_ENV_FILE`. Never read, print or copy it into `.env`.
  - It enters the container as `GTM_OPENAI_API_KEY` / `GTM_OPENAI_BASE_URL`, and `app/src/gtm/config.py` maps it back to `OPENAI_*` inside workers only.
  - **Never set a container-wide `OPENAI_API_KEY`.** Codex picks it up, drops the ChatGPT login, and the Orchestrator fails with 401.
  - `OPENAI_BASE_URL` must be `https://us.api.openai.com/v1`. Any other host gives 401 `incorrect_hostname`.
- **The Orchestrator's adapter is swappable** with `adapter:` and `model:` in `org.yaml`, then re-run `bootstrap.py`. Its instructions and skills are model-agnostic.
  - **`claude_local`:** needs the user's Claude subscription connected in the UI under Apps → Connections, or `ANTHROPIC_API_KEY`. The model defaults to `GTM_CEO_MODEL`.
  - **`codex_local`:** runs on the host's Codex CLI ChatGPT login. `~/.codex` is mounted at `/host-codex`, and `auth.json` is symlinked, never copied.
    - **Usage limit hit:** log the host `codex` into another account. No restart is needed.
    - **400 on the model:** each ChatGPT plan allows different models. Probe with `codex exec -m <model> "say ok"` before pinning `model:`. `gpt-5.6-luna` worked on the second account.
  - **Weaker models drift** from long instructions. That's why the HARD RULE in AGENTS.md and the attached skills exist.
- **Other keys:** TinyFish, Bright Data and AgentMail keys go in `harness/.env`, or in each tool's own `.env` / session file (`brightdata/.env`, `agentmail/.env`, `video/.fal/`, `video/.vizard/`). Tools resolve their own secrets, so never pass a key as a CLI argument.

## Unstick a campaign

| Symptom | Cause | Fix |
|---|---|---|
| A stage never starts, though its blocker is done | It was created as `backlog`, and Paperclip never wakes backlog issues | Set it to `todo`. `campaign.py new` already does this. |
| A stage is `blocked` | The worker recorded a failure in its comment and in `workflow.json` | Fix the cause, then `uv run harness/campaign.py retry <STAGE> -m "what was fixed"`. |
| A stage hit the 900 s timeout, and `retry` does nothing | The agent is stuck in `error`, and Paperclip wants execution reconciliation | `docker compose exec -T --user node -w /workspace/app paperclip uv run gtm agent <role> --run <CAMPAIGN>`, then mark the stage issue `done`. This is an open gap. |
| Mid-run the worker loses `tinyfish`/`openai`, or certifi's CA file is missing | A nested `uv run --project X` inherited `UV_PROJECT_ENVIRONMENT` and synced over `/paperclip/venvs/app` | Call other uv projects with `env -u UV_PROJECT_ENVIRONMENT`, then `uv sync --frozen` the app again. |
| Research is slow, or a duplicate paid TinyFish Agent run appears | Full research mode plus a non-idempotent SDK retry | Cancel the orphaned run and keep `GTM_RESEARCH_MODE=minimal`. |
| The Orchestrator fails with 401 or 400, or hits a usage limit | See Keys and auth | Fix the auth, clear the agent's error state, and have the founder text again. |
| The Orchestrator hand-makes content or skips the launcher | Model drift; weaker models ignore long instructions | Check that its AGENTS.md has the HARD RULE and that the `gtm-orchestrator` skill is attached (`sync_skills.py`). |
| A stage update never reached the phone | `chat_relay.py` isn't running, the stage didn't render its card, or the brief has no `chat_issue` | Start the relay (`--once` does a single pass). Sent updates are listed in `state/chat_relay_sent.json`. |
| The founder got a raw adapter error | Paperclip projects agent failures into the chat | Open gap: there's no friendly-error filter yet. |
| The founder voted on a poll and nothing happened | Poll votes aren't read back | Open gap. Approval works through an APPROVE text reply. |

## How the container runs

- **Container:** `gtm-paperclip`, running paperclipai 2026.1005.0 in authenticated/private mode.
- **Mounts:** `/workspace` is the repo root, and agents run as uid `node`.
- **uv:** a wrapper gives each project its own venv at `/paperclip/venvs/<project>`, so host `.venv` folders are never touched.
- **ffmpeg:** there's no system ffmpeg. vidgen uses imageio-ffmpeg's static build; override it with `VIDGEN_FFMPEG`.
- **Process agents** run `uv run gtm agent <role>` with cwd `/workspace/app`, no shell, and a 900 s timeout.
  - **Finding the issue:** the issue id isn't injected. Get it from `GET /api/heartbeat-runs/$PAPERCLIP_RUN_ID` → `contextSnapshot.issueId`.
  - **Comment every run:** a run that doesn't comment on its issue is re-woken with `missing_issue_comment`.
  - **Helpers:** `app/src/gtm/paperclip_agent.py` wraps all of this.
- **Chat-origin issues:** a comment there wakes the Orchestrator, and non-bound agents can't attach files to it. That's why stage updates go out through the relay and not as comments.
  - **How the relay works:** workers only render `runs/<id>/cards/*.png`, which act as triggers. The relay sends native iMessage UI through `photon/send_rich.mjs`: text, link previews, inline mp4, Apple polls and screen effects.
- **Approvals are board-only.** An approval binds the video, script and QA hashes. Changed media needs a new package and a new approval.
- **Skills** in `harness/skills/` reach only LLM agents (`codex_local` symlinks them into `CODEX_HOME/skills`; `claude_local` mounts them in `.claude/skills`). Process agents ignore skills; their behaviour lives in code.

## Adding a tool or worker that any model can drive

The harness may run on Codex or Claude Code, so everything it calls must stay model-agnostic:

- **CLI output:** one JSON line on stdout. `{"ok": true, ...}` on success; `{"ok": false, "error": ...}` and exit code 1 on failure. Progress goes to stderr.
- **Skills:** a plain-markdown `SKILL.md` per tool, with no vendor tool names. Give exact container commands with `/workspace/...` paths.
- **No hardcoded LLM vendor:** use `GTM_LLM_PROVIDER` and env-selected models. Tools find their own secrets.
- **Python:** always uv. Each project gets its own venv, small tools are uv scripts with inline dependencies, and a nested `uv run` is prefixed with `env -u UV_PROJECT_ENVIRONMENT`.
- **Exposing a tool:** list it under `tools:` in `org.yaml`. Put an Orchestrator-facing skill in `harness/skills/` and attach it under that agent's `skills:` in `org.yaml`.
- **Don't give content tools to the Orchestrator.** That includes video and image skills, because it must route content requests to the pipeline.

## Demo runs

- **Recording:** record the screen to `recordings/` (gitignored). Log each step with its time offset in `SHOWDOWN.md`.
- **Texting:** text the Photon line from Mac Messages, a minute or more apart.
- **Shared browser:** Dia is shared between sessions. Use a named daemon (`BU_NAME=<you> browser-harness`) and only touch tabs you opened.
