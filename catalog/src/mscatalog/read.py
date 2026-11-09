"""Read: TinyFish Fetch the vendor's home page, then the pricing, privacy, about and integrations pages it links to."""
import time
from urllib.parse import urlparse

from . import store
from .discover import Candidate, registrable

KINDS = {
    "pricing": ("pricing", "plans", "price"),
    "privacy": ("privacy",),
    "about": ("about", "company", "team", "our-story"),
    "integrations": ("integrations", "integration", "apps"),
}
GUESS = {"pricing": "/pricing", "privacy": "/privacy", "about": "/about", "integrations": "/integrations"}
SKIP_HOSTS = ("app.", "login.", "auth.", "dashboard.", "help.", "support.", "docs.", "blog.", "status.")


def _client():
    from mstools.tinyfish import client
    return client()


def fetch_with_links(urls: list[str], max_chars: int = 15_000, attempts: int = 3) -> dict[str, dict]:
    """url -> {url, final_url, title, text, links}. Retries what failed (Fetch throttles bursts); the rest is left out."""
    out: dict[str, dict] = {}
    todo = list(dict.fromkeys(urls))
    for attempt in range(attempts):
        if not todo:
            break
        if attempt:
            time.sleep(2.0 * attempt)
        for i in range(0, len(todo), 10):
            chunk = todo[i:i + 10]
            try:
                res = _client().fetch.get_contents(urls=chunk, links=True, per_url_timeout_ms=20_000)
            except Exception:
                continue
            for r in res.results:
                text = (r.text or "")[:max_chars]
                if text.strip():
                    out[r.url] = {"url": r.url, "final_url": getattr(r, "final_url", None) or r.url, "title": r.title,
                                  "text": text, "links": list(r.links or [])}
        todo = [u for u in todo if u not in out]
    return out


def links_only(urls: list[str]) -> dict[str, list[str]]:
    return {u: p["links"] for u, p in fetch_with_links(urls, max_chars=100).items()}


def pick_links(domain: str, links: list[str]) -> dict[str, str]:
    picked: dict[str, str] = {}
    for link in links:
        p = urlparse(link)
        host = (p.hostname or "").lower()
        if registrable(host) != domain or host.startswith(SKIP_HOSTS) or "#" in link and p.path in ("", "/"):
            continue
        path = p.path.lower().rstrip("/")
        last = path.rsplit("/", 1)[-1]
        for kind, words in KINDS.items():
            if kind in picked:
                continue
            if any(last == w or last.startswith(w + "-") or last.endswith("-" + w) or (kind == "privacy" and w in last)
                   for w in words) and path.count("/") <= 2:
                picked[kind] = link.split("#")[0]
    return picked


def run(c: Candidate, fetch=fetch_with_links) -> dict:
    home_url = f"https://{c.domain}/"
    got = fetch([home_url])
    home = got.get(home_url) or next(iter(got.values()), None)
    if home is None:  # try the first URL search found on this domain
        alt = next((u for u in c.urls if registrable(u) == c.domain), None)
        if alt and alt != home_url:
            got = fetch([alt])
            home = next(iter(got.values()), None)
    pages = []
    if home:
        home["kind"] = "home"
        pages.append(home)
        picked = pick_links(c.domain, home.get("links", []))
        base = f"{urlparse(home['final_url']).scheme or 'https'}://{urlparse(home['final_url']).hostname or c.domain}"
        for kind in KINDS:
            picked.setdefault(kind, base + GUESS[kind])
        extra = fetch(list(picked.values()), max_chars=60_000)
        for kind, url in picked.items():
            p = extra.get(url)
            if p and p["text"].strip():
                p["kind"] = kind
                if kind != "privacy":
                    p["text"] = p["text"][:15_000]
                p["links"] = []
                pages.append(p)
        home["links"] = home.get("links", [])[:150]
    rec = {"domain": c.domain, "name_guess": c.name_guess, "urls": c.urls[:10], "hits": c.hits[:25], "pages": pages,
           "ok": bool(home and home["text"].strip())}
    store.save_json(store.pages_dir() / f"{c.domain}.json", rec)
    return rec
