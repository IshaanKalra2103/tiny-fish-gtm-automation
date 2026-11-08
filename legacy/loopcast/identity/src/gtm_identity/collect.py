"""Gather what the brand's own site says and looks like: copy, rendered type, colors, screenshots, images."""

from __future__ import annotations

import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urljoin, urlparse

from PIL import Image

from . import tf

SUBPAGE_HINTS = ("pricing", "product", "features", "use-case", "solutions", "customers", "case-stud",
                 "about", "enterprise", "docs", "blog")
MAX_TEXT = 6000


def pick_subpages(home_url: str, links: list[str], limit: int) -> list[str]:
    """Same-site pages most likely to say what the product is, in SUBPAGE_HINTS order."""
    host = urlparse(home_url).netloc.removeprefix("www.")
    seen, ranked = set(), []
    for link in links:
        u = urlparse(link)
        if u.netloc.removeprefix("www.") != host and not u.netloc.endswith("." + host):
            continue
        clean = f"{u.scheme}://{u.netloc}{u.path}".rstrip("/")
        if clean in seen or clean == home_url.rstrip("/"):
            continue
        rank = next((i for i, h in enumerate(SUBPAGE_HINTS) if h in u.path.lower() or h in u.netloc.lower()), None)
        if rank is not None:
            seen.add(clean)
            ranked.append((rank, clean))
    by_hint: dict[int, str] = {}
    for rank, url in ranked:  # one page per hint first, so 6 blog posts don't crowd out pricing
        by_hint.setdefault(rank, url)
    picked = [by_hint[r] for r in sorted(by_hint)]
    picked += [u for _, u in sorted(ranked) if u not in picked]
    return picked[:limit]


def palette(image_paths: list[Path], neutrals: int = 2, accents: int = 4) -> list[dict]:
    """Brand colors from the screenshots: the main neutrals plus the strongest accent hues.

    Accents (an orange headline, a gradient banner) cover few pixels, so they're found by binning vivid
    pixels by hue rather than by ranking all colors by share.
    """
    import colorsys
    from collections import defaultdict

    if not image_paths:
        return []
    pixels = []
    for p in image_paths:
        small = Image.open(p).convert("RGB").resize((360, 225))
        pixels += list(getattr(small, "get_flattened_data", small.getdata)())
    total = len(pixels)
    bins, grays = defaultdict(list), defaultdict(int)
    for rgb in pixels:
        h, s, v = colorsys.rgb_to_hsv(*(c / 255 for c in rgb))
        if s >= 0.45 and v >= 0.35:
            bins[int(h * 18) % 18].append(rgb)  # 20-degree hue bins
        elif s < 0.2:
            grays[tuple(c // 24 * 24 for c in rgb)] += 1

    def avg(group):
        return "#%02X%02X%02X" % tuple(sorted(c[i] for c in group)[len(group) // 2] for i in range(3))

    out = [{"hex": "#%02X%02X%02X" % tuple(min(255, c + 12) for c in rgb), "share": round(n / total, 3)}
           for rgb, n in sorted(grays.items(), key=lambda x: -x[1])[:neutrals]]
    vivid = sorted(bins.values(), key=len, reverse=True)
    out += [{"hex": avg(g), "share": round(len(g) / total, 3)} for g in vivid[:accents] if len(g) / total >= 0.002]
    return out


def css_hex(value: str | None) -> str | None:
    m = re.match(r"rgba?\((\d+),\s*(\d+),\s*(\d+)(?:,\s*([\d.]+))?\)", value or "")
    if not m or (m.group(4) is not None and float(m.group(4)) == 0):
        return None
    return "#%02X%02X%02X" % tuple(int(x) for x in m.groups()[:3])


def first_font(stack: str | None) -> str | None:
    return stack.split(",")[0].strip().strip("\"'") if stack else None


def collect(brand_url: str, out_dir: Path, *, max_pages: int = 6, browser: bool = True) -> dict:
    out_dir.mkdir(parents=True, exist_ok=True)
    errors: list[dict] = []

    home, errs = tf.fetch([brand_url], links=True, image_links=True)
    errors += errs
    if not home:
        raise RuntimeError(f"could not fetch {brand_url}: {errs}")
    subpages = pick_subpages(brand_url, home[0]["links"], max_pages)
    tf.log(f"fetched home; reading {len(subpages)} subpages")
    pages, errs = tf.fetch(subpages) if subpages else ([], [])
    errors += errs

    facts: dict = {}
    if browser:
        try:
            facts = tf.capture(brand_url, out_dir)
        except Exception as e:  # pixels are nice to have; copy alone still works
            errors.append({"url": brand_url, "error": f"browser: {type(e).__name__}: {e}"})
            tf.log(f"browser capture failed: {e}")

    styles = facts.get("styles") or {}
    fonts = list(dict.fromkeys(f for f in (first_font((s or {}).get("font")) for s in styles.values()) if f))
    css_colors = list(dict.fromkeys(c for s in styles.values() for c in (css_hex((s or {}).get("color")),
                                                                          css_hex((s or {}).get("bg"))) if c))
    shots = facts.get("screenshots", [])

    images = []
    candidates = [("og", facts.get("og_image"))] + [("icon", u) for u in (facts.get("icons") or [])[:1]]
    candidates += [(f"img{i}", u) for i, u in enumerate(home[0]["image_links"][:3])]
    for name, url in candidates:
        if not url:
            continue
        url = urljoin(brand_url, url)
        ext = Path(urlparse(url).path).suffix.lower()
        path = out_dir / f"{name}{ext if ext in ('.png', '.jpg', '.jpeg', '.webp', '.gif') else '.img'}"
        if tf.download(url, path):
            images.append(path.name)

    return {
        "brand_url": brand_url,
        "collected_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "meta": {k: facts.get(k) or (home[0].get(k) if k in ("title", "description") else None)
                 for k in ("title", "description", "og_title", "og_image", "theme_color")},
        "pages": [{"url": p["url"], "title": p["title"], "text": p["text"][:MAX_TEXT]} for p in home + pages],
        "styles": styles,
        "fonts": fonts,
        "css_colors": css_colors,
        "palette": palette([out_dir / s for s in shots]),
        "screenshots": shots,
        "images": images,
        "browser_minutes": facts.get("browser_minutes", 0),
        "errors": errors,
    }
