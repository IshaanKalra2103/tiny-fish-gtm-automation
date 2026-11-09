---
name: match
description: Pick 3 to 5 jobs AI can take off this owner's plate and save the needs record.
---

# Needs

1. `ws get profile`, then `catalog needs --type <business_type>`.
2. Choose 3 to 5 jobs. Start from the catalog's jobs for this type, ranked by the profile's `pains`. A pain that maps to
   a job outside the default list may move it in (a salon that misses calls gets `missed-calls`).
3. For each: `need_id`, a plain `title` in the owner's words, `why` (one sentence that ties it to their business, e.g.
   "You're on a roof when the phone rings, so calls go to voicemail"), and `est_hours_saved_week` (a modest, honest
   estimate; 1 to 5 is typical; never above 10).
4. Write the JSON with the Write tool (never `cat`, `echo` or a heredoc) to `/work/tmp/needs.json`, then
   `ws save needs /work/tmp/needs.json`. Shape (the key is `items`, 3 to 5 of them):
   `{"items": [{"need_id": "website-chat", "title": "...", "why": "...", "est_hours_saved_week": 2}]}`
