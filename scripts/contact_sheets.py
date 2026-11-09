# /// script
# requires-python = ">=3.12"
# dependencies = []
# ///
"""One contact sheet PNG (6 frames, 3x2) per preview mp4, for checking previews by eye (plan Task 13 Step 3).

    uv run scripts/contact_sheets.py <out_dir> [--media web/public/demo-media] [--frames 6] [--width 480]

Writes <out_dir>/<slug>__<tool_id>.png for every mp4 under the media dir. Needs ffmpeg and ffprobe on PATH.
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MEDIA = ROOT / "web" / "public" / "demo-media"


def sample_times(duration: float, n: int) -> list[float]:
    """n timestamps at the middle of n equal slices, so no frame is the black first or last one."""
    return [duration * (i + 0.5) / n for i in range(n)]


def duration_of(mp4: Path) -> float:
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(mp4)],
                         capture_output=True, text=True, check=True).stdout.strip()
    return float(out)


def sheet(mp4: Path, dest: Path, frames: int = 6, width: int = 480) -> None:
    times = sample_times(duration_of(mp4), frames)
    cols = 3 if frames >= 3 else frames
    rows = -(-frames // cols)
    with tempfile.TemporaryDirectory() as tmp:
        for i, t in enumerate(times):
            subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{t:.3f}", "-i", str(mp4), "-frames:v", "1",
                            "-vf", f"scale={width}:-2", f"{tmp}/f{i:02d}.png"], check=True)
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-framerate", "1", "-i", f"{tmp}/f%02d.png",
                        "-vf", f"tile={cols}x{rows}:padding=6:margin=6:color=white", "-frames:v", "1", str(dest)],
                       check=True)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ffmpeg contact sheets for the demo preview videos")
    ap.add_argument("out_dir", type=Path)
    ap.add_argument("--media", type=Path, default=DEFAULT_MEDIA)
    ap.add_argument("--frames", type=int, default=6)
    ap.add_argument("--width", type=int, default=480, help="width of each frame in px")
    a = ap.parse_args(argv)
    missing = [b for b in ("ffmpeg", "ffprobe") if not shutil.which(b)]
    if missing:
        print(f"Not found on PATH: {', '.join(missing)}. Install with `brew install ffmpeg`.", file=sys.stderr)
        return 2
    mp4s = sorted(a.media.rglob("*.mp4"))
    if not mp4s:
        print(f"No mp4 files under {a.media}", file=sys.stderr)
        return 1
    a.out_dir.mkdir(parents=True, exist_ok=True)
    failed = 0
    for mp4 in mp4s:
        rel = mp4.relative_to(a.media).with_suffix("")
        dest = a.out_dir / ("__".join(rel.parts) + ".png")
        try:
            sheet(mp4, dest, a.frames, a.width)
            print(f"{mp4.relative_to(a.media)} -> {dest}")
        except (subprocess.CalledProcessError, ValueError) as e:
            failed += 1
            print(f"FAILED {mp4}: {e}", file=sys.stderr)
    print(f"{len(mp4s) - failed}/{len(mp4s)} sheets in {a.out_dir}")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
