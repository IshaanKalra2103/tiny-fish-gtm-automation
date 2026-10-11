---
name: short-video
description: Produce the campaign's short vertical video. For the demo, caption one of five ready-made 22-second template clips with a punchy hook, 3-5 caption lines and a CTA (no generation, seconds to run). Use for the Content Generation (video) step of a GTM campaign.
---

# Short video

## Demo mode (use this for now): caption a template

No new footage is generated. Pick one of five pre-rendered 22s 1080x1920 clips, each with a beat, and burn catchy captions onto it.

| template | look |
|---|---|
| `parkour` | full-screen Minecraft parkour (brainrot classic) |
| `split` | TinyFish site on top, parkour below |
| `neon` | animated neon gradient |
| `matrix` | orange Game-of-Life grid on black, techy |
| `product` | slow, dimmed scroll down the GTM campaign dashboard |

```sh
uv run --project /workspace/video vidgen template make --campaign <campaign> \
  --hook "Your AI agent got stuck again?" \
  --line "TinyFish agents browse real sites" --line "Search fetch and click at scale" --line "Live data no scripts" \
  --cta "Try TinyFish free" [--template auto|parkour|split|neon|matrix|product]
```

- **Hook:** shown for 0-3s, at most 8 words.
- **Caption lines:** 3-5 of them, at most 7 words each, evenly timed. The longest word in each line pops in the accent colour.
- **CTA:** shown for the last 3.5s, above a `tinyfish.ai` tag.
- **Template:** `auto` picks one consistently from the text. Name one to choose it yourself.
- **Output:** one JSON line, `{"ok": true, "path": ".../runs/<campaign>/video_vN.mp4", "template": ..., "thumbnail": ...}`. Post the path on your issue.

Write the captions from the campaign script and evidence. Keep claims to what the evidence supports.

`vidgen template list` shows the templates. The base clips live in `/workspace/video/templates/`, and `vidgen template build` re-renders them on the host.

## Later: generate with Vizard (refs + prompt, uses credits)

1. Make 2-4 reference images with your own image generation (e.g. Codex's image tool).
2. Run:

```sh
uv run --project /workspace/video vidgen vizard make --campaign <campaign> --prompt "<hook, message, CTA, style, what each ref is>" \
  --ref /workspace/runs/<campaign>/refs/1.png [--ref ...] [--seconds 22] [--tier flash|pro|max|ultra]
```

Vizard does the visuals, voiceover, music and captions, and the result is clamped to 20-25s.

- `{"ok": false, "question": ...}`: run `vidgen vizard send <project_id> --message "<answer>"`, then `vidgen vizard status <project_id> --wait 600 --download --campaign <campaign>`.
- Revisions use the same `send` + `status` pair.
- Auth is `video/.vizard/session.json`, handled by the tool.

## Notes

- **From inside another uv-run process** (e.g. a `gtm` worker), prefix with `env -u UV_PROJECT_ENVIRONMENT`. Otherwise uv syncs vidgen's dependencies over the caller's venv.
- **ffmpeg:** found on PATH, or, in the harness container, the static build bundled with imageio-ffmpeg in a venv. Override it with `VIDGEN_FFMPEG`.
