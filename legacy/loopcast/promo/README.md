# Loopcast promo video

The 57.5 s launch video for Loopcast. It is modelled shot for shot on the DMflo motion-graphics promo (same beats, timing, palette and transitions). The content and numbers are real data from `runs/tinyfish-demo-1` and `runs/TIN-13`.

The video is one HTML page, `index.html`. It renders in headless Chromium, and `seek(t)` is a pure function of time.

## Files

| File | What it does |
|---|---|
| `vo.py` | Records the voiceover as one ElevenLabs take (Sarah, speed 1.15, cached by text and settings), cuts it into lines and places each line at the reference VO's start time. Output: `build/vo.wav` and `build/vo_words.js` (word timings that scenes anchor to with `W('word')`). |
| `music.py` | Scores the music bed with the ElevenLabs Music API: a section-timed plan at 120 BPM, drop at 10 s, breakdown at 50 s, final hit at 54 s. Output: `build/music_<tag>.mp3`. |
| `src/scenes/*.js` | One file per scene: problem, brand, how, team, scan, dash, cli, price, end. Each has `build()` and `update(t)` and registers its own SFX cues. |
| `audio.py` | Synthesises the SFX cues, ducks the music under the VO, cuts the bass on the end card, and writes `build/mix.wav`. |
| `render.py` | Renders stills, contact sheets, cue lists and the full video (8 parallel Chromium workers, 4-sample motion blur). |
| `motion_stats.py` | Measures the share of frames that move and the longest still hold, so the cut can be checked against the reference. |

## Rebuild

```bash
uv run vo.py take && uv run vo.py place      # only if the script changes (costs ElevenLabs characters)
uv run render.py cues && uv run audio.py a   # SFX cues -> mix
uv run render.py full --workers 8 --sub 4    # about 25 min -> build/video.mp4
ffmpeg -i build/video.mp4 -i build/mix.wav -c:v copy -c:a aac -b:a 256k \
  -af loudnorm=I=-14:TP=-1.0:LRA=11 -shortest -movflags +faststart build/loopcast-promo.mp4
```

## Previewing

- **In the browser:** serve this folder (`python -m http.server`), then open `index.html?t=12`. Space plays with audio; the arrow keys step one frame, and Shift+arrow steps one second.
- **Stills and sheets:** `uv run render.py at 12.4 30` writes stills, and `uv run render.py sheet 10 14 10 8` writes a contact sheet.
- **Corner HUD:** add `--hud` or `?hud=1`. It is off by default.
