"""fal.ai through its MCP relay (https://mcp.fal.ai/mcp-relay), signed in once with OAuth.

Default model: MiniMax H3 Max text-to-video (`minimax/h3-max/text-to-video`): 5-15s per clip,
9:16, native soundtrack. Session: video/.fal/session.json (gitignored).
"""

import json
import mimetypes
import os
import sys
import time
from pathlib import Path

import httpx

from .config import FPS, H, PACKAGE_ROOT, VidgenError, W, run, tool
from .mcp_http import RemoteMCP

# Cheapest good option on fal (Oct 2026): H3 Max Turbo at $0.015/s, half of H3 Max ($0.03/s).
MODEL = os.environ.get("VIDGEN_FAL_MODEL", "minimax/h3-max-turbo/text-to-video")
# With a ref image: Turbo image-to-video uses it as the first frame ($0.015/s). For stronger product fidelity
# set minimax/h3-max/reference-to-video (up to 9 refs, $0.05/s).
REF_MODEL = os.environ.get("VIDGEN_FAL_REF_MODEL", "minimax/h3-max-turbo/image-to-video")
PRICE_PER_SECOND = {  # USD, from fal get_pricing on 2026-10-11
    "minimax/h3-max-turbo/text-to-video": 0.015, "minimax/h3-max-turbo/image-to-video": 0.015,
    "minimax/h3-max/text-to-video": 0.03, "minimax/h3-max/reference-to-video": 0.05,
}
MAX_USD = float(os.environ.get("VIDGEN_FAL_MAX_USD", "0.50"))  # per video; above this we don't submit


def estimate(endpoint: str, seconds: float, clips: int) -> float:
    if endpoint not in PRICE_PER_SECOND:
        raise VidgenError(f"no known price for {endpoint}; add it to PRICE_PER_SECOND before spending")
    return round(PRICE_PER_SECOND[endpoint] * (seconds + 0.7) * clips, 3)

client = RemoteMCP(
    name="fal",
    resource="https://mcp.fal.ai/mcp-relay",
    authorize="https://authkit.fal.ai/oauth2/authorize",
    token="https://authkit.fal.ai/oauth2/token",
    register="https://authkit.fal.ai/oauth2/register",
    session=Path(os.environ.get("FAL_SESSION_FILE", PACKAGE_ROOT / ".fal" / "session.json")),
)


def _json(res: dict) -> dict:
    """Relay tools answer with JSON text (plus a trailing account line); pull the JSON object out."""
    if "text" not in res:
        return res
    text = res["text"]
    try:
        return json.loads(text[text.index("{"):text.rindex("}") + 1])
    except ValueError:
        return {"text": text}


def _find(obj, key: str):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            if (hit := _find(v, key)) is not None:
                return hit
    elif isinstance(obj, list):
        for v in obj:
            if (hit := _find(v, key)) is not None:
                return hit
    return None


def upload(ref: str) -> str:
    """Public URLs pass through; local files go to fal's CDN via a signed PUT. Returns a URL models can read."""
    if ref.startswith(("http://", "https://")):
        return ref
    path = Path(ref).expanduser()
    prep = _json(client.call("upload_file", {"prepare_upload": True, "file_name": path.name,
                                             "file_size": path.stat().st_size}))
    put, url = _find(prep, "upload_url"), _find(prep, "file_url")
    if not put or not url:
        raise VidgenError(f"fal upload not prepared for {path.name}: {json.dumps(prep)[:300]}")
    mime = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    r = httpx.put(put, content=path.read_bytes(), headers={"Content-Type": mime}, timeout=300)
    if r.status_code >= 300:
        raise VidgenError(f"fal upload PUT {r.status_code}: {r.text[:200]}")
    return url


def generate(prompts: list[str], folder: Path, seconds: float = 11, aspect: str = "9:16",
             resolution: str = "768P", wait: int = 900, refs: list[str] | None = None) -> list[Path]:
    """Submit one clip per prompt in parallel, wait, download in order.

    With `refs` (already-uploaded URLs) the clips use REF_MODEL, and prompts can cite them as Image 1, 2...
    """
    endpoint = REF_MODEL if refs else MODEL
    cost = estimate(endpoint, seconds, len(prompts))
    if cost > MAX_USD:
        raise VidgenError(f"estimated ${cost} > VIDGEN_FAL_MAX_USD=${MAX_USD}; not submitting")
    if not refs:
        extra = {}
    elif endpoint.endswith("image-to-video"):
        extra = {"image_url": refs[0]}  # first frame: e.g. the Codex-drawn creator holding the product
    else:
        extra = {"reference_image_urls": refs[:9]}
    sub = _json(client.call("submit_jobs", {"requests": [
        {"index": i, "endpoint_id": endpoint, "input": {
            "prompt": p, "duration": seconds, "resolution": resolution, "prompt_expansion_mode": "disabled",  # exact
            **({} if endpoint.endswith("image-to-video") else {"aspect_ratio": aspect}), **extra}}
        for i, p in enumerate(prompts)]}, timeout=120))
    items = sub.get("results") or sub.get("requests") or sub.get("jobs") or []
    jobs = []
    for i, it in enumerate(items):
        rid = _find(it, "request_id")
        if not rid:
            raise VidgenError(f"fal rejected clip {i}: {json.dumps(it)[:300]}")
        jobs.append({"index": _find(it, "index") if _find(it, "index") is not None else i, "endpoint_id": endpoint,
                     "request_id": rid, **{k: v for k in ("status_url", "response_url") if (v := _find(it, k))}})
    if len(jobs) != len(prompts):
        raise VidgenError(f"fal accepted {len(jobs)}/{len(prompts)} clips: {json.dumps(sub)[:300]}")
    print(f"[fal] {len(jobs)} clips queued on {endpoint}" + (f" with {len(refs)} refs" if refs else "")
          + f" (est ${cost})",
          file=sys.stderr, flush=True)
    deadline = time.time() + wait
    while True:
        st = _json(client.call("wait_for_jobs", {"jobs": jobs, "timeout_seconds": 15}, timeout=60))
        if st.get("all_terminal"):
            break
        if time.time() > deadline:
            raise VidgenError(f"fal clips not done within {wait}s: {[j['request_id'] for j in jobs]}")
        time.sleep(float(st.get("poll_after_seconds") or 5))
    paths = []
    folder.mkdir(parents=True, exist_ok=True)
    for j in sorted(jobs, key=lambda j: j["index"]):
        res = _json(client.call("get_job_result", {k: j[k] for k in ("endpoint_id", "request_id", "response_url")
                                                    if k in j}, timeout=120))
        url = (_find(res, "video") or {}).get("url") if isinstance(_find(res, "video"), dict) else _find(res, "url")
        if not url:
            raise VidgenError(f"fal clip {j['index']} has no video: {json.dumps(res)[:300]}")
        path = folder / f"fal_{j['request_id'][:8]}.mp4"
        with httpx.stream("GET", url, follow_redirects=True, timeout=600) as r:
            r.raise_for_status()
            with open(path, "wb") as f:
                for chunk in r.iter_bytes():
                    f.write(chunk)
        paths.append(path)
    return paths


def join(clips: list[Path], out: Path) -> Path:
    """Concatenate clips (video + their native audio) into one 1080x1920 30fps mp4."""
    fit = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},fps={FPS},setsar=1,format=yuv420p"
    ins = [a for c in clips for a in ("-i", str(c))]
    parts = "".join(f"[{i}:v]{fit}[v{i}];[{i}:a]aresample=44100,aformat=channel_layouts=stereo[a{i}];"
                    for i in range(len(clips)))
    cat = "".join(f"[v{i}][a{i}]" for i in range(len(clips))) + f"concat=n={len(clips)}:v=1:a=1[v][a]"
    run([tool("ffmpeg"), "-hide_banner", "-loglevel", "error", "-y", *ins, "-filter_complex", parts + cat,
         "-map", "[v]", "-map", "[a]", "-c:v", "libx264", "-preset", "veryfast", "-crf", "21", "-c:a", "aac",
         "-b:a", "160k", str(out)], "join fal clips")
    return out
