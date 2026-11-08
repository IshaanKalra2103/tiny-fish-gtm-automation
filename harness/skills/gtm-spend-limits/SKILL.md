---
name: gtm-spend-limits
description: Spend and rate-limit rules for the GTM harness. Covers the free/cheap defaults to keep, what each paid provider costs, when paid generation may be switched on, no blind retries of paid runs, and texting, email and posting caps. Use before any action that costs money or credits, sends messages, or posts, and whenever a run is slow or failing and a retry is tempting.
---

# Spend and rate limits

The user's standing instructions: "be well under rate limits" and "don't waste tokens on unnecessary stuff". After running out of credits mid-session, they added "stop fal for now and limit to demo only". Cheap and reliable beats impressive.

## Keep these defaults

| Setting | Default | What it means |
|---|---|---|
| `GTM_RESEARCH_MODE` | `minimal` | Search, Fetch, Browser and a 5-post Bright Data sample, capped at 180 s, about 1-3 min in total. `full` adds a TinyFish Agent run on YouTube filters: 5-11 min and $0.35-0.80. It once hit the 900 s stage timeout. |
| `GTM_VIDEO_MODE` | `demo` | Captions and motion over a reference image. Free, takes seconds. |
| `VIDGEN_ALLOW_PAID` | unset | fal and Vizard are off, and vidgen forces demo mode. |
| `GTM_TINYFISH_BUDGET_USD` | `1.50` | TinyFish cap per run. |
| Paperclip budgets | $20/month for the company, $5 for the Orchestrator, $2 per specialist | Hard ceilings, set by `bootstrap.py`. |

**Turn paid generation on only when the user asks for it in the current conversation.** Turn it back off afterwards.

## What things cost

| Provider | Cost | Notes |
|---|---|---|
| TinyFish Search, Fetch | free | Use these first. |
| TinyFish Agent | $0.016 per step | YouTube-filter runs take 22-49 steps. At most **2 concurrent** automation runs. |
| TinyFish Browser | $0.002 per minute | 4 screenshots take about 18 s. |
| fal, MiniMax H3 Max text-to-video | $0.03 per second | A 22 s ad costs about $0.66. Off by the user's request. |
| fal, reference-to-video (product ref) | $0.05 per second | A 22 s ad costs about $1.10. |
| Vizard | about 40 credits per 22 s video | Takes about 15 min. Too slow for a live demo. |
| Codex image generation (vidgen `--person` / `--product`) | about 22k Codex tokens and 45 s per image | Reuse `runs/<id>/refs/` across revisions. |
| ElevenLabs | Starter tier (about 18k characters were left this cycle on 2026-10-11) | Keep test scripts short. |
| OpenAI | per token, not tracked in the run ledger | Persona QA makes 3 calls per draft with frames. |

## Retries

- **Never blindly retry a paid run that errored or timed out.** It may still be running. Check first (TinyFish `get_run` / `list_runs`, `vidgen vizard status`), and cancel orphans. The TinyFish SDK once started a duplicate paid Agent run on its own retry.
- **Don't regenerate what exists.** The workflow skips completed stages on redelivery, and `campaign.py retry` re-runs only the blocked stage.
- **Test one at a time, at the smallest size:** one clip, the shortest script, one persona, before scaling up.

## Messaging and posting caps

| Channel | Cap |
|---|---|
| Founder iMessage (Photon line) | One text per event. Test texts at least a minute apart. The relay waits 3 s between stage updates. |
| AgentMail `send` (enforced by `agentmail/inbox.py`) | 30 s gap per inbox; at most 40 per inbox and 90 in total per 24 h. |
| New social accounts | One per platform per day from this network. Stop at CAPTCHAs and security checks and hand them to a human. |
| Posting (Instagram, TikTok) | At most 3 posts a day per account, at least 2 h apart; at most 1 a day in the first week. Official APIs only (Instagram Graph `content_publishing_limit`, TikTok Content Posting). Any rate-limit or action-block pauses that account for 24 h and gets reported to a human. Never retry in a loop. |

Publishing in this harness is simulated. Nothing posts without an approved board approval.
