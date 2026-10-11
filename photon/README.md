# photon

The iMessage interface for the GTM harness, via [Photon Spectrum](https://photon.codes/docs/spectrum-ts) (Photon project `gtm-automation`, Free plan, shared-pool line).

## How it fits the harness

The harness is the brain, and the interface carries no model logic. Paperclip (v2026.916 and later) has a native, experimental `imessage-photon` chat channel:

- **How messages arrive:** it streams iMessages from Photon over gRPC, so it needs no public URL or inbound port.
- **Who handles them:** each conversation becomes a task for one bound agent. That's the **GTM Orchestrator**, so you can text it to start a campaign, check status or approve.
- **What gets sent back:** the agent's replies go back to the thread. Board comments stay internal, and publishing still needs a board approval.
- **Runtime:** the bound agent can use any adapter (`claude_local`, `codex_local`, ...). Nothing here depends on the model or runtime.

`connect_paperclip.py` wires the channel. It's idempotent, prints one JSON line and never prints secrets:

```sh
uv run photon/connect_paperclip.py            # bind to the orchestrator
uv run photon/connect_paperclip.py --status   # report only
uv run photon/connect_paperclip.py --agent qa # bind to another org.yaml agent key
```

What it reads:
- `harness/state/integration.env`, written by `harness/bootstrap.py`
- `photon/.env`, which holds `PROJECT_ID` and `PROJECT_SECRET`

What it does:
1. Turns on `enableChatConnectors`.
2. Creates the endpoint and checks the Photon project.
3. Configures the shared allocation. The secret goes only to Paperclip's vault.
4. Sets short, human-sounding iMessage reply instructions and verifies the endpoint.

**One-time steps for the user:** text the line, confirm your identity from the link you get back, then finish the test at `http://localhost:3100/apps/chat/<endpointId>/settings`.

## Smoke test (Spectrum echo)

`src/index.ts` is a standalone echo loop for checking the Photon line and credentials. **Stop it before connecting the Paperclip channel**, or both will reply.

```sh
npm install
npm run start   # tsx --env-file=.env; replies "echo: <text>"
```

## Environment

`.env` is gitignored, and `create-spectrum-project` fills it in through the Photon CLI. Don't echo it.

- `PROJECT_ID`
- `PROJECT_SECRET`

These come from your project Settings on the [Photon dashboard](https://app.photon.codes). To manage the project from a terminal, use `npx -y @photon-ai/cli@latest` (`whoami`, `spectrum users list`, `spectrum lines list`, `projects regenerate-secret`).
