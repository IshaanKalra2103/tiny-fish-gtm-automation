---
name: gtm-growth-loop
description: Run the TinyFish growth loop for a campaign: trend research, analysis and personas, script, short video, persona QA with revisions, publish package behind human approval, and learnings. Use when a GTM campaign issue is assigned to one of the roles research, analysis, strategy, video, qa, publish or learn.
---

# GTM growth loop

There's one CLI with one subcommand per role. Every call prints exactly one JSON line to stdout. Success looks like `{"ok": true, "run": ..., "summary": ..., "dir": ...}`. Failure prints `{"ok": false, "error": ...}` and exits 1. Progress goes to stderr. Artifacts live in `runs/<run-id>/` (in the harness, `/workspace/runs/<campaign>/`), so read the files you need rather than expecting them in stdout.

```bash
cd /workspace/app                                    # on the host: app/
uv run gtm agent research --run GTM-1                # TinyFish Search+Fetch+Agent+Browser, Bright Data -> evidence.json
uv run gtm agent analysis --run GTM-1                # insights.json, personas.json, charts.json
uv run gtm agent strategy --run GTM-1                # script_v1.json
uv run gtm agent video    --run GTM-1                # video_v1.mp4 (+ frames for QA)
uv run gtm agent qa       --run GTM-1                # qa_vN.json; revises and re-renders up to v3 -> qa.json
uv run gtm agent publish  --run GTM-1                # publish.json (status awaiting_approval | needs_human)
uv run gtm approve GTM-1                             # human only: marks it ready_to_publish (simulated)
uv run gtm agent learn    --run GTM-1                # appends to runs/learnings.json for the next campaign
uv run gtm run --run GTM-1 --niche "AI browser agents" --brand-url https://www.tinyfish.ai/   # all roles in order
uv run gtm report GTM-1                              # rebuilds runs/GTM-1/index.html (the dashboard)
```

Inside Paperclip, omit `--run`. The CLI finds the assigned issue, checks it out, derives the run id from the root campaign issue (for example `GTM-1`), and comments and sets the status itself. The campaign issue description can set the brief with `brand_url: ...`, `niche: ...`, `audience: ...` and `goal: ...` lines.

## Rules

- Run the roles in order. Each role reads the previous role's files. `qa` runs its own revise loop, so don't call `strategy` or `video` again after `qa` has started.
- `research` takes 3–8 minutes because the TinyFish Agent run is slow. It spends real money: TinyFish Agent is $0.016 per step, and each run is capped by `GTM_TINYFISH_BUDGET_USD` (default $1.50).
- Never approve on a human's behalf. `publish` stops at the approval gate, and posting is simulated.
- Persona scores come from **synthetic** personas built from public comments. Report them as hypotheses, not as audience validation.
- Keys resolve on their own: `TINYFISH_API_KEY`, then the LLM key for `GTM_LLM_PROVIDER` (`openai` uses `OPENAI_API_KEY` plus an optional `OPENAI_BASE_URL`; `anthropic` uses `ANTHROPIC_API_KEY`), from the environment, `app/.env`, or `GTM_ENV_FILE`. Bright Data reads its own key in `brightdata/`. Never pass keys on the command line.
