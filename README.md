# MainStreet AI

MainStreet AI helps Main Street small businesses (diners, coffee shops, small HVAC firms, landscapers, salons) discover, compare and adopt AI tools they can trust. Every tool in the catalog is vetted with a visible trust score and a human review, and an agent can set the chosen tool up for the owner, over the web or iMessage.

Built for the UMD AI for Small Business Hack-a-thon, Fall 2026. Design: `docs/superpowers/specs/2026-11-08-aisb-ai-tool-discovery-design.md`. Plan: `docs/superpowers/plans/2026-11-08-mainstreet-ai.md`.

## Layout

| Path | What it is |
|---|---|
| `web/` | Next.js app on Vercel: intake, needs, compare, preview, setup; static catalog and demo businesses |
| `api/` | FastAPI on the Mac (`msapi`): owner workspaces, sandboxed agent turns, approvals, iMessage endpoint |
| `sandbox/` | Docker image the agent runs in: Claude Code with a fixed `settings.json`, `CLAUDE.md`, skills, and the tool CLIs in `sandbox/tools` (`mstools`) |
| `catalog/` | Offline pipeline (`mscatalog`): discover, read, extract, vet, human review, export `catalog.json` |
| `demo-sites/` | Five fictional Maryland business websites, deployed as their own static Vercel project |
| `imessage/` | Photon relay from iMessage to the API |
| `scripts/` | `live.sh` (tunnel, deploy, relay) and `prerun_demos.py` |

This folder holds only the hackathon work (branch `aisb` of IshaanKalra2103/tiny-fish-gtm-automation). Loopcast, the TinyFish GTM app it grew from, lives on `main` in ~/Documents/projects/tiny-fish-gtm-automation.

## Run it

```bash
uv sync
uv run pytest                 # all Python tests
./scripts/live.sh             # API + Cloudflare tunnel + Vercel env + iMessage relay
./scripts/live.sh stop
```

Keys come from the macOS Keychain: `TINYFISH_API_KEY`, `OPENROUTER_API_KEY`, `AGENTMAIL_API_KEY`, `AISB_CLAUDE_OAUTH`.
