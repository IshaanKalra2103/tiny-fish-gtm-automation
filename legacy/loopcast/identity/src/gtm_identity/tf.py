"""TinyFish calls used by the identity tools. Search and Fetch are free; Browser is $0.002/min."""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from urllib.parse import urlparse

import httpx
from tinyfish import TinyFish

_client: TinyFish | None = None

# Runs inside the page: what the site actually renders (type, colors, meta), not what its copy claims.
PAGE_FACTS_JS = """() => {
  const pick = (sel) => {
    const el = document.querySelector(sel);
    if (!el) return null;
    const s = getComputedStyle(el);
    return {font: s.fontFamily, weight: s.fontWeight, size: s.fontSize, color: s.color, bg: s.backgroundColor};
  };
  const meta = (q) => document.querySelector(q)?.getAttribute('content') || null;
  return {
    title: document.title,
    description: meta('meta[name="description"]'),
    og_title: meta('meta[property="og:title"]'),
    og_image: meta('meta[property="og:image"]'),
    theme_color: meta('meta[name="theme-color"]'),
    icons: [...document.querySelectorAll('link[rel*="icon"]')].map(l => l.href).slice(0, 4),
    styles: {body: pick('body'), h1: pick('h1'), h2: pick('h2'), p: pick('p'), a: pick('a'),
             button: pick('button, a[class*="button"], a[class*="btn"]')},
  };
}"""


def log(msg: str) -> None:
    print(f"[identity] {msg}", file=sys.stderr)


def client() -> TinyFish:
    global _client
    if _client is None:
        _client = TinyFish()
    return _client


def fetch(urls: list[str], **kw) -> tuple[list[dict], list[dict]]:
    """Fetch up to 10 URLs per call. Returns (pages, errors)."""
    pages, errors = [], []
    for i in range(0, len(urls), 10):
        res = client().fetch.get_contents(urls=urls[i:i + 10], **kw)
        for r in res.results:
            pages.append({"url": r.final_url or r.url, "title": r.title, "description": r.description,
                          "text": r.text or "", "links": r.links or [], "image_links": r.image_links or []})
        errors += [{"url": e.url, "error": e.error} for e in (res.errors or [])]
    return pages, errors


def search(query: str, **kw) -> list[dict]:
    for wait in (2, 5, 10, None):  # free tier is 30 requests/min
        try:
            res = client().search.query(query=query, location="US", language="en", **kw)
            return [{"title": r.title, "url": r.url, "snippet": r.snippet, "site": r.site_name, "date": r.date}
                    for r in res.results]
        except Exception as e:
            if wait is None or "429" not in str(e):
                raise
            log(f"search rate-limited, waiting {wait}s")
            time.sleep(wait)
    return []


def capture(url: str, out_dir: Path, shots: int = 3, attempts: int = 2) -> dict:
    """Remote TinyFish browser over CDP: desktop screenshots while scrolling, plus rendered type, colors and meta."""
    for attempt in range(1, attempts + 1):
        try:
            return _capture(url, out_dir, shots)
        except Exception as e:
            log(f"browser attempt {attempt} failed: {type(e).__name__}: {str(e)[:160]}")
            if attempt == attempts:
                raise
            time.sleep(3)
    return {}


def _capture(url: str, out_dir: Path, shots: int) -> dict:
    from playwright.sync_api import sync_playwright

    session = client().browser.sessions.create(url=url, timeout_seconds=300)
    started = time.time()
    paths: list[str] = []
    try:
        with sync_playwright() as p:
            browser = p.chromium.connect_over_cdp(session.cdp_url, timeout=60000)
            # Use the session's own tab: it already navigated to `url` at creation, and TinyFish's browser
            # closes the connection on new_context().
            ctx = browser.contexts[0]
            page = ctx.pages[0] if ctx.pages else ctx.new_page()
            page.set_viewport_size({"width": 1440, "height": 900})
            if urlparse(page.url).netloc != urlparse(url).netloc:
                page.goto(url, wait_until="commit", timeout=60000)
            try:
                page.wait_for_load_state("domcontentloaded", timeout=30000)
            except Exception:
                log("page still loading after 30s; capturing what has rendered")
            page.wait_for_timeout(4000)
            facts = page.evaluate(PAGE_FACTS_JS)
            out_dir.mkdir(parents=True, exist_ok=True)
            for i in range(shots):
                path = out_dir / f"shot_{i}.jpg"
                page.screenshot(path=str(path), type="jpeg", quality=85)
                paths.append(path.name)
                page.mouse.wheel(0, 900)
                page.wait_for_timeout(1500)
            browser.close()
    finally:
        try:
            httpx.delete(f"https://api.browser.tinyfish.ai/{session.session_id}",
                         headers={"X-API-Key": os.environ.get("TINYFISH_API_KEY", "")}, timeout=20)
        except Exception:
            pass  # sessions also expire on idle timeout
    facts["screenshots"] = paths
    facts["browser_minutes"] = round((time.time() - started) / 60, 2)
    return facts


def download(url: str, path: Path, max_bytes: int = 5_000_000) -> bool:
    try:
        r = httpx.get(url, timeout=20, follow_redirects=True)
        if r.status_code != 200 or len(r.content) > max_bytes or "image" not in r.headers.get("content-type", ""):
            return False
        path.write_bytes(r.content)
        return True
    except httpx.HTTPError:
        return False
