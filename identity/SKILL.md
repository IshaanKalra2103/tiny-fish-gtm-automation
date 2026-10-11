---
name: product-identity-pmf
description: First stage of a GTM campaign. Work out what the product really is (positioning, audience, voice, visual identity) from its own website, render a moodboard of it, then research candidate niches for live demand, pains and competitors, and pick the niche the campaign should target. Use when a campaign issue for the Product Identity & PMF role is assigned, or before trend research when the niche isn't decided.
---

# Product identity + PMF

You do the thinking; the `identity` CLI only collects evidence and renders. Every command prints one JSON line (`{"ok": true, ...}`, or `{"ok": false, "error": ...}` with exit code 1). Files go to `/workspace/runs/<campaign>/identity/`.

```bash
cd /workspace/identity          # on the host: identity/
uv run identity collect   --campaign <id> --brand <homepage URL>
uv run identity schema    --kind identity     # exact fields for identity.json
uv run identity validate  --campaign <id> --kind identity
uv run identity moodboard --campaign <id>
uv run identity market    --campaign <id>     # niches come from identity.json
uv run identity schema    --kind pmf
uv run identity validate  --campaign <id> --kind pmf
```

## Steps

1. **Collect.** Run `collect`. It uses TinyFish Fetch to read the homepage plus up to 6 subpages (pricing, product, customers, docs, ...). It uses TinyFish Browser to capture 3 desktop screenshots and the fonts and colors the site actually renders. Takes about 1.5 minutes and about $0.003. It also writes `moodboard_draft.png`.
2. **Decide what the product really is.** Read `evidence.json` and look at the screenshots and `moodboard_draft.png`. Then write `identity.json`:
   - `what_it_really_is`: plain words, the way a customer would explain it to a colleague, not the hero copy.
   - `audience`: who has the pain, stated as the pain. `value_props` / `proof`: each claim cites a URL from `evidence.json`. Never invent numbers or customers.
   - `voice`: exactly 3 adjectives, plus do's and don'ts that a script writer can follow.
   - `visual`: palette hexes and fonts taken from `evidence.json` (`palette`, `css_colors`, `fonts`). Swap in a closer hex only if a screenshot clearly shows one.
   - `niches`: 2–5 candidate niches where this product could win, each with 1–2 search terms people actually use.
3. **Validate and render.** Run `validate --kind identity` and fix every problem it lists. Then run `moodboard`, open `moodboard.png`, and check that it reads true to the site. If not, fix `identity.json` and render again.
4. **Research the market.** Run `market`. For each niche it runs 5 TinyFish searches: news in the last 30 days, Reddit and HN talk, pain threads, competitor roundups, and short videos. It then reads the top community threads with Fetch. Takes about 40 seconds and is free.
   - Optional: get engagement numbers on that niche's short videos:
     `uv run --project /workspace/brightdata bd-gateway sample --campaign <id> --platform tiktok --urls-file /workspace/runs/<id>/identity/social_urls_<niche>.txt --top 0`
5. **Pick the niche.** Read `market.json`: the `signals` counts, `age_days` on every result, and the thread excerpts. Write `pmf.json`:
   - Score each niche 1–5 on `demand`, `urgency`, `competition` (5 = crowded) and `fit`. Back each score with at least 2 `signals` that cite URLs from `market.json`, and list the real `pains` in people's words.
   - `chosen_niche`: the one the campaign targets. It must be one of the scored niches.
   - `hypothesis`: "For <segment> who <pain>, <product> <does what>, unlike <alternative>."
   - `risks` and `next_tests`: what would prove you wrong, and the cheapest test for it.
6. Validate with `--kind pmf`. Then comment on your issue: the chosen niche, a one-line hypothesis, and the paths to `moodboard.png` and `pmf.json`. The research stage reads `chosen_niche`, and strategy reads `identity.json` for voice, audience and claims.

## Rules

- Counts in `market.json` are search results, not market size. Say "signal", never "demand is X".
- PMF here is a hypothesis built from public signals. Label it that way. It hasn't been validated with customers.
- Don't profile individual people from community threads. Quote pains, not usernames.
- The TinyFish key comes from the environment (`TINYFISH_API_KEY`) or `identity/.env`. Never print it.
