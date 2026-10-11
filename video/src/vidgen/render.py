"""Spec -> 1080x1920 H.264 short, in one ffmpeg pass.

Formats (see SKILL.md for the spec fields):
  brainrot   split screen: images/clips on top, gameplay below, word-by-word captions on the seam
  story      Reddit-story: post card while the title is read, then captions over full-screen gameplay
  slideshow  full-screen images with slow zooms, hook banner, captions
  listicle   ranked "#N" items over full-screen images, title intro, captions
"""

import json
import re
import shutil
import sys
import time
from pathlib import Path

from PIL import Image

from . import footage, graphics, images
from .config import FPS, H, W, VidgenError, run, tool
from .tts import ElevenLabs, Word

FORMATS = {
    "brainrot": "split screen: images on top, gameplay below, 1-2 word pop captions on the seam",
    "story": "Reddit story: post card while the title is read, then captions over full-screen gameplay",
    "slideshow": "full-screen images with slow zooms, hook banner, 3-word captions",
    "listicle": "ranked #N items with labels over full-screen images, title intro, captions",
}

DEFAULTS = {
    "brainrot": {"shot_seconds": 1.8, "caption_words": 2, "caption_y": 960, "read_title": False, "speed": 1.12},
    "story": {"shot_seconds": 0, "caption_words": 3, "caption_y": 900, "read_title": True, "speed": 1.1},
    "slideshow": {"shot_seconds": 3.0, "caption_words": 3, "caption_y": 1380, "read_title": False, "speed": 1.05},
    "listicle": {"shot_seconds": 3.5, "caption_words": 3, "caption_y": 1420, "read_title": True, "speed": 1.08},
}

VIDEO_EXT = {".mp4", ".mov", ".webm", ".mkv", ".m4v"}


def log(msg: str) -> None:
    print(f"[render] {msg}", file=sys.stderr)


def sentences(text: str) -> list[str]:
    parts = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))
    return [p for p in parts if p]


def normalize(spec: dict) -> dict:
    fmt = spec.get("format", "brainrot")
    if fmt not in FORMATS:
        raise VidgenError(f"unknown format {fmt!r}; one of {sorted(FORMATS)}")
    s = {**DEFAULTS[fmt], **spec, "format": fmt}
    segs = list(s.get("segments") or [])
    if not segs and s.get("script"):
        segs = [{"text": t} for t in sentences(s["script"])]
    if not segs:
        raise VidgenError("spec needs `segments` (list of {text, ...}) or `script`")
    for seg in segs:
        if not str(seg.get("text", "")).strip():
            raise VidgenError("every segment needs non-empty `text`")
    s["segments"] = segs
    if s["read_title"] and not s.get("title"):
        s["read_title"] = False
    return s


def _parts(s: dict) -> list[dict]:
    """Narration parts in reading order: optional title, then each segment."""
    parts = [{"kind": "title", "text": s["title"]}] if s["read_title"] else []
    parts += [{"kind": "segment", "index": i, "text": seg["text"], "seg": seg} for i, seg in enumerate(s["segments"])]
    return parts


def _time_parts(parts: list[dict], words: list[Word], total: float) -> None:
    counts = [len(p["text"].split()) for p in parts]
    if len(words) == sum(counts):
        idx = 0
        for p, c in zip(parts, counts):
            p["words"] = words[idx: idx + c]
            idx += c
    else:  # alignment split words differently: fall back to proportional split
        log(f"word count mismatch ({len(words)} vs {sum(counts)}), splitting proportionally")
        acc = 0
        for p, c in zip(parts, counts):
            lo, hi = round(acc / sum(counts) * len(words)), round((acc + c) / sum(counts) * len(words))
            p["words"] = words[lo:hi] or words[lo: lo + 1]
            acc += c
    for i, p in enumerate(parts):
        p["start"] = 0.0 if i == 0 else graphics.snap(p["words"][0].start)
    for i, p in enumerate(parts):
        p["end"] = parts[i + 1]["start"] if i + 1 < len(parts) else total


def _media_for(part: dict, s: dict, n: int) -> tuple[list[Path], list[dict]]:
    """Image (or clip) paths for one narration part, plus their source records."""
    seg = part.get("seg") or (s["segments"][0] if s["segments"] else {})
    if part["kind"] == "title" and s.get("title_query"):
        seg = {"query": s["title_query"]}
    if seg.get("video"):
        return [Path(seg["video"]).expanduser()], [{"video": seg["video"]}]
    given = seg.get("images") or ([seg["image"]] if seg.get("image") else [])
    if given:
        paths = [images.fetch_url(g) if re.match(r"^https?://", g) else Path(g).expanduser() for g in given]
        return paths, [{"image": g} for g in given]
    query = seg.get("query") or s.get("query") or (s.get("title") or seg["text"])[:80]
    found = []
    for q in _fallbacks(query, s):
        try:
            found = images.acquire(q, n=max(n, 1), license=s.get("license", "any"))
            break
        except VidgenError as e:
            log(f"{e}; trying a broader query")
    if not found:
        raise VidgenError(f"no usable images for {query!r} or its fallbacks")
    return [Path(f["path"]) for f in found], [{k: f[k] for k in ("url", "page", "title", "engine", "query")}
                                              for f in found]


def _fallbacks(query: str, s: dict) -> list[str]:
    """The query, then broader versions of it, then the spec-wide query or title."""
    words = [w for w in query.split() if w.lower() not in images.STOP]
    out = [query, " ".join(words), " ".join(words[:2]), s.get("query"), s.get("title")]
    return [q for q in dict.fromkeys(out) if q]


def _shots(parts: list[dict], s: dict, region: tuple[int, int], work: Path) -> list[dict]:
    """Cut each part into shots of ~shot_seconds, cycling that part's images."""
    shots = []
    for p in parts:
        dur = p["end"] - p["start"]
        n = max(1, round(dur / s["shot_seconds"])) if s["shot_seconds"] else 1
        paths, sources = _media_for(p, s, n)
        p["sources"] = sources
        for k in range(n):
            a = graphics.snap(p["start"] + dur * k / n)
            b = graphics.snap(p["start"] + dur * (k + 1) / n)
            path = paths[k % len(paths)]
            shots.append({"start": a, "frames": round(b * FPS) - round(a * FPS), "path": path,
                          "video": path.suffix.lower() in VIDEO_EXT, "zoom_in": len(shots) % 2 == 0})
    # prepare stills at 1.5x the region so zoompan has sub-pixel headroom
    big = (int(region[0] * 1.5), int(region[1] * 1.5))
    for i, sh in enumerate(shots):
        if not sh["video"]:
            out = work / f"shot_{i:03d}.jpg"
            with Image.open(sh["path"]) as im:
                graphics.cover(im.convert("RGB"), big).save(out, quality=90)
            sh["prepared"] = out
    return [sh for sh in shots if sh["frames"] > 0]


def _caption_layers(parts: list[dict], s: dict) -> tuple[list[graphics.Layer], list[tuple[float, float, str]]]:
    layers, srt = [], []
    k, y = int(s["caption_words"]), int(s["caption_y"])
    color, hl = s.get("caption_color", "#FFFFFF"), s.get("highlight_color", "#FFE600")
    size = int(s.get("caption_size", 104 if k <= 2 else 88))
    for p in parts:
        if p["kind"] == "title" and s["format"] in ("story", "listicle"):
            continue  # the card / title banner carries it
        words = p["words"]
        chunks, cur = [], []
        for w in words:
            cur.append(w)
            if len(cur) >= k or re.search(r"[.!?,;:]$", w.text):
                chunks.append(cur)
                cur = []
        if cur:
            chunks.append(cur)
        for ci, chunk in enumerate(chunks):
            texts = [re.sub(r"[^\w'%$#@&+-]", "", w.text) or w.text for w in chunk]
            nxt = chunks[ci + 1][0].start if ci + 1 < len(chunks) else min(p["end"], chunk[-1].end + 0.35)
            srt.append((chunk[0].start, nxt, " ".join(w.text for w in chunk)))
            for wi, w in enumerate(chunk):
                a = w.start
                b = chunk[wi + 1].start if wi + 1 < len(chunk) else nxt
                active = wi if len(chunk) > 1 else None
                if wi == 0:  # pop in: 85% -> 108% -> 100%
                    for j, sc in enumerate((0.85, 1.08)):
                        layers.append(graphics.Layer(a + j / FPS, a + (j + 1) / FPS,
                                                     [graphics.caption(texts, active, y, size, sc, color, hl)], z=10))
                    a += 2 / FPS
                if b > a:
                    layers.append(graphics.Layer(a, b, [graphics.caption(texts, active, y, size, 1.0, color, hl)], z=10))
    return layers, srt


def _format_layers(parts: list[dict], s: dict) -> list[graphics.Layer]:
    fmt, layers = s["format"], []
    title_part = parts[0] if parts and parts[0]["kind"] == "title" else None
    if fmt == "story" and title_part:
        layers.append(graphics.Layer(0, title_part["end"], [graphics.reddit_card(
            s["title"], s.get("subreddit", "r/AskReddit"), s.get("author", "u/throwaway_8812"),
            int(s.get("upvotes", 24100)), int(s.get("comments", 3200)))], z=5))
    if fmt in ("slideshow", "listicle"):
        layers.append(graphics.Layer(0, parts[-1]["end"], [graphics.gradient()], z=0))
    if fmt == "listicle":
        if title_part:
            layers.append(graphics.Layer(0, title_part["end"], [graphics.banner(s["title"], 330)], z=5))
        items = [p for p in parts if p["kind"] == "segment"]
        for rank, p in enumerate(items):
            n = len(items) - rank if s.get("countdown", True) else rank + 1
            layers.append(graphics.Layer(p["start"], p["end"], graphics.badge(n, p["seg"].get("label")), z=5))
    if fmt == "slideshow" and s.get("title"):
        layers.append(graphics.Layer(0, min(3.0, parts[-1]["end"]), [graphics.banner(s["title"], 330)], z=5))
    if fmt == "brainrot" and s.get("title"):
        layers.append(graphics.Layer(0, min(2.6, parts[-1]["end"]), [graphics.banner(s["title"], 150, size=50)], z=5))
    return layers


def _srt(entries: list[tuple[float, float, str]], path: Path) -> None:
    def ts(t: float) -> str:
        ms = int(round(t * 1000))
        return f"{ms // 3600000:02d}:{ms // 60000 % 60:02d}:{ms // 1000 % 60:02d},{ms % 1000:03d}"
    path.write_text("".join(f"{i}\n{ts(a)} --> {ts(b)}\n{t}\n\n" for i, (a, b, t) in enumerate(entries, 1)))


def render(spec: dict, out: Path, work: Path | None = None) -> dict:
    t0 = time.time()
    s = normalize(spec)
    fmt = s["format"]
    out.parent.mkdir(parents=True, exist_ok=True)
    work = work or out.parent / f".{out.stem}_work"
    if work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True)

    # 1. voiceover, one call for the whole script (cached)
    parts = _parts(s)
    tts = ElevenLabs()
    speech = tts.speak(" ".join(p["text"] for p in parts), voice=s.get("voice"), model=s.get("model"),
                       speed=float(s["speed"]), stability=float(s.get("stability", 0.45)),
                       style=float(s.get("style", 0.0)))
    log(f"voiceover {speech.duration:.1f}s, {speech.chars} chars ({'cached' if speech.cached else 'new'})")
    total = graphics.snap(speech.duration + 0.4)
    _time_parts(parts, speech.words, total)

    # 2. visuals
    uses_images = fmt != "story"
    uses_game = fmt in ("brainrot", "story")
    region = (W, H // 2) if fmt == "brainrot" else (W, H)
    shots = _shots(parts, s, region, work) if uses_images else []
    game, game_offset = None, 0.0
    if uses_game:
        game = footage.resolve(s.get("gameplay", "minecraft"))
        game_offset = footage.pick_offset(game, total, s.get("seed"))
    log(f"{len(shots)} shots, gameplay={game.name if game else None}")

    # 3. overlays
    cap_layers, srt = _caption_layers(parts, s)
    track = graphics.write_track(cap_layers + _format_layers(parts, s), total, work / "overlay")

    # 4. one ffmpeg pass
    args, filters, n = [tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y"], [], 0
    rw, rh = region
    labels = []
    for sh in shots:
        d = sh["frames"] / FPS
        if sh["video"]:
            args += ["-stream_loop", "-1", "-t", f"{d:.4f}", "-i", str(sh["path"])]
            filters.append(f"[{n}:v]scale={rw}:{rh}:force_original_aspect_ratio=increase,crop={rw}:{rh},"
                           f"fps={FPS},setsar=1,format=yuv420p,trim=end_frame={sh['frames']},setpts=PTS-STARTPTS[s{n}]")
        else:
            args += ["-loop", "1", "-framerate", str(FPS), "-t", f"{d:.4f}", "-i", str(sh["prepared"])]
            z = f"1+0.10*on/{sh['frames']}" if sh["zoom_in"] else f"1.10-0.10*on/{sh['frames']}"
            filters.append(f"[{n}:v]zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s={rw}x{rh}:fps={FPS},"
                           f"setsar=1,format=yuv420p,trim=end_frame={sh['frames']},setpts=PTS-STARTPTS[s{n}]")
        labels.append(f"[s{n}]")
        n += 1
    if shots:
        filters.append(f"{''.join(labels)}concat=n={len(labels)}:v=1:a=0[media]")
    if game:
        gh = H // 2 if fmt == "brainrot" else H
        args += ["-stream_loop", "-1", "-ss", f"{game_offset:.2f}", "-t", f"{total:.4f}", "-i", str(game)]
        filters.append(f"[{n}:v]scale={W}:{gh}:force_original_aspect_ratio=increase,crop={W}:{gh},"
                       f"fps={FPS},setsar=1,format=yuv420p,setpts=PTS-STARTPTS[game]")
        n += 1
    if fmt == "brainrot":
        top, bottom = ("[game]", "[media]") if s.get("gameplay_on_top") else ("[media]", "[game]")
        filters.append(f"{top}{bottom}vstack=inputs=2[base]")
    else:
        filters.append(f"{'[game]' if fmt == 'story' else '[media]'}null[base]")
    args += ["-f", "concat", "-safe", "0", "-i", str(track)]
    filters.append(f"[{n}:v]fps={FPS}[ov];[base][ov]overlay=0:0:eof_action=repeat:format=auto,format=yuv420p[v]")
    n += 1
    args += ["-i", str(speech.audio)]
    voice_i = n
    n += 1
    if s.get("music"):
        track_path = footage.music(s["music"])
        args += ["-stream_loop", "-1", "-i", str(track_path)]
        vol = float(s.get("music_volume", 0.12))
        filters.append(f"[{n}:a]volume={vol},afade=t=out:st={max(0, total - 1.5):.2f}:d=1.5[mus];"
                       f"[{voice_i}:a]apad[vo];[vo][mus]amix=inputs=2:duration=first:normalize=0[a]")
        n += 1
    else:
        filters.append(f"[{voice_i}:a]apad[a]")
    args += ["-filter_complex", ";".join(filters), "-map", "[v]", "-map", "[a]", "-t", f"{total:.4f}",
             "-r", str(FPS), "-c:v", "libx264", "-preset", s.get("preset", "veryfast"), "-crf", str(s.get("crf", 21)),
             "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "160k", "-ar", "44100", "-movflags", "+faststart", str(out)]
    log(f"ffmpeg: {n} inputs, {total:.1f}s")
    run(args, "ffmpeg render")

    # 5. sidecars: captions, thumbnail, metadata
    srt_path, thumb = out.with_suffix(".srt"), out.with_suffix(".jpg")
    _srt(srt, srt_path)
    run([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", f"{min(1.0, total / 2):.2f}", "-i", str(out),
         "-frames:v", "1", "-q:v", "3", str(thumb)], "thumbnail")
    meta = {
        "format": fmt, "duration": total, "path": str(out), "captions": str(srt_path), "thumbnail": str(thumb),
        "voice_id": speech.voice_id, "tts_chars": speech.chars, "tts_cached": speech.cached,
        "gameplay": {"clip": game.name, "offset": game_offset} if game else None,
        "parts": [{"kind": p["kind"], "text": p["text"], "start": p["start"], "end": p["end"],
                   "sources": p.get("sources", [])} for p in parts],
        "spec": spec, "render_seconds": round(time.time() - t0, 1),
    }
    out.with_suffix(".json").write_text(json.dumps(meta, indent=1))
    if not s.get("keep_work"):
        shutil.rmtree(work, ignore_errors=True)
    return meta


def next_version(folder: Path, stem: str = "video") -> Path:
    nums = [int(m.group(1)) for p in folder.glob(f"{stem}_v*.mp4") if (m := re.search(r"_v(\d+)\.mp4$", p.name))]
    return folder / f"{stem}_v{max(nums, default=0) + 1}.mp4"


def estimate_chars(spec: dict) -> int:
    s = normalize(spec)
    return len(" ".join(p["text"] for p in _parts(s)))

