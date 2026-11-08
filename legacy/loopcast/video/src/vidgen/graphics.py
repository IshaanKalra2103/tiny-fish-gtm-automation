"""Pillow-drawn overlays (captions, Reddit card, banners, listicle badges) and the
overlay track that flattens them into one transparent PNG sequence for ffmpeg.

Text is drawn here rather than in ffmpeg because Homebrew's ffmpeg ships without
drawtext/libass.
"""

from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

from .config import FONTS, FPS, H, W

FALLBACK_FONTS = [
    "/System/Library/Fonts/Supplemental/Arial Black.ttf",
    "/System/Library/Fonts/Supplemental/Impact.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
]


@lru_cache(maxsize=64)
def font(size: int, weight: str = "Black") -> ImageFont.FreeTypeFont:
    for path in [FONTS / f"Montserrat-{weight}.ttf", *FALLBACK_FONTS]:
        if Path(path).exists():
            return ImageFont.truetype(str(path), size)
    return ImageFont.load_default(size)


def hex_rgb(color: str) -> tuple[int, int, int]:
    c = color.lstrip("#")
    return tuple(int(c[i:i + 2], 16) for i in (0, 2, 4))


def snap(t: float) -> float:
    return round(t * FPS) / FPS


@dataclass
class Sprite:
    """An RGBA image placed at (x, y) on the 1080x1920 frame."""
    image: Image.Image
    x: int
    y: int


def _wrap(words: list[str], f: ImageFont.FreeTypeFont, max_w: int) -> list[list[int]]:
    lines: list[list[int]] = [[]]
    for i, w in enumerate(words):
        trial = " ".join(words[j] for j in lines[-1] + [i])
        if lines[-1] and f.getlength(trial) > max_w:
            lines.append([i])
        else:
            lines[-1].append(i)
    return lines


def caption(words: list[str], active: int | None, center_y: int, size: int = 92, scale: float = 1.0,
            color: str = "#FFFFFF", highlight: str = "#FFE600", stroke: int = 11, max_w: int = 940) -> Sprite:
    """Bold outlined caption; the `active` word gets the highlight colour."""
    words = [w.upper() for w in words]
    f = font(max(12, int(size * scale)))
    sw = max(2, int(stroke * scale))
    lines = _wrap(words, f, max_w)
    space = f.getlength(" ")
    asc, desc = f.getmetrics()
    line_h = int((asc + desc) * 1.02)
    widths = [sum(f.getlength(words[i]) for i in line) + space * (len(line) - 1) for line in lines]
    cw, ch = int(max(widths)) + sw * 2 + 24, line_h * len(lines) + sw * 2 + 24
    img = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    shadow = Image.new("RGBA", (cw, ch), (0, 0, 0, 0))
    d, sd = ImageDraw.Draw(img), ImageDraw.Draw(shadow)
    for li, line in enumerate(lines):
        x = (cw - widths[li]) / 2
        y = 12 + sw + li * line_h
        for i in line:
            fill = hex_rgb(highlight) if i == active else hex_rgb(color)
            sd.text((x + 5, y + 7), words[i], font=f, fill=(0, 0, 0, 150), stroke_width=sw, stroke_fill=(0, 0, 0, 150))
            d.text((x, y), words[i], font=f, fill=fill, stroke_width=sw, stroke_fill=(0, 0, 0))
            x += f.getlength(words[i]) + space
    shadow = shadow.filter(ImageFilter.GaussianBlur(6))
    shadow.alpha_composite(img)
    return Sprite(shadow, (W - cw) // 2, center_y - ch // 2)


def _rounded(size: tuple[int, int], radius: int, fill, shadow: bool = True) -> Image.Image:
    pad = 30 if shadow else 0
    img = Image.new("RGBA", (size[0] + pad * 2, size[1] + pad * 2), (0, 0, 0, 0))
    if shadow:
        sh = Image.new("RGBA", img.size, (0, 0, 0, 0))
        ImageDraw.Draw(sh).rounded_rectangle((pad, pad + 8, pad + size[0], pad + size[1] + 8), radius, fill=(0, 0, 0, 110))
        img = sh.filter(ImageFilter.GaussianBlur(14))
    ImageDraw.Draw(img).rounded_rectangle((pad, pad, pad + size[0], pad + size[1]), radius, fill=fill)
    return img


def banner(text: str, center_y: int, size: int = 58, dark: bool = False, max_w: int = 900) -> Sprite:
    """TikTok-style text box: black text on white (or white on black)."""
    f = font(size, "Bold")
    words = text.split()
    lines = [" ".join(words[i] for i in line) for line in _wrap(words, f, max_w)]
    asc, desc = f.getmetrics()
    line_h = int((asc + desc) * 1.08)
    bw = int(max(f.getlength(t) for t in lines)) + 64
    bh = line_h * len(lines) + 40
    box = _rounded((bw, bh), 22, (16, 16, 16, 235) if dark else (255, 255, 255, 250))
    d = ImageDraw.Draw(box)
    for i, t in enumerate(lines):
        d.text((30 + (bw - f.getlength(t)) / 2, 30 + 20 + i * line_h), t, font=f,
               fill=(255, 255, 255) if dark else (18, 18, 18))
    return Sprite(box, (W - box.width) // 2, center_y - box.height // 2)


def badge(number: int, label: str | None, top: int = 230, color: str = "#FFE600") -> list[Sprite]:
    """Listicle rank ("#3") with the item label under it."""
    out = [caption([f"#{number}"], 0, top + 95, size=170, highlight=color, stroke=14)]
    if label:
        out.append(caption(label.split(), None, top + 270, size=66, stroke=9))
    return out


def gradient(top: bool = True, bottom: bool = True, strength: int = 170) -> Sprite:
    """Dark fades at the top and bottom so text stays readable over busy images."""
    col = Image.new("L", (1, H), 0)
    px = col.load()
    for y in range(H):
        a = 0
        if top and y < 620:
            a = max(a, int(strength * (1 - y / 620) ** 1.6))
        if bottom and y > H - 760:
            a = max(a, int(strength * ((y - (H - 760)) / 760) ** 1.6))
        px[0, y] = a
    alpha = col.resize((W, H))
    img = Image.new("RGBA", (W, H), (0, 0, 0, 255))
    img.putalpha(alpha)
    return Sprite(img, 0, 0)


def _fmt_count(n: int) -> str:
    return f"{n / 1000:.1f}k".replace(".0k", "k") if n >= 1000 else str(n)


def reddit_card(title: str, subreddit: str = "r/AskReddit", author: str = "u/throwaway", upvotes: int = 24100,
                comments: int = 3200, center_y: int = 860) -> Sprite:
    cw, pad = 960, 40
    tf = font(50, "Bold")
    lines = [" ".join(title.split()[i] for i in line) for line in _wrap(title.split(), tf, cw - pad * 2)]
    asc, desc = tf.getmetrics()
    lh = int((asc + desc) * 1.12)
    ch = pad + 84 + 26 + lh * len(lines) + 30 + 56 + pad
    card = _rounded((cw, ch), 30, (255, 255, 255, 255))
    d = ImageDraw.Draw(card)
    ox, oy = 30 + pad, 30 + pad
    # header: avatar, subreddit, author
    d.ellipse((ox, oy, ox + 84, oy + 84), fill=(255, 69, 0))
    d.ellipse((ox + 22, oy + 26, ox + 62, oy + 62), fill=(255, 255, 255))
    d.ellipse((ox + 31, oy + 37, ox + 39, oy + 45), fill=(255, 69, 0))
    d.ellipse((ox + 45, oy + 37, ox + 53, oy + 45), fill=(255, 69, 0))
    d.text((ox + 104, oy + 4), subreddit, font=font(36, "Bold"), fill=(26, 26, 27))
    d.text((ox + 104, oy + 48), f"{author}  ·  6h", font=font(28, "Bold"), fill=(124, 124, 124))
    y = oy + 84 + 26
    for t in lines:
        d.text((ox, y), t, font=tf, fill=(26, 26, 27))
        y += lh
    # footer: upvote arrow + count, comment bubble + count
    y += 30
    d.polygon([(ox + 18, y + 4), (ox + 36, y + 30), (ox, y + 30)], fill=(255, 69, 0))
    d.rectangle((ox + 11, y + 30, ox + 25, y + 46), fill=(255, 69, 0))
    sf = font(34, "Bold")
    d.text((ox + 52, y + 4), _fmt_count(upvotes), font=sf, fill=(26, 26, 27))
    bx = ox + 52 + int(sf.getlength(_fmt_count(upvotes))) + 60
    d.rounded_rectangle((bx, y + 6, bx + 40, y + 36), 10, outline=(124, 124, 124), width=5)
    d.polygon([(bx + 8, y + 34), (bx + 18, y + 34), (bx + 6, y + 46)], fill=(124, 124, 124))
    d.text((bx + 56, y + 4), _fmt_count(comments), font=sf, fill=(26, 26, 27))
    return Sprite(card, (W - card.width) // 2, center_y - card.height // 2)


def cover(img: Image.Image, size: tuple[int, int], blur_fill: bool = True) -> Image.Image:
    """Fit `img` into `size`. If the aspect differs a lot, the image sits whole on a blurred,
    enlarged copy of itself (no faces or text cropped away); otherwise it is center-cropped."""
    tw, th = size
    ia, ta = img.width / img.height, tw / th
    if not blur_fill or 0.8 < ia / ta < 1.25:
        return ImageOps.fit(img, size, Image.LANCZOS)
    bg = ImageOps.fit(img, (tw // 8, th // 8), Image.BILINEAR).filter(ImageFilter.GaussianBlur(6))
    bg = bg.resize(size, Image.BILINEAR)
    bg = Image.blend(bg, Image.new("RGB", size, (0, 0, 0)), 0.35)
    fg = ImageOps.contain(img, (tw, int(th * 0.9)) if ia < ta else (tw, th), Image.LANCZOS)
    bg.paste(fg, ((tw - fg.width) // 2, (th - fg.height) // 2))
    return bg


@dataclass
class Layer:
    start: float
    end: float
    sprites: list[Sprite]
    z: int = 0


def write_track(layers: list[Layer], total: float, folder: Path) -> Path:
    """Flatten timed layers into PNG frames plus an ffmpeg concat list (one frame per change)."""
    folder.mkdir(parents=True, exist_ok=True)
    for L in layers:
        L.start, L.end = snap(max(0.0, L.start)), snap(min(total, L.end))
    cuts = sorted({0.0, snap(total), *(L.start for L in layers), *(L.end for L in layers)})
    entries: list[tuple[tuple, float]] = []
    for a, b in zip(cuts, cuts[1:]):
        if b - a < 1e-6:
            continue
        key = tuple(i for i, L in enumerate(layers) if L.start <= a < L.end)
        if entries and entries[-1][0] == key:
            entries[-1] = (key, entries[-1][1] + (b - a))
        else:
            entries.append((key, b - a))
    files: dict[tuple, Path] = {}
    lines = ["ffconcat version 1.0"]
    for key, dur in entries:
        if key not in files:
            frame = Image.new("RGBA", (W, H), (0, 0, 0, 0))
            for i in sorted(key, key=lambda i: layers[i].z):
                for s in layers[i].sprites:
                    frame.alpha_composite(s.image, (max(0, s.x), max(0, s.y)))
            files[key] = folder / f"ov_{len(files):04d}.png"
            frame.save(files[key], compress_level=1)
        lines += [f"file '{files[key].resolve()}'", f"duration {dur:.6f}"]
    lines.append(f"file '{files[entries[-1][0]].resolve()}'")  # concat demuxer needs the last frame twice
    track = folder / "overlay.ffconcat"
    track.write_text("\n".join(lines) + "\n")
    return track
