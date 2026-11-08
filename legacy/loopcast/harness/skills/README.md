# Harness skills

How the GTM harness should work and operate, drawn from every build session on 2026-10-11 (the user's directions, the end-to-end iMessage runs in `SHOWDOWN.md`, and `CURRENT.md`). Each folder is a plain-markdown skill that works the same on Codex and Claude Code.

| Skill | For | Covers |
|---|---|---|
| [`gtm-orchestrator`](gtm-orchestrator/SKILL.md) | GTM Orchestrator (attached) | Routing a founder's request, the one-command launch with a verbatim niche, the stage map, what never to do, blocked stages, reporting |
| [`gtm-founder-chat`](gtm-founder-chat/SKILL.md) | GTM Orchestrator (attached) | iMessage style, what may go in the thread, turning errors into plain words, pacing, APPROVE by text |
| [`gtm-spend-limits`](gtm-spend-limits/SKILL.md) | GTM Orchestrator (attached) and operators | Free and cheap defaults, the paid-generation gate, provider prices, no blind retries, texting, email and posting caps |
| [`gtm-content-quality`](gtm-content-quality/SKILL.md) | Anyone writing scripts or video prompts, or judging drafts | Formats, precise shot prompts, product refs, caption and CTA layout, evidence-backed claims, what QA scores mean |
| [`gtm-harness-ops`](gtm-harness-ops/SKILL.md) | Operators (host Claude Code or Codex sessions, humans) | Bring-up, keys and Codex auth, unsticking a campaign, the container and process-agent contract, model-agnostic tool rules |

The tool skills stay next to their tools: `app/SKILL.md`, `video/SKILL.md`, `identity/SKILL.md`, `brightdata/SKILL.md` and `agentmail/SKILL.md`.

## Install

`uv run harness/bootstrap.py` ends by running `sync_skills.py`, which:
- creates or updates every folder here as a Paperclip company skill (slug = folder name);
- attaches the skills listed under each agent's `skills:` in `org.yaml`.

To re-sync after editing a skill:

```sh
uv run harness/sync_skills.py --check   # read-only: what would change
uv run harness/sync_skills.py           # apply; agents pick it up on their next run
```

Only LLM agents load skills: `codex_local` gets them as `CODEX_HOME/skills` symlinks, and `claude_local` gets them in `.claude/skills`. The seven `process` stage agents ignore skills, so their rules live in `app/` code.

Keep content-making skills (video, image) off the Orchestrator. It must route content requests to the pipeline, not make content itself.
