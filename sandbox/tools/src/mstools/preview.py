"""preview: a short video of a tool doing its job in the owner's business (OpenRouter video API).

Cached per tool. Live renders are capped per owner, per day and by a global dollar cap.
"""
import argparse
import os
import time

import httpx

from . import config, ws
from .budget import BudgetExceeded, bump_count, charge, spent
from .cli import ToolError, log, run

API = "https://openrouter.ai/api/v1/videos"


def http_client() -> httpx.Client:
    return httpx.Client(timeout=60)


def _headers() -> dict:
    key = os.environ.get("OPENROUTER_API_KEY")
    if not key:
        raise ToolError("OPENROUTER_API_KEY is not set.")
    return {"Authorization": f"Bearer {key}"}


def _record(tool: str, prompt: str, status: str, video_file: str | None = None, cost: float = 0.0) -> dict:
    data = {"tool_id": tool, "prompt": prompt, "status": status, "video_file": video_file, "cost_usd": round(cost, 4)}
    ws.save("preview", data)
    return data


def make(tool: str, prompt: str, seconds: int) -> dict:
    ws.check_id(tool)  # it names the .mp4 and the record: check before any spend or file write
    work = config.work()
    seconds = max(config.PREVIEW_MIN_SECONDS, min(config.PREVIEW_MAX_SECONDS, seconds))
    allowed = [d for d in config.VIDEO_DURATIONS if d <= seconds] or [min(config.VIDEO_DURATIONS)]
    seconds = max(allowed)
    mp4 = work / f"preview_{tool}.mp4"
    existing = ws.load("preview", tool)
    if existing and existing.get("status") == "completed" and mp4.exists():
        return {"preview": existing, "cached": True}
    estimate = seconds * config.video_usd_per_sec()
    gl, cap = config.global_budget(), config.CAPS["video_global"]
    try:
        if spent(gl, "video_global") + estimate > cap:
            raise BudgetExceeded("The preview budget for this demo is used up.")
        bump_count(config.owner_budget(), "previews", config.PREVIEWS_PER_OWNER)
        bump_count(gl, "previews", config.PREVIEWS_PER_DAY, per_day=True)
    except BudgetExceeded as e:
        return {"preview": _record(tool, prompt, "capped"), "cached": False, "message": str(e)}

    body = {"model": config.video_model(), "prompt": prompt, "duration": seconds, "resolution": "720p",
            "aspect_ratio": "16:9", "generate_audio": False}
    poll = float(os.environ.get("MS_VIDEO_POLL_SECONDS", "15"))
    with http_client() as h:
        r = h.post(API, json=body, headers=_headers())
        if r.status_code >= 400:
            log(f"submit failed {r.status_code}: {r.text[:300]}")
            return {"preview": _record(tool, prompt, "failed"), "cached": False, "message": "The video service refused the request."}
        job = r.json()
        url = job.get("polling_url") or f"{API}/{job['id']}"
        deadline = time.time() + 600
        while True:
            st = h.get(url, headers=_headers()).json()
            status = st.get("status")
            if status == "completed":
                break
            if status in ("failed", "cancelled", "expired") or time.time() > deadline:
                log(f"video job {job.get('id')} ended {status}: {st.get('error')}")
                return {"preview": _record(tool, prompt, "failed"), "cached": False, "message": "The preview could not be made."}
            log(f"video job {job.get('id')}: {status}")
            time.sleep(poll)
        video_url = (st.get("unsigned_urls") or [None])[0]
        if not video_url:
            return {"preview": _record(tool, prompt, "failed"), "cached": False, "message": "No video came back."}
        dl = h.get(video_url, headers=_headers(), follow_redirects=True)
        dl.raise_for_status()
        mp4.write_bytes(dl.content)
    cost = float((st.get("usage") or {}).get("cost") or estimate)
    charge(gl, "video_global", cost, float("inf"))  # record what was actually spent
    return {"preview": _record(tool, prompt, "completed", mp4.name, cost), "cached": False}


def _main(a: argparse.Namespace) -> dict:
    return make(a.tool, a.prompt, a.seconds)


def main() -> None:
    p = argparse.ArgumentParser(prog="preview", description="Make a short preview video of a tool.")
    sub = p.add_subparsers(dest="cmd", required=True)
    m = sub.add_parser("make")
    m.add_argument("--tool", required=True)
    m.add_argument("--prompt", required=True)
    m.add_argument("--seconds", type=int, default=6)
    run(_main, p)


if __name__ == "__main__":
    main()
