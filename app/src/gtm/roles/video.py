"""Content Generation: script -> voiceover (OpenAI TTS) -> word timestamps -> 1080x1920 MP4.

Layout keeps text off the product (persona QA kept flagging captions over the UI): a title band at the top, the
brand screenshot (TinyFish Browser) in its own framed panel that slowly scrolls like a screen recording, and captions
in a dedicated zone below the panel.
"""

import json
import os
import platform
import shutil
import subprocess
from pathlib import Path

import numpy as np
from moviepy import AudioFileClip, ColorClip, CompositeVideoClip, ImageClip
from PIL import Image, ImageDraw, ImageFont

from .. import config, llm
from ..run import Run

ROLE = "video"
W, H = 1080, 1920
PANEL_X, PANEL_Y, PANEL_W, PANEL_H = 50, 470, 980, 960  # product area; nothing else is drawn over it
ORANGE, INK = (255, 106, 0), (16, 16, 24)
FONTS = ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"]


def run(r: Run) -> str:
    with r.timer(ROLE):
        info = render(r, 1)
    return f"video_v1.mp4: {info['seconds']}s, voice={info['voice']}"


VIDGEN = Path(os.environ.get("GTM_VIDGEN_PROJECT", Path(__file__).resolve().parents[4] / "video"))


def render(r: Run, version: int) -> dict:
    """B2C short via vidgen (talking-head / product / brainrot); the built-in renderer is the safety net."""
    try:
        return _render_vidgen(r, version)
    except Exception as e:  # never lose the demo to a video-tool hiccup
        r.log(ROLE, f"vidgen failed, using built-in renderer: {str(e)[:300]}", version=version)
        return _render_moviepy(r, version)


def _render_vidgen(r: Run, version: int) -> dict:
    s, brief = r.read(f"script_v{version}.json"), r.brief
    themes = r.read("insights.json").get("themes", []) if r.exists("insights.json") else []
    first = themes[0] if themes else {}
    trend = (first.get("name") or first.get("theme") or str(first)[:80]) if first else brief.get("niche", "")
    fmt = os.environ.get("GTM_VIDEO_FORMAT", "talking-head")
    lines = [sc["on_screen_text"] for sc in s["scenes"] if sc.get("on_screen_text")
             and sc["on_screen_text"].strip().lower() != s["cta"].strip().lower()][:4]
    out = r.path(f"video_v{version}.mp4")
    shots = [r.dir / p for p in r.read("evidence.json").get("shots", [])] if r.exists("evidence.json") else []
    person = r.dir / "refs" / "video_v1_ref1.png"  # reuse v1's Codex-drawn face across revisions
    shot = ["--ref", str(shots[0])] if shots else []
    attempts = [(fmt, shot)]
    if fmt == "talking-head":  # Codex draws the face once; if that fails, a product ad off the evidence shot
        face = (["--ref", str(person)] if person.exists() else
                ["--person", f"a relatable creator in their 20s, one of {brief.get('audience', 'the target audience')}, "
                             f"filming a selfie video about {brief['brand']}, natural light, TikTok UGC look"])
        attempts = [(fmt, face), ("product", shot)]
    env = {k: v for k, v in os.environ.items() if k != "UV_PROJECT_ENVIRONMENT"}  # don't sync over app's venv
    for fmt, ref in attempts:
        cmd = ["uv", "run", "--project", str(VIDGEN), "vidgen", "ad", fmt, "--out", str(out), "--brand", brief["brand"],
               "--trend", trend, "--hook", s["hook"], *[a for ln in lines for a in ("--line", ln)], "--cta", s["cta"],
               *ref, "--mode", os.environ.get("GTM_VIDEO_MODE", "demo")]
        p = subprocess.run(cmd, capture_output=True, text=True, env=env, timeout=1800)
        res = json.loads((p.stdout.strip().splitlines() or ["{}"])[-1] or "{}")
        if res.get("ok"):
            break
        r.log(ROLE, f"vidgen {fmt} failed: {str(res.get('error') or p.stderr.strip()[-200:])[:300]}", version=version)
    if not res.get("ok"):
        raise RuntimeError(res.get("error") or p.stderr.strip()[-300:] or "vidgen returned no result")
    shown = [s["hook"], *lines, s["cta"]]
    info = {"version": version, "path": out.name, "seconds": float(res.get("duration") or res.get("target_seconds") or 22),
            "voice": "vizard voiceover" if res.get("mode") == "vizard" else "none (beat + captions)",
            "words": len(" ".join(shown).split()), "transcript": " / ".join(shown) + " [on-screen captions]",
            "frames": _qa_frames(r, out, version), "format": fmt, "mode": res.get("mode"), "engine": "vidgen"}
    r.write(f"video_v{version}.json", info)
    r.log(ROLE, f"vidgen {fmt} video_v{version}.mp4 ({info['seconds']}s, {info['mode']})", version=version)
    return info


def _render_moviepy(r: Run, version: int) -> dict:
    s = r.read(f"script_v{version}.json")
    shots = [r.dir / p for p in r.read("evidence.json").get("shots", [])]
    segments = _segments(s)
    spoken = " ".join(t for t, _ in segments)

    audio_path, words, voice = _voiceover(r, spoken, version)
    audio = AudioFileClip(str(audio_path))
    dur = audio.duration
    bounds = _scene_bounds(segments, words, len(s["scenes"]), dur)

    layers = [ColorClip((W, H), color=INK, duration=dur)]
    for i, (t0, t1) in enumerate(bounds):
        scene = s["scenes"][i]
        layers.append(_panel(shots, scene["shot"], t1 - t0).with_start(t0).with_position((PANEL_X, PANEL_Y)))
        title = s["hook"] if i == 0 else scene["on_screen_text"]
        layers.append(ImageClip(_title_band(title, hook=(i == 0))).with_start(t0).with_duration(t1 - t0).with_position((0, 0)))
    for text, a, b in _caption_chunks(words):
        layers.append(ImageClip(_caption_box(text)).with_start(a).with_duration(max(b - a, 0.25))
                      .with_position(("center", PANEL_Y + PANEL_H + 40)))
    layers.append(ImageClip(_watermark(r.brief["brand_url"])).with_duration(dur).with_position(("center", 1820)))

    out = r.path(f"video_v{version}.mp4")
    CompositeVideoClip(layers, size=(W, H)).with_duration(dur).with_audio(audio).write_videofile(
        str(out), fps=30, codec="libx264", audio_codec="aac", logger=None)
    frames = _qa_frames(r, out, version)
    info = {"version": version, "path": out.name, "seconds": round(dur, 1), "voice": voice, "words": len(words),
            "transcript": spoken, "frames": frames}
    r.write(f"video_v{version}.json", info)
    r.log(ROLE, f"rendered video_v{version}.mp4 ({info['seconds']}s, {voice})", version=version)
    return info


# ── audio ───────────────────────────────────────────────────────────────
def _segments(s: dict) -> list[tuple[str, int]]:
    segs = []
    first = s["scenes"][0]["voiceover"]
    if s["hook"].lower()[:20] not in first.lower():
        segs.append((s["hook"], 0))
    segs += [(sc["voiceover"], i) for i, sc in enumerate(s["scenes"])]
    if s["cta"].lower()[:20] not in s["scenes"][-1]["voiceover"].lower():
        segs.append((s["cta"], len(s["scenes"]) - 1))
    return segs


def _voiceover(r: Run, text: str, version: int) -> tuple[Path, list[tuple[str, float, float]], str]:
    path = r.path(f"vo_v{version}.mp3")
    try:
        speech = llm.openai_client().audio.speech.create(model=config.TTS_MODEL, voice="alloy", input=text,
                                                  instructions="Confident developer-advocate. Brisk, clear, upbeat.")
        path.write_bytes(speech.read())
        tr = llm.openai_client().audio.transcriptions.create(model="whisper-1", file=path.open("rb"), response_format="verbose_json",
                                                      timestamp_granularities=["word"])
        return path, [(w.word, w.start, w.end) for w in tr.words], config.TTS_MODEL
    except Exception as e:  # offline fallback: system TTS + proportional caption timing
        r.log(ROLE, f"OpenAI TTS failed ({e}); using system voice", level="warn")
        wav = r.path(f"vo_v{version}.wav")
        if platform.system() == "Darwin":
            subprocess.run(["say", "-v", "Samantha", "-r", "185", "-o", str(wav), "--data-format=LEI16@22050", text], check=True)
        elif shutil.which("espeak-ng"):
            subprocess.run(["espeak-ng", "-s", "165", "-w", str(wav), text], check=True)
        else:
            raise
        dur = AudioFileClip(str(wav)).duration
        toks = text.split()
        total = sum(len(t) + 1 for t in toks)
        words, t = [], 0.0
        for tok in toks:
            d = dur * (len(tok) + 1) / total
            words.append((tok, t, t + d))
            t += d
        return wav, words, "system"


def _scene_bounds(segments, words, n_scenes, dur) -> list[tuple[float, float]]:
    """Map script word counts onto the transcript's word timestamps to find where each scene starts."""
    counts = [len(t.split()) for t, _ in segments]
    total, nw = sum(counts), max(len(words), 1)
    starts = {}
    cum = 0
    for (text, scene), c in zip(segments, counts):
        idx = min(int(round(cum / total * nw)), nw - 1)
        starts.setdefault(scene, words[idx][1] if words else 0.0)
        cum += c
    starts[0] = 0.0
    edges = [starts.get(i, 0.0) for i in range(n_scenes)] + [dur]
    return [(edges[i], max(edges[i + 1], edges[i] + 0.5)) for i in range(n_scenes)]


def _caption_chunks(words, n=3):
    for i in range(0, len(words), n):
        g = words[i:i + n]
        yield " ".join(w[0].strip() for w in g).upper(), g[0][1], g[-1][2]


# ── visuals ─────────────────────────────────────────────────────────────
def _font(size: int) -> ImageFont.FreeTypeFont:
    for f in FONTS:
        if Path(f).exists():
            return ImageFont.truetype(f, size)
    return ImageFont.load_default(size)


def _wrap(draw, text, font, width) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=font) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    return lines + [line] if line else lines


def _fit(text, width, size, max_lines):
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    while size > 30:
        font = _font(size)
        lines = _wrap(probe, text, font, width)
        if len(lines) <= max_lines:
            return font, lines
        size -= 6
    return _font(size), _wrap(probe, text, _font(size), width)


def _title_band(text: str, hook: bool) -> np.ndarray:
    font, lines = _fit(text, W - 120, 92 if hook else 80, 3)
    lh = int(font.size * 1.18)
    h = 120 + lh * len(lines)
    img = Image.new("RGBA", (W, h), (*INK, 235))
    d = ImageDraw.Draw(img)
    for i, line in enumerate(lines):
        d.text((W / 2, 60 + i * lh), line, font=font, fill=ORANGE if hook else (255, 255, 255), anchor="ma")
    d.rectangle([0, h - 8, W, h], fill=(*ORANGE, 255))
    return np.array(img)


def _caption_box(text: str) -> np.ndarray:
    font, lines = _fit(text, W - 200, 76, 2)
    lh = int(font.size * 1.2)
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = int(max(probe.textlength(line, font=font) for line in lines)) + 80
    h = lh * len(lines) + 56
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, h - 1], radius=28, fill=(*INK, 225))
    for i, line in enumerate(lines):
        d.text((w / 2, 28 + i * lh), line, font=font, fill=(255, 255, 255), anchor="ma")
    return np.array(img)


def _watermark(url: str) -> np.ndarray:
    font = _font(40)
    label = url.replace("https://", "").replace("www.", "").rstrip("/")
    probe = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
    w = int(probe.textlength(label, font=font)) + 48
    img = Image.new("RGBA", (w, 64), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([0, 0, w - 1, 63], radius=32, fill=(*ORANGE, 240))
    d.text((w / 2, 12), label, font=font, fill=(255, 255, 255), anchor="ma")
    return np.array(img)


def _panel(shots: list[Path], idx: int, dur: float):
    """Screenshot in its own frame, scrolling slowly from the top (reads like a screen recording)."""
    if not shots:
        return ColorClip((PANEL_W, PANEL_H), color=(36, 36, 48), duration=dur)
    img = Image.open(shots[max(0, min(idx, len(shots) - 1))]).convert("RGB")
    img = img.resize((PANEL_W, int(img.height * PANEL_W / img.width)))
    travel = max(min(img.height - PANEL_H, 420), 0)
    shot = ImageClip(np.array(img)).with_duration(dur).with_position(lambda t: (0, -int(travel * min(t / max(dur, 0.1), 1))))
    return CompositeVideoClip([shot], size=(PANEL_W, PANEL_H)).with_duration(dur)


def _qa_frames(r: Run, video: Path, version: int, n: int = 8) -> list[str]:
    from moviepy import VideoFileClip

    clip = VideoFileClip(str(video))
    out = []
    for i in range(n):
        t = clip.duration * (i + 0.5) / n
        p = r.path(f"frames_v{version}/f{i}_{t:.1f}s.jpg")
        Image.fromarray(clip.get_frame(t)).resize((540, 960)).save(p, "JPEG", quality=82)
        out.append(str(p.relative_to(r.dir)))
    clip.close()
    return out
