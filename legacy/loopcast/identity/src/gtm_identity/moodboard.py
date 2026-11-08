"""Render moodboard.png: the brand's real screenshots, colors and type, next to what the agent concluded it is.

Without identity.json it renders a draft from the evidence alone, so the agent can look at it first.
"""

from __future__ import annotations

from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

W, H, M = 1600, 1000, 48
INK, MUTED, PAPER, LINE = (24, 24, 27), (110, 110, 118), (246, 245, 242), (222, 220, 214)
FONT_FILES = {
    "regular": ["/System/Library/Fonts/Supplemental/Arial.ttf", "/System/Library/Fonts/Helvetica.ttc",
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf"],
    "bold": ["/System/Library/Fonts/Supplemental/Arial Bold.ttf", "/System/Library/Fonts/Helvetica.ttc",
             "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"],
}


def font(size: int, weight: str = "regular") -> ImageFont.FreeTypeFont:
    for path in FONT_FILES[weight]:
        if Path(path).exists():
            return ImageFont.truetype(path, size)
    return ImageFont.load_default(size)


def wrap(draw: ImageDraw.ImageDraw, text: str, f, width: int, max_lines: int) -> list[str]:
    lines, line = [], ""
    for word in text.split():
        trial = f"{line} {word}".strip()
        if draw.textlength(trial, font=f) <= width:
            line = trial
        else:
            lines.append(line)
            line = word
    lines.append(line)
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;") + "…"
    return [l for l in lines if l]


def text_block(draw, xy, text, f, width, max_lines, fill=INK, gap=6) -> int:
    x, y = xy
    for line in wrap(draw, text, f, width, max_lines):
        draw.text((x, y), line, font=f, fill=fill)
        y += f.size + gap
    return y


def label(draw, xy, text) -> int:
    draw.text(xy, text.upper(), font=font(13, "bold"), fill=MUTED)
    return xy[1] + 22


def chips(draw, xy, items, width, f=None) -> int:
    f = f or font(17)
    x0, (x, y) = xy[0], xy
    for item in items:
        w = int(draw.textlength(item, font=f)) + 24
        if x + w > x0 + width:
            x, y = x0, y + f.size + 22
        draw.rounded_rectangle((x, y, x + w, y + f.size + 14), radius=14, outline=INK, width=2)
        draw.text((x + 12, y + 6), item, font=f, fill=INK)
        x += w + 8
    return y + f.size + 26


def tile(path: Path, size: tuple[int, int]) -> Image.Image | None:
    try:
        return ImageOps.fit(Image.open(path).convert("RGB"), size, Image.Resampling.LANCZOS, centering=(0.5, 0.0))
    except Exception:
        return None


def render(evidence: dict, identity: dict | None, folder: Path, out: Path) -> Path:
    img = Image.new("RGB", (W, H), PAPER)
    d = ImageDraw.Draw(img)
    meta = evidence.get("meta") or {}
    name = (identity or {}).get("product") or meta.get("og_title") or meta.get("title") or evidence["brand_url"]
    tagline = (identity or {}).get("one_liner") or meta.get("description") or ""

    # Header
    d.text((M, M - 6), name[:48], font=font(52, "bold"), fill=INK)
    text_block(d, (M, M + 58), tagline, font(24), 1000, 1, fill=MUTED)
    tag = (identity or {}).get("category") or "DRAFT · run the identity agent"
    tf = font(16, "bold")
    tw = int(d.textlength(tag.upper(), font=tf)) + 28
    d.rounded_rectangle((W - M - tw, M, W - M, M + 34), radius=17, fill=INK)
    d.text((W - M - tw + 14, M + 8), tag.upper(), font=tf, fill=PAPER)
    d.line((M, 150, W - M, 150), fill=LINE, width=2)

    # Left: what the site actually looks like
    shots = [folder / s for s in evidence.get("screenshots", [])]
    imgs = [folder / s for s in evidence.get("images", []) if not s.startswith("icon")]
    hero = tile(shots[0], (900, 506)) if shots else None
    if hero:
        img.paste(hero, (M, 172))
        d.rectangle((M, 172, M + 900, 678), outline=LINE, width=2)
    row = [t for t in (tile(p, (292, 170)) for p in (shots[1:3] + imgs[:1])[:3]) if t]
    for i, t in enumerate(row):
        x = M + i * 304
        img.paste(t, (x, 692))
        d.rectangle((x, 692, x + 292, 862), outline=LINE, width=2)

    # Right: what it really is
    x, width, y = 990, W - M - 990, 172
    if identity:
        y = label(d, (x, y), "What it really is")
        y = text_block(d, (x, y), identity["what_it_really_is"], font(19), width, 5) + 14
        y = label(d, (x, y), "For")
        for seg in identity.get("audience", [])[:3]:
            y = text_block(d, (x, y), f"• {seg['name']}: {seg['pain']}", font(18), width, 2) + 2
        y = label(d, (x, y + 12), "Voice")
        y = chips(d, (x, y), identity["voice"]["adjectives"], width)
        y = label(d, (x, y), "Value")
        for vp in identity.get("value_props", [])[:3]:
            y = text_block(d, (x, y), f"• {vp['claim']}", font(18), width, 2) + 2
        if y < 790:
            y = label(d, (x, y + 12), "Keywords")
            chips(d, (x, y), identity.get("keywords", [])[:8], width, font(15))
    else:
        y = label(d, (x, y), "From the site")
        y = text_block(d, (x, y), meta.get("description") or "(no meta description)", font(19), width, 6) + 14
        y = label(d, (x, y), "Pages read")
        for p in evidence.get("pages", [])[:7]:
            y = text_block(d, (x, y), f"• {p.get('title') or p['url']}", font(16), width, 1, fill=MUTED)

    # Bottom: palette and type as rendered
    d.line((M, 884, W - M, 884), fill=LINE, width=2)
    hexes = (identity or {}).get("visual", {}).get("palette") or [c["hex"] for c in evidence.get("palette", [])]
    for i, hx in enumerate(hexes[:6]):
        sx = M + i * 118
        d.rounded_rectangle((sx, 902, sx + 104, 940), radius=8, fill=hx, outline=LINE, width=1)
        d.text((sx, 946), hx.upper(), font=font(13), fill=MUTED)
    fonts = (identity or {}).get("visual", {}).get("type") or evidence.get("fonts") or ["(not captured)"]
    fx = M + 6 * 118 + 30
    d.text((fx, 902), "TYPE", font=font(13, "bold"), fill=MUTED)
    d.text((fx, 922), " · ".join(fonts[:3]), font=font(22, "bold"), fill=INK)
    d.text((W - M - 360, 960), f"Evidence: {evidence['brand_url']}"[:60], font=font(12), fill=MUTED)

    out.parent.mkdir(parents=True, exist_ok=True)
    img.save(out)
    return out
