# /// script
# requires-python = ">=3.11"
# dependencies = ["pyobjc-framework-Quartz"]
# ///
"""Record one macOS window by id (captured even when covered) to an mp4, until a stop file appears.

usage: uv run winrec.py <window-id> <out.mp4> <stopfile> [fps]
"""
import subprocess
import sys
import time
from pathlib import Path

import Quartz as Q

wid, out, stop = int(sys.argv[1]), sys.argv[2], Path(sys.argv[3])
fps = float(sys.argv[4]) if len(sys.argv) > 4 else 20.0
opts = Q.kCGWindowImageBoundsIgnoreFraming | Q.kCGWindowImageBestResolution


def grab():
    img = Q.CGWindowListCreateImage(Q.CGRectNull, Q.kCGWindowListOptionIncludingWindow, wid, opts)
    if img is None:
        return None
    w, h, bpr = Q.CGImageGetWidth(img), Q.CGImageGetHeight(img), Q.CGImageGetBytesPerRow(img)
    data = Q.CGDataProviderCopyData(Q.CGImageGetDataProvider(img))
    return w, h, bpr, bytes(data)


first = grab()
if not first:
    sys.exit("no window image")
w, h, bpr, _ = first
stride_w = bpr // 4
print(f"recording window {wid}: {w}x{h} (stride {stride_w}) at {fps} fps -> {out}", flush=True)
ff = subprocess.Popen(
    ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "bgra", "-s", f"{stride_w}x{h}",
     "-use_wallclock_as_timestamps", "1", "-i", "-",
     "-vf", f"crop={w - w % 2}:{h - h % 2}:0:0,fps={int(fps)}", "-c:v", "libx264", "-crf", "16",
     "-preset", "veryfast", "-pix_fmt", "yuv420p", out],
    stdin=subprocess.PIPE)
n, t0, dt = 0, time.time(), 1.0 / fps
while not stop.exists():
    t = time.time()
    g = grab()
    if g and g[0] == w and g[1] == h and g[2] == bpr:
        ff.stdin.write(g[3])
        n += 1
    time.sleep(max(0.0, dt - (time.time() - t)))
ff.stdin.close()
ff.wait()
print(f"wrote {out}: {n} frames in {time.time() - t0:.1f}s", flush=True)
