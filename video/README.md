# Demo film engine

Renders the MainStreet AI demo film from one edit list, `film.toml`, with fframes (Rust, Skia on
Metal, ffmpeg). Output: 1920x1080, 30 fps, H.264 + AAC stereo mp4.

Two steps:

1. `prep.py` reads `film.toml` and turns every source into intermediates in `build/media/`:
   trimmed, speed-adjusted, constant 30 fps H.264 clips already cropped/fitted for their layout,
   and 48 kHz stereo wav files, loudness-normalised per file (voice to -16 LUFS). It writes
   `build/plan.json`. It caches by ffmpeg command + source size/mtime, so re-running after an
   edit only rebuilds what changed.
2. The `film` binary reads `build/plan.json` and places everything: cards, frames, lower thirds,
   fades, audio. It refuses to run if `film.toml` changed after the last prep.

## Run

```sh
cd video
cp film.example.toml film.toml        # then edit; paths are relative to film.toml
./make.sh film.toml out.mp4           # = prep + cargo build --release + render
```

Or by hand:

```sh
uv run prep.py film.toml
cargo build --release
FILM=film.toml ./target/release/film render -o out.mp4
```

`FILM` defaults to `film.toml`. Footage goes in `../footage/` (gitignored), e.g.
`file = "../footage/c1.mov"`. `CRF=16` before `render` for higher quality (default 18).

## Checking

Scenes are named `sNN_kind[_style]` (e.g. `s03_card_number`). `timeline` lists them.

```sh
R="env FILM=film.toml ./target/release/film"
$R timeline                                  # segments, times, audio tracks
$R frame s03_card_number@2s -o build/qa      # one frame (also: 95.5s, 1200, 50%)
$R frame "s01_clip@1s,s05_screen@end" -o build/qa
$R render 1:20..1:40 -o build/part.mp4       # a range (audio cut to match)
$R render s07_screen -o build/s07.mp4        # one segment
$R audio analyze                             # loudness: aim -14 LUFS, true peak < -1 dBTP
$R audio at s02_split@5s                     # what plays at a moment
$R inspect                                   # missing media / fonts / clipped text
ffmpeg -i out.mp4 -vf "fps=2,scale=320:-1,tile=8x5" build/qa/sheet_%02d.png
```

## film.toml

Top level (both optional):

```toml
music = { file = "../footage/music.mp3", gain_db = -20 }   # ducked under all voice and clip audio
master_gain_db = 2.0                                        # final loudness trim (default 2.0)
```

Then one `[[seg]]` per segment, in order. Every segment can have `fade = 0.3` (crossfade from
the previous segment, eaten from the end of the previous one) and `caption = "..."` (a pill at the
bottom; not on cards). Cuts are hard by default. A section card gets a short dip to black.

`vo` and `sfx` lists work on every kind: `{ file, at, gain_db }`, `at` in seconds from the
segment start. VO is loudness-normalised and ducks the music; sfx is not normalised and defaults to
`gain_db = -10`.

### clip: talking head, its own audio plays

```toml
[[seg]]
kind = "clip"
file = "../footage/c1.mov"
in = 3.2                  # seconds in the source
out = 18.0                # optional: default end of file
lower_third = { name = "Ishaan Kalra", line = "Team Forge" }   # first 4 s (dur = 4 to change)
gain_db = 0               # optional trim on the clip's audio
```

Landscape footage is scaled to cover 1920x1080. Portrait footage is shown at full height over a
blurred, darkened copy of itself. Rotation metadata is respected; mono audio plays on both
channels.

Timeline beside a talking head: add `panel`, the clip takes the left 55%:

```toml
panel = { title = "The next 16 weeks", blocks = [
  { label = "Weeks 1-4",   title = "Real owners", line = "20 Maryland businesses with the SBDC", at = 0.5 },
  { label = "Weeks 5-8",   title = "The catalog", line = "Playbooks, reviews, monitoring",        at = 9.0 },
  { label = "Weeks 9-12",  title = "Scale",       line = "Hosted sandboxes, sign-in, Spanish",    at = 18.0 },
  { label = "Weeks 13-16", title = "People",      line = "Local helpers, SBDC distribution",      at = 27.0 },
] }
```

`at` is seconds from the segment start; blocks without `at` are spread evenly.

### split: two people side by side

```toml
[[seg]]
kind = "split"
dur = 8.5
left  = { file = "../footage/a.mov", in = 2.0, out = 6.4, audio_at = 0.2 }
right = { file = "../footage/b.mov", in = 1.0, out = 5.0, audio_at = 4.5 }
```

Each side is center-cropped to 958x1080 with a 4 px dark gap. Each side's audio (`in`..`out`)
plays at `audio_at` seconds into the segment, and that side's picture is shifted to stay in lip
sync (before and after the line it shows the footage around it, frozen if the file runs out).
Several lines per side: replace `in/out/audio_at` with
`lines = [{ in = 2.0, out = 4.1, at = 0.2 }, { in = 9.0, out = 12.5, at = 6.0 }]`.

### screen: screen recording, its own audio muted

```toml
[[seg]]
kind = "screen"
file = "../footage/intake.mov"
in = 10.0
out = 70.0
speed = 4.0                      # optional; segment length = (out - in) / speed
caption = "Sped up 4x"           # optional
vo = [{ file = "../footage/v3.wav", at = 0.5 }]
zoom = { x = 0.55, y = 0.1, w = 0.4, h = 0.4, at = 2.0, dur = 1.2, until = 9.0 }
full = false                     # true: fill the frame instead of the rounded screen frame
```

The recording sits in a rounded frame on the dark background (about 90% width; phone recordings
are fitted by height). `zoom` region is in fractions of the recording (0..1): an eased push-in
starting at `at` over `dur` seconds, held, and eased back out at `until` (optional).
`dur = ...` on the segment overrides its length (the last frame is held).

### card: designed full-frame cards

`dur` is optional on every card: without it the card lasts until the last `vo` ends + 0.6 s
(3 s for a section, 6 s for credits, 4 s otherwise).

```toml
[[seg]]
kind = "card"
style = "section"
eyebrow = "Part 1 of 4"
title = "The MVP: a working product"
subtitle = "optional line"

[[seg]]
kind = "card"
style = "number"
figure = "27%"
line = "of calls to home-services businesses go unanswered"
source = "Source: Invoca"
vo = [{ file = "../footage/v1.wav", at = 0.3 }]

[[seg]]
kind = "card"
style = "pair"
left  = { figure = "1 in 5", line = "U.S. businesses used AI in the past two weeks" }
right = { figure = "22%",    line = "of firms not planning to use AI don't know what it can do" }
source = "Source: U.S. Census Bureau, BTOS"

[[seg]]
kind = "card"
style = "bullets"
title = "What the agent does"
check = true                       # default check mark for every line (else an accent dot)
items = [
  "Reads the business",            # plain strings, spread evenly...
  { text = "Compares tools", at = 2.4, check = false },   # ...or with their own time / mark
]                                   # up to 6

[[seg]]
kind = "card"
style = "timeline"
title = "The next 16 weeks"
blocks = [{ label = "Weeks 1-4", title = "Real owners", line = "...", at = 0.5 }, ...]   # 4 blocks

[[seg]]
kind = "card"
style = "image"
file = "../docs/video/architecture.png"   # full frame, fitted, slow 1.0 -> 1.06 push-in
pad = 0                                   # optional margin in px

[[seg]]
kind = "card"
style = "credits"
title = "Team Forge"
names = ["Ishaan Kalra", "Dylan ..."]
coach = "Coached by ..."                  # optional
url = "https://mainstreet-ai-five.vercel.app"   # default
```

### broll: like clip, muted by default

```toml
[[seg]]
kind = "broll"
file = "../footage/imessage.mov"
in = 0.0
out = 12.0
audio = false            # true to keep its own sound
vo  = [{ file = "../footage/v5.wav", at = 0.5 }]
sfx = [{ file = "../footage/ding.wav", at = 3.2, gain_db = -12 }]
```

## Look

Charcoal background, off-white Inter (fonts in `media/`), one orange accent (#f08a3c). Titles
rise 20 px and fade in with a spring; bullets and timeline blocks reveal on their `at` times.

## Speed

Measured on the placeholder edit list (80.6 s, every kind): prep 12 s from cold, render 31 s
(frames drawn on the GPU with Skia Metal; most of the time is libx264 at preset fast, CRF 18).
A 10-minute film renders in roughly 4 minutes.

## Known limits

- The libav that fframes links has no `h264_videotoolbox`, so the final encode is libx264 (CPU).
- Audio is mixed at 44.1 kHz AAC 192 kb/s (fframes default).
- Loudness is normalised per file, then summed; check `audio analyze` on the real cut and use
  `master_gain_db` if it lands more than 1 LU off -14.
- Fades eat into the end of the previous segment; the previous segment's sound keeps playing
  under the fade.
