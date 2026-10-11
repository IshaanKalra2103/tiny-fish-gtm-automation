"""Image acquisition from Bing Images, with Openverse (Creative Commons) as the fallback.

No API keys: Bing is scraped the way a browser would load it; Openverse is a public API. Every image keeps
its source page in the manifest, so whoever publishes can check the rights later.
"""

import hashlib
import html
import json
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass
from io import BytesIO
from pathlib import Path

import httpx
from PIL import Image, ImageOps

from .config import CACHE, VidgenError

UA = ("Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/141.0.0.0 Safari/537.36")

# Bing's license filter codes. "any" means no filter.
LICENSES = {"any": None, "cc": "L2_L3_L4_L5_L6_L7", "commercial": "L2_L3"}


@dataclass
class Found:
    url: str
    page: str | None
    title: str | None
    engine: str


def search_bing(client: httpx.Client, query: str, count: int = 50, license: str = "any") -> list[Found]:
    qft = "+filterui:imagesize-large"
    if code := LICENSES[license]:
        qft += f"+filterui:license-{code}"
    r = client.get("https://www.bing.com/images/async",
                   params={"q": query, "first": 0, "count": count, "mmasync": 1, "qft": qft,
                           "setmkt": "en-US", "setlang": "en-US"})
    r.raise_for_status()
    found = []
    for m in re.findall(r'\bm="([^"]+)"', r.text):
        try:
            d = json.loads(html.unescape(m))
        except json.JSONDecodeError:
            continue
        if d.get("murl"):
            found.append(Found(d["murl"], d.get("purl"), d.get("t"), "bing"))
    return found


def search_openverse(client: httpx.Client, query: str) -> list[Found]:
    """Openverse (Creative Commons images, no key). Used when Bing comes back thin or off-topic."""
    r = client.get("https://api.openverse.org/v1/images/", params={"q": query, "page_size": 30})
    if r.status_code != 200:
        return []
    return [Found(x["url"], x.get("foreign_landing_url"), x.get("title"), f"openverse:{x.get('license')}")
            for x in r.json().get("results", []) if x.get("url")]


STOP = {"meme", "memes", "funny", "the", "and", "with", "for", "image", "images", "photo", "picture", "png",
        "jpg", "gif", "template", "reaction", "4k", "hd", "wallpaper"}


def rank(query: str, found: list[Found]) -> list[Found]:
    """Stable-sort results whose title or URL mentions a query keyword first."""
    return sorted(found, key=lambda f: -min(_hits(query, f), 2))


def _hits(query: str, f: Found) -> int:
    keys = [w for w in re.findall(r"[a-z0-9]+", query.lower()) if len(w) >= 3 and w not in STOP]
    text = f"{f.title or ''} {f.page or ''} {f.url}".lower()
    return sum(k in text for k in keys)


def _ahash(img: Image.Image) -> int:
    small = img.convert("L").resize((8, 8))
    px = list(small.getdata())
    avg = sum(px) / 64
    return sum(1 << i for i, p in enumerate(px) if p > avg)


def _download(client: httpx.Client, f: Found, min_side: int) -> tuple[Found, Image.Image] | None:
    try:
        r = client.get(f.url, headers={"Referer": f.page or "https://www.bing.com/"}, timeout=12)
        if r.status_code != 200 or len(r.content) > 20_000_000:
            return None
        img = ImageOps.exif_transpose(Image.open(BytesIO(r.content)))
        img.load()
    except Exception:
        return None
    if min(img.size) < min_side or max(img.size) / min(img.size) > 3.2:
        return None
    return f, img.convert("RGB")


def acquire(query: str, n: int = 6, license: str = "any", min_side: int = 360, refresh: bool = False) -> list[dict]:
    """Return up to `n` downloaded images for `query`, newest cache first.

    Cached per (query, license) under assets/cache/images/, so a re-render reuses the
    same pictures. Asking for more than the cache holds tops it up.
    """
    slug = re.sub(r"[^a-z0-9]+", "-", query.lower()).strip("-")[:40]
    folder = CACHE / "images" / f"{slug}-{hashlib.sha1(f'{query}|{license}'.encode()).hexdigest()[:8]}"
    manifest_path = folder / "manifest.json"
    manifest = [] if refresh or not manifest_path.exists() else json.loads(manifest_path.read_text())
    manifest = [m for m in manifest if Path(m["path"]).exists()]
    if len(manifest) >= n:
        return manifest[:n]

    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=20) as client:
        candidates: list[Found] = []
        try:
            candidates = rank(query, search_bing(client, query, license=license))
        except httpx.HTTPError as e:
            print(f"[images] bing error: {e}", file=sys.stderr)
        if sum(_hits(query, c) > 0 for c in candidates[: n * 3]) < n:  # thin or off-topic: add Openverse
            try:
                candidates += rank(query, search_openverse(client, query))
            except httpx.HTTPError as e:
                print(f"[images] openverse error: {e}", file=sys.stderr)
            candidates = rank(query, candidates)
        seen_urls = {m["url"] for m in manifest}
        candidates = rank(query, [c for c in candidates if c.url not in seen_urls])
        hashes = {m["ahash"] for m in manifest}

        folder.mkdir(parents=True, exist_ok=True)
        with ThreadPoolExecutor(12) as pool:
            for got in pool.map(lambda c: _download(client, c, min_side), candidates[: max(n * 4, 12)]):
                if len(manifest) >= n:
                    break
                if not got:
                    continue
                f, img = got
                h = _ahash(img)
                if any(bin(h ^ other).count("1") <= 4 for other in hashes):  # near-duplicate
                    continue
                hashes.add(h)
                path = folder / f"{len(manifest):02d}.jpg"
                img.save(path, quality=92)
                manifest.append({"path": str(path), "width": img.width, "height": img.height, "ahash": h,
                                 "query": query, "license_filter": license, **asdict(f)})
    manifest_path.write_text(json.dumps(manifest, indent=1))
    if not manifest:
        raise VidgenError(f"no usable images found for {query!r}")
    print(f"[images] {query!r}: {len(manifest)} images", file=sys.stderr)
    return manifest[:n]


def fetch_url(url: str) -> Path:
    """Download one image URL into the cache (for specs that name images directly)."""
    path = CACHE / "images" / "direct" / (hashlib.sha1(url.encode()).hexdigest()[:16] + ".jpg")
    if path.exists():
        return path
    with httpx.Client(headers={"User-Agent": UA}, follow_redirects=True, timeout=20) as client:
        got = _download(client, Found(url, None, None, "url"), min_side=1)
    if not got:
        raise VidgenError(f"could not download image {url}")
    path.parent.mkdir(parents=True, exist_ok=True)
    got[1].save(path, quality=92)
    return path
