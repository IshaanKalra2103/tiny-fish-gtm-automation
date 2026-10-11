"""Background gameplay and music, fetched with yt-dlp and cached under assets/.

Gameplay is normalized once to H.264, 30 fps, 1080p, no audio, with a keyframe every
second. That makes every later render seek and decode it cheaply.
"""

import random
import re
import sys
from pathlib import Path

from .config import ASSETS, FPS, VidgenError, probe_duration, run, tool

GAMEPLAY = ASSETS / "gameplay"

# name -> YouTube search used when the clip isn't cached yet
PRESETS = {
    "minecraft": "minecraft parkour gameplay no copyright 4k",
    "subway": "subway surfers gameplay no copyright full screen",
    "gta": "gta 5 mega ramp gameplay no copyright",
    "satisfying": "satisfying kinetic sand cutting no copyright no music",
    "trackmania": "trackmania gameplay no copyright no commentary",
}


def _ytdlp() -> list[str]:
    try:
        return [tool("yt-dlp")]
    except VidgenError:
        return [sys.executable, "-m", "yt_dlp"]


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "_", name.lower()).strip("_")[:40] or "clip"


def cached() -> list[str]:
    return sorted(p.stem for p in (GAMEPLAY / "prepared").glob("*.mp4"))


def fetch(name: str, query: str | None = None, url: str | None = None, start: int = 60, length: int = 180) -> Path:
    """Download `length` seconds of gameplay (from `start`) and prepare it. Idempotent."""
    name = _slug(name)
    prepared = GAMEPLAY / "prepared" / f"{name}.mp4"
    if prepared.exists():
        return prepared
    raw = GAMEPLAY / "raw" / f"{name}.mp4"
    if not raw.exists():
        target = url or f"ytsearch1:{query or PRESETS.get(name) or name + ' gameplay no copyright'}"
        print(f"[footage] downloading {name} from {target}", file=sys.stderr)
        raw.parent.mkdir(parents=True, exist_ok=True)
        run([*_ytdlp(), "-q", "--no-warnings", "--no-playlist",
             "-f", "bv*[height<=1080][vcodec^=avc1]/bv*[height<=1080]/b[height<=1080]",
             "--download-sections", f"*{start}-{start + length}", "--force-keyframes-at-cuts",
             "--remux-video", "mp4", "-o", str(raw.with_suffix(".%(ext)s")), target], f"yt-dlp {name}")
    print(f"[footage] preparing {name}", file=sys.stderr)
    prepared.parent.mkdir(parents=True, exist_ok=True)
    tmp = prepared.with_suffix(".tmp.mp4")
    run([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", "-i", str(raw), "-an",
         "-vf", f"fps={FPS},scale=-2:1080", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21",
         "-g", str(FPS), "-pix_fmt", "yuv420p", "-movflags", "+faststart", str(tmp)], f"prepare {name}")
    tmp.rename(prepared)
    return prepared


def resolve(name_or_path: str) -> Path:
    p = Path(name_or_path).expanduser()
    if p.suffix and p.exists():
        return p
    return fetch(name_or_path)


def pick_offset(path: Path, need: float, seed: int | None = None) -> float:
    total = probe_duration(path)
    if total <= need + 1:
        return 0.0
    return round(random.Random(seed).uniform(0, total - need - 0.5), 2)


def music(source: str) -> Path:
    """A local audio file, or a URL / `ytsearch1:...` query fetched as audio once."""
    p = Path(source).expanduser()
    if p.exists():
        return p
    out = ASSETS / "music" / f"{_slug(source)}.m4a"
    if not out.exists():
        out.parent.mkdir(parents=True, exist_ok=True)
        target = source if re.match(r"^(https?://|ytsearch\d*:)", source) else f"ytsearch1:{source}"
        print(f"[footage] downloading music {target}", file=sys.stderr)
        run([*_ytdlp(), "-q", "--no-warnings", "--no-playlist", "-f", "ba[ext=m4a]/ba",
             "--download-sections", "*0-180", "-o", str(out), target], "yt-dlp music")
    return out
