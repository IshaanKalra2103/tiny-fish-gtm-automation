---
name: account-signup
description: Create a website account (Instagram, TikTok, or similar) for the team, using a throwaway AgentMail inbox for the email verification code. Drives the user's Dia browser over CDP with browser-harness in a private context. Use when asked to sign up for or make an account with one of the throwaway emails.
---

# Account sign-up with a throwaway inbox

Host-side workflow: it needs the user's Dia browser, so it does not run inside the
Paperclip container. Tools:

- `browser-harness` (CDP into Dia; remote debugging on port 9222)
- `uv run agentmail/inbox.py` (see `agentmail/SKILL.md`): `list`, `wait`, `read`
- Credentials file `agentmail/.accounts.json` (gitignored, mode 600)

## Ground rules

- **Pacing.** One account per platform per sitting. Make every step a single attempt:
  no click loops, and no resending codes faster than the page's own countdown. Wait
  for spinners to finish (10-20 s) instead of clicking again.
- **Stop at security checks.** CAPTCHA, puzzle, "confirm you're human", phone
  verification, "continue on the app", "suspicious activity": stop and hand the step
  to the user. Never solve, bypass, or retry around them, and never spoof
  fingerprints, mouse movement, or IPs.
- **Posting is not part of sign-up.** If content must be posted later, use the
  platform's official posting API (Instagram Graph API, TikTok Content Posting API)
  or have a human approve and press Post. Never script "human-like" posting.
- Never print passwords or API keys. Read them from files inside the browser script.

## Steps

1. **Pick an inbox** from `uv run agentmail/inbox.py list` that hasn't been used on
   this platform yet (check `.accounts.json`).
2. **Write credentials first.** Add an entry to `agentmail/.accounts.json` (email, a
   generated 16-character password, name, username, an adult birthday) with
   `status: pending`, and `chmod 600` it. Check the file is gitignored with
   `git check-ignore agentmail/.accounts.json`.
3. **Use a named daemon and a private browser context.** The user is logged in to
   Instagram and TikTok in Dia's default profile, so never sign up there.
   ```python
   # BU_NAME=<your-session> browser-harness <<'PY'
   ctx = cdp("Target.createBrowserContext", disposeOnDetach=False)["browserContextId"]
   tab = cdp("Target.createTarget", url="about:blank", browserContextId=ctx)["targetId"]
   switch_tab(tab, activate=True); goto_url(SIGNUP_URL)
   ```
   Don't pass `newWindow=True`; Dia drops that tab immediately. Save both IDs.
4. **Re-attach and assert at the start of every script.** The daemon can silently
   fall back to another tab, such as the AgentMail console with its Delete buttons:
   ```python
   switch_tab(TAB); assert "instagram.com" in page_info()["url"]
   ```
5. **Fill the form** using accessibility-tree nodes (role and name), clicking at each
   node's box center and typing with `type_text`. For inputs a site prefills, use
   `fill_input(selector, text, clear_first=True)`. Birthday pickers are custom
   comboboxes: click the combobox, then click the `option` node.
6. **Read every field back before anything that sends an email** (`js(...)` on the
   input values). TikTok's email autocomplete silently rewrote
   `x@agentmail.to` to `x@gmail.com` and sent the code to a stranger. Fix it with
   `fill_input` and then `press_key("Escape")`. After fixing one field, re-check the
   others: the TikTok password field was cleared.
7. **Note the time, then trigger the code** (Submit or Send code). Store
   `since = now - 5s` in ISO format.
8. **Get the code:**
   ```bash
   uv run agentmail/inbox.py wait ADDR --from instagram --since "$SINCE" --timeout 150
   ```
   Use `codes[0]` from the JSON. Instagram re-sends the *same* code when the form is
   resubmitted, so a repeated code is normal.
9. **Enter the code, continue, and screenshot** the result
   (`capture_screenshot(path, max_dim=1200)`). If the page lands on a security
   check, stop (see the ground rules).
10. **Record the outcome** in `.accounts.json`: `created`, or `blocked: <reason>`.
    Leave the private tab logged in, and tell the user the username and where the
    password is stored.

## Platform notes (2026-10-11)

| Platform | URL | Notes |
|---|---|---|
| Instagram | `instagram.com/accounts/emailsignup/` | One page: email, password, birthday (3 custom comboboxes), full name, username (prefilled, so clear it; a green check means it's available). Submit opens a 6-digit code step. It worked end to end with no CAPTCHA. |
| TikTok | `tiktok.com/signup/phone-or-email/email` | Birthday comboboxes, email, password, Send code (60 s cooldown), 6-digit code, Next. The email code arrives from `noreply@account.tiktok.com`. On Next, the web sign-up was refused with "For security purposes, continue on the TikTok app". Finish in the mobile app with the same email and the code from `wait`. |
