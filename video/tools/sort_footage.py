# /// script
# requires-python = ">=3.11"
# dependencies = ["mlx-whisper"]
# ///
"""Transcribe raw takes and sort them by the clip id said at the start ("camera four", "voice nine").

usage: uv run video/tools/sort_footage.py <file-or-dir> [...] [--out footage/index.json]

For each take it writes: file, speaker guess (none; set by hand), clip id (C4 / V9 / None), the transcript,
word timings, and line_start / line_end: the first and last word after the spoken clip id, so the edit can
cut the slate off. Audio is extracted to 16 kHz mono with ffmpeg first.
"""
import json
import re
import subprocess
import sys
import tempfile
from pathlib import Path

import mlx_whisper

MODEL = "mlx-community/whisper-large-v3-turbo"
VIDEO_EXT = {".mov", ".mp4", ".m4v", ".m4a", ".wav", ".mp3", ".webm", ".aac", ".aiff", ".3gp"}
NUMS = {w: i for i, w in enumerate(
    "zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen".split())}
SLATE = re.compile(r"\b(camera|cam|voice|v|c)\s*[- ]?\s*(\d{1,2}|" + "|".join(NUMS) + r")\b", re.I)


def clip_id(text: str) -> tuple[str | None, int]:
    """The clip id said in the first words, and how many words the slate used (0 if none)."""
    head = " ".join(text.split()[:6]).lower().replace(".", " ").replace(",", " ")
    m = SLATE.search(head)
    if not m:
        return None, 0
    kind = "C" if m.group(1).lower() in ("camera", "cam", "c") else "V"
    n = m.group(2).lower()
    num = int(n) if n.isdigit() else NUMS[n]
    used = len(head[: m.end()].split())
    return f"{kind}{num}", used


def transcribe(path: Path) -> dict:
    with tempfile.TemporaryDirectory() as td:
        wav = Path(td) / "a.wav"
        subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(path), "-ac", "1", "-ar", "16000", str(wav)], check=True)
        r = mlx_whisper.transcribe(str(wav), path_or_hf_repo=MODEL, word_timestamps=True, language="en")
    words = [{"w": w["word"].strip(), "s": round(w["start"], 2), "e": round(w["end"], 2)}
             for seg in r["segments"] for w in seg.get("words", [])]
    text = " ".join(w["w"] for w in words)
    cid, used = clip_id(text)
    line = words[used:] if words else []
    dur = float(subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
                               capture_output=True, text=True).stdout.strip() or 0)
    return {"file": str(path), "duration": round(dur, 2), "clip": cid, "text": text,
            "line_start": line[0]["s"] if line else None, "line_end": line[-1]["e"] if line else None, "words": words}


def main() -> None:
    args = sys.argv[1:]
    out = Path(args[args.index("--out") + 1]) if "--out" in args else Path("footage/index.json")
    if "--out" in args:
        i = args.index("--out"); args = args[:i] + args[i + 2:]
    files: list[Path] = []
    for a in args:
        p = Path(a)
        files += sorted(f for f in p.rglob("*") if f.suffix.lower() in VIDEO_EXT) if p.is_dir() else [p]
    done = {}
    if out.exists():
        done = {r["file"]: r for r in json.loads(out.read_text())}
    for f in files:
        if str(f) in done:
            continue
        r = transcribe(f)
        done[str(f)] = r
        print(f"{r['clip'] or '??':>4}  {r['duration']:6.1f}s  {f.name}  | {r['text'][:90]}", flush=True)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(sorted(done.values(), key=lambda r: (r["clip"] or "zz", r["file"])), indent=1))
    print(f"index: {out} ({len(done)} takes)")


if __name__ == "__main__":
    main()
