---
name: throwaway-inbox
description: Use the team's throwaway AgentMail inboxes to sign up for websites, receive verification codes and links, and send plain-text email. Use when a task needs an email address you control, or an emailed code or confirmation link.
---

# Throwaway inbox

The team has three throwaway AgentMail inboxes (free tier, 3 max). One CLI covers all
mail work. Run it from any directory; it prints one JSON object per line.

```bash
M=/workspace/agentmail/inbox.py      # on the host: agentmail/inbox.py

uv run $M list                                         # the inboxes you can use
uv run $M wait ADDR --from github --since 2m           # block until a matching email arrives
uv run $M messages ADDR --limit 5                      # recent mail, newest first
uv run $M read ADDR MESSAGE_ID                         # one message in full
uv run $M send ADDR --to someone@x.com --subject S --text T
```

## Signing up for a site

1. Pick an inbox address from `list`.
2. Submit the site's sign-up form with that address.
3. Run `wait ADDR`, filtering with `--from` (sender contains) or `--subject` (subject
   contains). It returns the newest matching email received in the `--since` window
   (default `2m`; widen it if the form took longer), or exits 2 after `--timeout`
   seconds (default 180).
4. Use `codes` (4-8 digit numbers found in the subject and body) or `links` (URLs in
   the body; ignore the agentmail.to footer link) from the JSON.

## Rules

- Inboxes are shared with other agents. Filter `wait` by sender or subject so you
  don't take someone else's code.
- Don't run `create` or `delete` unless the task asks for it. The free tier is full,
  and deleting an inbox loses its mail permanently.
- `send` really sends. Don't retry a send just because it timed out; check
  `messages` on the recipient side first if you can.
- The API key comes from AGENTMAIL_API_KEY or `/workspace/agentmail/.env`. Never
  print it or copy it into issues, comments, or files.
