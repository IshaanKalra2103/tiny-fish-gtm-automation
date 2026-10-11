"""Build demo-video.mp4 from a finished run: dashboard walkthrough (headless Chrome capture) + draft v1 vs final.

usage: uv run python scripts/demo_video.py <run-id> <out.mp4>
"""

import subprocess
import sys
from pathlib import Path

import numpy as np
from moviepy import CompositeVideoClip, ImageClip, VideoFileClip, concatenate_videoclips
from PIL import Image, ImageDraw

from gtm import config
from gtm.roles.video import _font

W, H = 1920, 1080
CHROME = "/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"


def card(lines: list[tuple[str, int, tuple]], dur: float) -> ImageClip:
    img = Image.new("RGB", (W, H), (15, 15, 23))
    d = ImageDraw.Draw(img)
    y = H // 2 - sum(s for _, s, _ in lines) // 2 - 20 * len(lines)
    for text, size, color in lines:
        d.text((W / 2, y), text, font=_font(size), fill=color, anchor="ma")
        y += size + 40
    return ImageClip(np.array(img)).with_duration(dur)


def label(text: str, clip, color=(255, 106, 0)):
    img = Image.new("RGBA", (W, 110), (15, 15, 23, 230))
    ImageDraw.Draw(img).text((W / 2, 28), text, font=_font(52), fill=color, anchor="ma")
    return CompositeVideoClip([clip, ImageClip(np.array(img)).with_duration(clip.duration).with_position((0, H - 110))], size=(W, H))


def dashboard_pan(html: Path, png: Path, dur: float):
    subprocess.run([CHROME, "--headless=new", "--hide-scrollbars", f"--screenshot={png}", "--window-size=1440,9000",
                    "--virtual-time-budget=8000", html.resolve().as_uri()], check=True, capture_output=True)
    page = Image.open(png).convert("RGB")
    page = page.resize((W, int(page.height * W / page.width)))
    arr = np.array(page)
    # trim the blank tail
    rows = np.where(arr.mean(axis=(1, 2)) > 16)[0]
    arr = arr[: min(arr.shape[0], rows.max() + 40)] if len(rows) else arr
    travel = max(arr.shape[0] - H, 1)
    return ImageClip(arr).with_duration(dur).with_position(lambda t: (0, -int(travel * min(t / dur, 1)))).with_effects([])


def phone(video: Path, max_s: float):
    v = VideoFileClip(str(video))
    v = v.subclipped(0, min(max_s, v.duration)).resized(height=H - 130)
    return CompositeVideoClip([v.with_position(("center", 10))], size=(W, H), bg_color=(15, 15, 23)).with_duration(v.duration)


def main(run_id: str, out: str) -> None:
    rd = config.RUNS_DIR / run_id
    qa = __import__("json").loads((rd / "qa.json").read_text())
    final = qa["final_version"]
    v1 = __import__("json").loads((rd / "qa_v1.json").read_text())
    pan = dashboard_pan(rd / "index.html", rd / "dashboard_full.png", 42)
    clips = [
        card([("TinyFish growth loop", 96, (255, 106, 0)), ("one live run on tinyfish.ai · niche: AI browser agents", 48, (220, 220, 230)),
              ('uv run gtm run --brand-url https://www.tinyfish.ai/ --niche "AI browser agents"', 34, (140, 200, 255))], 5),
        label("Search finds threads + TikToks/Reels · Fetch reads them · Agent works YouTube filters · Browser captures the brand", pan),
        label(f"Draft v1 — FAILED persona QA ({v1['avg_score']}/10): " + (v1["blocking"][0][:70] if v1["blocking"] else ""), phone(rd / "video_v1.mp4", 12), (255, 92, 92)),
    ]
    if final != 1:
        fq = __import__("json").loads((rd / f"qa_v{final}.json").read_text())
        clips.append(label(f"Draft v{final} — {'PASSED' if fq['passed'] else 'still failing'} ({fq['avg_score']}/10) after automatic revision",
                           phone(rd / f"video_v{final}.mp4", 30), (61, 220, 132) if fq["passed"] else (255, 92, 92)))
    clips.append(card([("Stops at a human approval gate", 72, (255, 255, 255)), (f"uv run gtm approve {run_id}", 44, (140, 200, 255)),
                       ("Search · Fetch · Agent · Browser — all live TinyFish", 44, (255, 106, 0))], 5))
    concatenate_videoclips(clips, method="compose").write_videofile(out, fps=24, codec="libx264", audio_codec="aac", logger=None)
    print(out)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
