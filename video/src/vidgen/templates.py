"""Demo video templates: five pre-rendered 22s vertical clips with a beat, plus catchy captions.

For the demo nothing new is generated: `make` picks one of the five base clips and burns a hook,
caption lines and a CTA onto it (Pillow-drawn text, one ffmpeg overlay pass, audio copied).
`build` renders the base clips once from local sources; they live in video/templates/.
"""

import hashlib
import shutil
import tempfile
from pathlib import Path

from . import graphics
from .config import FPS, H, PACKAGE_ROOT, VidgenError, W, run, tool
from .graphics import Layer

DIR = PACKAGE_ROOT / "templates"
SRC = DIR / "src"
SECONDS = 22.0
GAMEPLAY = PACKAGE_ROOT / "assets" / "gameplay" / "prepared" / "minecraft.mp4"

# name -> what it looks like, where captions sit, highlight colour
TEMPLATES = {
    "parkour": {"look": "full-screen Minecraft parkour (brainrot classic)", "caption_y": 960, "accent": "#FFE600"},
    "split": {"look": "TinyFish site on top, parkour below", "caption_y": 960, "accent": "#00E5FF"},
    "neon": {"look": "animated neon gradient, kinetic text", "caption_y": 900, "accent": "#FF4FD8"},
    "matrix": {"look": "orange Game-of-Life grid on black, techy", "caption_y": 900, "accent": "#FF6A00"},
    "product": {"look": "slow, dimmed scroll down the GTM campaign dashboard", "caption_y": 1450, "accent": "#FF6A00"},
}

# 120 BPM: kick on every beat, hi-hat on the off-beat, a soft bass note. Generated, so royalty-free.
BEAT = ("aevalsrc='0.55*sin(2*PI*55*t)*exp(-18*mod(t,0.5))"
        "+0.08*(random(0)*2-1)*exp(-70*mod(t+0.25,0.5))"
        "+0.12*sin(2*PI*110*t)*(mod(floor(t/2),2)*0.6+0.4)*exp(-3*mod(t,0.5))'"
        f":s=44100:d={SECONDS}")


def path(name: str) -> Path:
    return DIR / f"{name}.mp4"


def available() -> dict:
    return {n: {**t, "path": str(path(n)), "built": path(n).exists()} for n, t in TEMPLATES.items()}


def pick(seed: str) -> str:
    """Stable choice for 'auto': the same campaign text always gets the same template."""
    names = sorted(TEMPLATES)
    return names[int(hashlib.sha256(seed.encode()).hexdigest(), 16) % len(names)]


def _video_inputs(name: str) -> tuple[list[str], str]:
    """ffmpeg input args and the filter that produces [bg] (1080x1920, 30fps, SECONDS long)."""
    d, frames = f"{SECONDS}", int(SECONDS * FPS)
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1"
    if name == "parkour":
        return ["-ss", "20", "-t", d, "-i", str(GAMEPLAY)], f"[0:v]{fit},eq=saturation=1.25[bg]"
    if name == "split":
        half = f"scale={W}:{H // 2}:force_original_aspect_ratio=increase,crop={W}:{H // 2},fps={FPS},setsar=1"
        return (["-loop", "1", "-framerate", str(FPS), "-t", d, "-i", str(SRC / "site.jpg"),
                 "-ss", "95", "-t", d, "-i", str(GAMEPLAY)],
                f"[0:v]scale={W}:-2,crop={W}:{H // 2}:0:'min(ih-{H // 2},t*28)',setsar=1[top];"
                f"[1:v]{half}[bot];[top][bot]vstack=inputs=2,fps={FPS}[bg]")
    if name == "neon":
        return (["-f", "lavfi", "-t", d, "-i",
                 f"gradients=s={W}x{H}:c0=0x2b0057:c1=0xff2fb5:c2=0x00e5ff:c3=0x1a1aff:n=4:speed=0.018:r={FPS}"],
                "[0:v]noise=alls=6:allf=t,setsar=1[bg]")
    if name == "matrix":
        return (["-f", "lavfi", "-t", d, "-i",
                 f"life=s=270x480:mold=10:r={FPS}:ratio=0.12:death_color=#0b0b12:life_color=#ff6a00"],
                f"[0:v]scale={W}:{H}:flags=neighbor,gblur=sigma=1.2,eq=brightness=-0.08,setsar=1[bg]")
    if name == "product":
        return (["-loop", "1", "-framerate", str(FPS), "-t", d, "-i", str(SRC / "dashboard.png")],
                f"[0:v]scale={W}:-2,crop={W}:{H}:0:'min(ih-{H},t*60)',gblur=sigma=2.5,eq=brightness=-0.22:saturation=1.2,"
                f"setsar=1,fps={FPS}[bg]")
    raise VidgenError(f"unknown template {name!r}; choose from {', '.join(TEMPLATES)}")


def build(force: bool = False) -> dict:
    """Render the five base clips (no text) into video/templates/. Needs the sources in templates/src/."""
    missing = [p for p in (GAMEPLAY, SRC / "site.jpg", SRC / "dashboard.png") if not p.exists()]
    if missing:
        raise VidgenError(f"missing template sources: {', '.join(str(p) for p in missing)}")
    built = {}
    for name in TEMPLATES:
        out = path(name)
        if out.exists() and not force:
            built[name] = "kept"
            continue
        inputs, vf = _video_inputs(name)
        n_video = sum(1 for a in inputs if a == "-i")
        run([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *inputs, "-f", "lavfi", "-i", BEAT,
             "-filter_complex", f"{vf};[bg]format=yuv420p[v];[{n_video}:a]afade=t=in:d=0.3,"
             f"afade=t=out:st={SECONDS - 1.2}:d=1.2,volume=0.9[a]",
             "-map", "[v]", "-map", "[a]", "-t", str(SECONDS), "-r", str(FPS), "-c:v", "libx264", "-preset", "medium",
             "-crf", "26", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", str(out)],
            f"build template {name}")
        built[name] = "built"
    return built


# Bases built on the fly from a reference image (e.g. a person or product made with Codex image gen).
IMAGE_LOOKS = {
    "talking-head": {"look": "person ref, slow push-in, lower-third captions", "caption_y": 1480, "accent": "#FFE600"},
    "product": {"look": "product ref, slow pull-out, centred captions", "caption_y": 1300, "accent": "#00E5FF"},
    "brainrot": {"look": "ref on top, parkour below, seam captions", "caption_y": 960, "accent": "#FF4FD8"},
}


def image_base(kind: str, image: Path, out: Path) -> Path:
    """22s 1080x1920 clip with the beat, from one reference image."""
    frames = int(SECONDS * FPS)
    if kind == "brainrot":
        inputs = ["-loop", "1", "-framerate", str(FPS), "-t", str(SECONDS), "-i", str(image),
                  "-ss", "60", "-t", str(SECONDS), "-i", str(GAMEPLAY)]
        half = f"scale={W}:{H // 2}:force_original_aspect_ratio=increase,crop={W}:{H // 2},setsar=1"
        vf = (f"[0:v]{half},zoompan=z='1+0.08*on/{frames}':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:"
              f"s={W}x{H // 2}:fps={FPS}[top];[1:v]{half},fps={FPS}[bot];[top][bot]vstack=inputs=2[bg]")
    else:
        z = f"1+0.12*on/{frames}" if kind == "talking-head" else f"1.12-0.12*on/{frames}"
        inputs = ["-loop", "1", "-framerate", str(FPS), "-t", str(SECONDS), "-i", str(image)]
        vf = (f"[0:v]scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},setsar=1,"
              f"zoompan=z='{z}':x='iw/2-(iw/zoom/2)':y='ih/3-(ih/zoom/3)':d=1:s={W}x{H}:fps={FPS}[bg]")
    n = inputs.count("-i")
    run([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *inputs, "-f", "lavfi", "-i", BEAT,
         "-filter_complex", f"{vf};[bg]format=yuv420p[v];[{n}:a]afade=t=out:st={SECONDS - 1.2}:d=1.2[a]",
         "-map", "[v]", "-map", "[a]", "-t", str(SECONDS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "24",
         "-c:a", "aac", "-b:a", "128k", str(out)], f"image base {kind}")
    return out


def make(name: str, hook: str, lines: list[str], cta: str, out: Path, image: Path | None = None,
         tag: str = "tinyfish.ai") -> dict:
    """Burn hook (0-3s), caption lines (evenly timed) and CTA (last 3.5s) onto a base clip.

    With `image`, `name` is one of IMAGE_LOOKS and the base is built from that image first.
    """
    tmpdir = None
    if image is not None:
        if name not in IMAGE_LOOKS:
            raise VidgenError(f"with an image, choose one of {', '.join(IMAGE_LOOKS)}")
        tmpdir = tempfile.TemporaryDirectory()
        base, t = image_base(name, Path(image), Path(tmpdir.name) / "base.mp4"), IMAGE_LOOKS[name]
    else:
        if name == "auto":
            name = pick(hook + "|".join(lines))
        if name not in TEMPLATES:
            raise VidgenError(f"unknown template {name!r}; choose from auto, {', '.join(TEMPLATES)}")
        base, t = path(name), TEMPLATES[name]
        if not base.exists():
            raise VidgenError(f"template {name} not built yet: run `vidgen template build`")
    try:
        return _caption(base, name, t, hook, lines, cta, out, tag)
    finally:
        if tmpdir:
            tmpdir.cleanup()


def _caption(base: Path, name: str, t: dict, hook: str, lines: list[str], cta: str, out: Path,
             tag: str) -> dict:
    hook_end, cta_start = 3.0, SECONDS - 3.5
    layers = [Layer(0, SECONDS, [graphics.gradient(top=True, bottom=True, strength=120)], z=0),
              Layer(0, hook_end, [graphics.caption(hook.split(), None, t["caption_y"], size=104,
                                                   highlight=t["accent"])], z=1)]
    lines = [ln for ln in lines if ln.strip()] or [hook]
    step = (cta_start - hook_end) / len(lines)
    for i, ln in enumerate(lines):
        words = ln.split()
        accent_word = max(range(len(words)), key=lambda k: len(words[k]))  # pop the longest word
        layers.append(Layer(hook_end + i * step, hook_end + (i + 1) * step,
                            [graphics.caption(words, accent_word, t["caption_y"], size=96, highlight=t["accent"])], z=1))
    cta_y = min(t["caption_y"], 1350)  # leave room for the brand tag below a two-line CTA
    layers.append(Layer(cta_start, SECONDS, [graphics.caption(cta.split(), None, cta_y, size=100,
                                                              highlight=t["accent"]),
                                             graphics.banner(tag, 1720, size=56, dark=True)], z=1))

    out.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as tmp:
        track = graphics.write_track(layers, SECONDS, Path(tmp))
        run([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(base),
             "-f", "concat", "-safe", "0", "-i", str(track),
             "-filter_complex", f"[1:v]fps={FPS}[ov];[0:v][ov]overlay=0:0:eof_action=repeat:format=auto,format=yuv420p[v]",
             "-map", "[v]", "-map", "0:a", "-t", str(SECONDS), "-c:v", "libx264", "-preset", "veryfast", "-crf", "22",
             "-c:a", "copy", "-movflags", "+faststart", str(out)], f"caption template {name}")
    thumb = out.with_suffix(".jpg")
    run([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-ss", "1.5", "-i", str(out),
         "-frames:v", "1", "-q:v", "3", str(thumb)], "thumbnail")
    return {"ok": True, "path": str(out), "template": name, "look": t["look"], "duration": SECONDS,
            "thumbnail": str(thumb), "lines": len(lines)}


def install_sources(site: Path, dashboard: Path) -> None:
    SRC.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(site, SRC / "site.jpg")
    shutil.copyfile(dashboard, SRC / "dashboard.png")
