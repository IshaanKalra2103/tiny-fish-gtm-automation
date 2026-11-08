"""Thin wrappers over the TinyFish primitives, each logging to the run and charging the budget ledger.

Search  -> discover URLs we don't have yet (free)
Fetch   -> read known URLs as clean markdown (free)
Agent   -> goal-driven multi-step work on interactive pages ($0.016/step)
Browser -> scripted CDP session for pixels, i.e. screenshots ($0.002/min)
"""

import os
import subprocess
import time
from pathlib import Path

import httpx
from tinyfish import BrowserProfile, ProxyConfig, TinyFish

from . import config
from .run import Run

_client: TinyFish | None = None


def client() -> TinyFish:
    global _client
    if _client is None:
        _client = TinyFish()
    return _client


def search(run: Run, query: str, role: str = "research", **kw) -> list[dict]:
    t0 = time.time()
    res = client().search.query(query=query, location="US", **kw)
    hits = [{"title": r.title, "url": r.url, "snippet": r.snippet, "site": r.site_name,
             "date": getattr(r, "date", None)} for r in res.results]
    run.charge("search", 0.0)
    run.log(role, f"TinyFish Search '{query}' -> {len(hits)} results", primitive="search",
            filters={k: v for k, v in kw.items() if v}, seconds=round(time.time() - t0, 1))
    return hits


def fetch(run: Run, urls: list[str], role: str = "research") -> list[dict]:
    docs: list[dict] = []
    for i in range(0, len(urls), 10):
        chunk = urls[i:i + 10]
        t0 = time.time()
        res = client().fetch.get_contents(urls=chunk)
        for r in res.results:
            docs.append({"url": r.url, "title": r.title, "text": r.text or ""})
        errors = [e.url for e in (res.errors or [])]
        run.charge("fetch", 0.0)
        run.log(role, f"TinyFish Fetch {len(chunk)} URLs -> {len(res.results)} pages", primitive="fetch",
                failed=errors, seconds=round(time.time() - t0, 1))
    return docs


def agent(run: Run, url: str, goal: str, schema: dict, role: str = "research") -> dict:
    """Blocking Agent run (call from a worker thread). Returns {'ok', 'result', 'steps', 'run_id'}."""
    t0 = time.time()
    run.log(role, f"TinyFish Agent started on {url}", primitive="agent", goal=goal[:160])
    r = client().agent.run(url=url, goal=goal, output_schema=schema, browser_profile=BrowserProfile.STEALTH,
                           proxy_config=ProxyConfig(enabled=True, country_code="US"))
    steps = r.num_of_steps or 0
    run.charge("agent", steps * config.AGENT_USD_PER_STEP)
    status = str(r.status)
    ok = "COMPLETED" in status.upper() and r.result is not None and not (r.result or {}).get("blocked")
    run.log(role, f"TinyFish Agent finished: {status}, {steps} steps", primitive="agent", ok=ok,
            run_id=r.run_id, seconds=round(time.time() - t0, 1), usd=round(steps * config.AGENT_USD_PER_STEP, 3))
    return {"ok": ok, "result": r.result, "steps": steps, "run_id": r.run_id, "error": str(r.error) if r.error else None}


def screenshots(run: Run, url: str, out_dir: Path, shots: int = 4, role: str = "research", attempts: int = 2) -> list[Path]:
    """Remote TinyFish browser over CDP: vertical, phone-sized screenshots while scrolling (video B-roll)."""
    for attempt in range(1, attempts + 1):
        try:
            return _screenshots(run, url, out_dir, shots, role)
        except Exception as e:
            run.log(role, f"Browser attempt {attempt} failed: {type(e).__name__}: {e}", level="warn")
            if attempt == attempts:
                raise
            time.sleep(3)
    return []


def _screenshots(run: Run, url: str, out_dir: Path, shots: int, role: str) -> list[Path]:
    """Drive the session's own page over raw CDP (cdp_shots.mjs): TinyFish sessions close extra contexts/pages,
    so we emulate a phone viewport on the existing target instead of opening a new one."""
    t0 = time.time()
    # Plain REST create: the SDK call intermittently hung or returned sessions whose CDP target never answered.
    resp = httpx.post("https://api.browser.tinyfish.ai", json={"url": url, "timeout_seconds": 300},
                      headers={"X-API-Key": os.environ["TINYFISH_API_KEY"]}, timeout=90)
    resp.raise_for_status()
    session = type("Session", (), resp.json())
    run.log(role, "TinyFish Browser session created", primitive="browser", session_id=session.session_id)
    out_dir.mkdir(parents=True, exist_ok=True)
    for old in out_dir.glob("shot_*.jpg"):
        old.unlink()
    try:
        p = subprocess.run(["node", str(Path(__file__).with_name("cdp_shots.mjs")), session.cdp_url, str(out_dir), url, str(shots)],
                           capture_output=True, text=True, timeout=180)
        if "ERR" in p.stderr or p.returncode:
            raise RuntimeError((p.stderr or p.stdout).strip()[-300:])
    finally:
        _close_session(session.session_id)
        run.charge("browser", (time.time() - t0) / 60 * config.BROWSER_USD_PER_MIN)
    paths = sorted(out_dir.glob("shot_*.jpg"))
    if not paths:
        raise RuntimeError("no screenshots captured")
    run.log(role, f"TinyFish Browser captured {len(paths)} screenshots of {url}", primitive="browser",
            seconds=round(time.time() - t0, 1))
    return paths


def _close_session(session_id: str) -> None:
    try:
        httpx.delete(f"https://api.browser.tinyfish.ai/{session_id}",
                     headers={"X-API-Key": os.environ["TINYFISH_API_KEY"]}, timeout=20)
    except Exception:
        pass  # sessions also expire on idle timeout
