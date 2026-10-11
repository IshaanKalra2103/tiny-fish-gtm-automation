# identity: product identity, moodboard, PMF market research

This is the first stage of a campaign. It works out what the product really is and which niche to go after, before the trend research stage digs into content.

| Command | Does | TinyFish | Cost / time |
|---|---|---|---|
| `identity collect --campaign C --brand URL` | Reads the homepage and up to 6 key subpages, captures 3 desktop screenshots, and records the fonts, colors and meta the site actually renders. Writes `evidence.json` + `moodboard_draft.png` | Fetch (with links and images) + Browser | ~$0.003, ~1.5 min |
| `identity moodboard --campaign C` | Renders `moodboard.png`: the real screenshots, palette and type next to the agent's `identity.json` (positioning, audience, voice, value, keywords) | none | instant |
| `identity market --campaign C [--niche N]` | For each niche, runs 5 searches (news in the last 30 days, Reddit/HN talk, pains, competitor roundups, short videos), then reads the top threads. Writes `market.json` + a `social_urls_<niche>.txt` per niche for `bd-gateway` | Search + Fetch | free, ~40 s for 2 niches |
| `identity schema/validate --kind identity\|pmf` | The contract for what the agent writes, and a check of the file | none | instant |

**The tools don't call an LLM.** The harness agent (Claude Code or Codex, model chosen in Paperclip) reads the evidence and writes `identity.json` and `pmf.json`; the tools validate them and render. `SKILL.md` is that agent's procedure.

**Outputs:** everything goes in `runs/<campaign>/identity/` (`GTM_RUNS_DIR` moves it):
- `evidence.json`, `shot_*.jpg`, `moodboard_draft.png`
- `identity.json` and `moodboard.png`
- `market.json`, `social_urls_*.txt`
- `pmf.json`

The research stage uses `pmf.json`'s `chosen_niche` as its niche.

```bash
cd identity && uv sync
uv run pytest                     # 10 offline tests, no key needed
TINYFISH_API_KEY=... uv run identity collect --campaign demo --brand https://www.tinyfish.ai/
```

**Checked live against tinyfish.ai on Oct 11 2026:**
- `collect` read 6 pages: home, pricing, customers, enterprise, docs and blog.
- It captured 3 screenshots and found the fonts Host Grotesk, Familjen Grotesk, Inter and Geist Mono.
- Its palette was white and gray, plus the purple, orange-red and magenta of the gradient banner.
- `market` returned 10 results per signal type for "AI browser agents" and read real "what breaks for browser agents" threads.

**TinyFish Browser gotcha:** use the session's own tab, which has already navigated to the URL at creation. Calling `new_context()` closes the connection.
