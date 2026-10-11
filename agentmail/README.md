# agentmail

Throwaway AgentMail inboxes for the GTM agents: create them, sign up for sites with them, wait for verification codes and links, and send mail.

- Account: AgentMail console (https://console.agentmail.to), signed in with Google as `codingfrig12@gmail.com`, org "Ishaan's Organization", Free Tier (3 inboxes, 3,000 emails/month).
- API key: `tiny-fish-gtm-automation` (org scope, full access), in `.env` as `AGENTMAIL_API_KEY`. An `AGENTMAIL_API_KEY` environment variable takes precedence.
- Throwaway inboxes for sign-ups: `funnyflower74@agentmail.to` (Instagram `@agentlab.gtm.xhcq`), `eagerspring500@agentmail.to`.
- `youngmirror648@agentmail.to` is attached to the GTM Orchestrator through Paperclip's native AgentMail channel, so each email thread becomes a Paperclip task. Don't use it for sign-ups.

`inbox.py` is a uv script with inline dependencies (locked in `inbox.py.lock`). It runs from any directory and never touches a surrounding project's venv, so it is safe inside the Paperclip container, where `UV_PROJECT_ENVIRONMENT` points at `app/`'s venv.

```bash
uv run agentmail/inbox.py list
uv run agentmail/inbox.py wait eagerspring500@agentmail.to --subject verify --since 2m
uv run agentmail/inbox.py read ADDR MESSAGE_ID
uv run agentmail/inbox.py messages ADDR --limit 5
uv run agentmail/inbox.py send ADDR --to x@y.com --subject S --text T
uv run agentmail/inbox.py create [-u name] [-n "Display"] [--count N]
uv run agentmail/inbox.py delete ADDR [ADDR ...]
```

In the Paperclip container use `/workspace/agentmail/inbox.py`. `SKILL.md` is the agent-facing version of this, for the harness's Claude agents.

## Paperclip channel

`connect_paperclip.py` attaches an existing inbox to a harness agent through Paperclip's built-in AgentMail channel. Paperclip vaults the key, receives mail over WebSocket, and turns each thread into a task. It's idempotent.

```bash
uv run agentmail/connect_paperclip.py            # youngmirror648@ -> orchestrator
uv run agentmail/connect_paperclip.py --status
```

## Account sign-ups

`account-signup/SKILL.md` is the browser workflow for creating site accounts (Instagram, TikTok) with the throwaway inboxes. It's linked into `.claude/skills/`.
