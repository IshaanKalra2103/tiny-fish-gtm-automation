# agentmail

Creates AgentMail inboxes (agent email addresses) for the GTM agents.

- Account: AgentMail console (https://console.agentmail.to), signed in with Google as `codingfrig12@gmail.com`, org "Ishaan's Organization", Free Tier (3 inboxes, 3,000 emails/month).
- API key: `tiny-fish-gtm-automation` (org scope, full access), stored in `.env` as `AGENTMAIL_API_KEY`.

```bash
uv run create_inbox.py -u tinyfish-gtm -n "TinyFish GTM"   # tinyfish-gtm@agentmail.to
uv run create_inbox.py                                    # random address
uv run create_inbox.py -u gtm-agent --count 2             # gtm-agent-1@, gtm-agent-2@
uv run create_inbox.py --list
```

Each inbox is printed as one JSON line. Named inboxes are idempotent: re-running the same command returns the existing inbox.
