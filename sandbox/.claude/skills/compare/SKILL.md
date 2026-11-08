---
name: compare
description: Compare 2 or 3 vetted tools for one job and save the compare record.
---

# Compare

1. `ws get profile`. Run `catalog match --type <business_type> --need <need_id> --works-with <profile.uses joined by commas>`.
2. Keep 2 or 3 options. For each write a `fit_sentence`: one plain sentence on why it fits THIS business (price, what
   it works with, how long setup takes). Copy `works_with` from the tool's integrations that the owner already uses.
3. `recommended_tool_id`: the best fit. Prefer tools that work with what they already use, then the higher trust
   score, then a free plan. Prefer a tool with `can_setup: true` when it is close.
4. `ws save compare /work/tmp/compare.json`.
5. In your reply name the recommended tool, its price, and why, in two or three sentences. Mention the trust badge in
   plain words ("verified by our team", "use with caution").
