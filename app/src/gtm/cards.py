"""iMessage cards: one PNG per stage (1080x1350, 4:5) so the chat thread is the dashboard.

research -> what's trending (sources + top posts), analysis -> theme chart + 3 ideas, video -> frames,
qa -> persona scorecard, publish -> final caption + approval ask. Everything comes from the run's JSON files.
"""

import json
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

from .run import Run

W, H, PAD = 1080, 1350, 64
# Minimal, print-like: paper background, ink type, hairline rules; colour only for pass/fail.
BG, FG, MUTED, RULE, TRACK = (250, 249, 246), (17, 17, 17), (112, 112, 108), (222, 220, 214), (234, 232, 226)
ACCENT, GOOD, BAD = FG, (31, 110, 70), (168, 40, 30)
FONTS = {
    False: ["/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf", "/System/Library/Fonts/Helvetica.ttc"],
    True: ["/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf", "/System/Library/Fonts/Helvetica.ttc"],
}
STAGES = ["research", "analysis", "video", "qa", "publish"]


def font(size: int, bold: bool = False):
    for path in FONTS[bold]:
        if Path(path).exists():
            return ImageFont.truetype(path, size, index=1 if bold and path.endswith(".ttc") else 0)
    return ImageFont.load_default(size)


def clean(text: str) -> str:
    """Drop emoji and symbols the bundled fonts can't draw (they render as boxes)."""
    return "".join(ch for ch in str(text) if ord(ch) < 0x2190 or ch in "“”‘’…–—·")


def wrap(d: ImageDraw.ImageDraw, text: str, f, width: int, max_lines: int = 3) -> list[str]:
    lines, cur = [], ""
    for word in clean(text).split():
        while len(word) > 1 and d.textlength(word, font=f) > width:  # e.g. URLs: truncate instead of overflowing
            word = word[:-2] + "…"
        trial = f"{cur} {word}".strip()
        if d.textlength(trial, font=f) <= width:
            cur = trial
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    lines = [ln for ln in lines if ln]
    if len(lines) > max_lines:
        lines = lines[:max_lines]
        lines[-1] = lines[-1].rstrip(".,;: ") + "…"
    return lines


class Card:
    def __init__(self, r: Run, step: str, title: str):
        self.img = Image.new("RGB", (W, H), BG)
        self.d = ImageDraw.Draw(self.img)
        self.d.text((PAD, PAD), f"{step}".upper(), font=font(24), fill=MUTED)
        self.d.text((W - PAD - self.d.textlength(r.id, font=font(24)), PAD), r.id, font=font(24), fill=MUTED)
        self.y = PAD + 64
        self.text(title, 56, bold=True, lines=3, gap=1.15)
        self.y += 22
        self.d.line((PAD, self.y, W - PAD, self.y), fill=FG, width=2)
        self.y += 30

    def text(self, s: str, size: int, color=FG, bold=False, lines=3, x=PAD, width=W - 2 * PAD, gap=1.22):
        f = font(size, bold)
        for ln in wrap(self.d, s, f, width, lines):
            self.d.text((x, self.y), ln, font=f, fill=color)
            self.y += int(size * gap)

    def panel(self, height: int):
        """A section: hairline on top, no fill (keeps the card quiet)."""
        self.d.line((PAD, self.y, W - PAD, self.y), fill=RULE, width=1)
        top = self.y
        self.y += 22
        return top

    def bar(self, label: str, value: float, vmax: float, color=ACCENT):
        f = font(28)
        for ln in wrap(self.d, label, f, W - 2 * PAD - 60, 2):
            self.d.text((PAD, self.y), ln, font=f, fill=FG)
            self.y += 34
        full = W - 2 * PAD
        width = int(full * max(value, 0) / max(vmax, 1))
        self.d.rectangle((PAD, self.y + 8, PAD + full, self.y + 14), fill=TRACK)
        self.d.rectangle((PAD, self.y + 8, PAD + max(width, 6), self.y + 14), fill=color)
        self.y += 40

    def save(self, path: Path) -> Path:
        path.parent.mkdir(parents=True, exist_ok=True)
        self.img.save(path, optimize=True)
        return path


def research(r: Run) -> Path:
    ev, charts = r.read("evidence.json"), r.read("charts.json", {})
    c = Card(r, "1 · trend research", f"What's trending in {ev['brief']['niche']}")
    counts = (f"{len(ev['threads'])} threads read · {len(ev['news'])} news · "
              f"{sum(len(v) for v in ev.get('social_search', {}).values())} TikToks/Reels found · "
              f"{len(ev['youtube']['videos'])} Shorts · {len(ev.get('shots', []))} site captures")
    c.text(counts, 30, MUTED, lines=2)
    c.y += 20
    posts = charts.get("social_top") or []
    c.text("Top posts by engagement" if posts else "Top threads", 34, bold=True)
    c.y += 8
    items = ([(p["label"].split(": ", 1)[-1], f"{p.get('likes', 0):,} likes · {p['label'].split(':')[0]}") for p in posts[:4]]
             or [(t["title"], t["url"][:60]) for t in ev["threads"][:4]])
    for text, meta in items:
        top = c.panel(150)
        c.text(" ".join(text.split()), 30, bold=True, lines=2, x=PAD, width=W - 2 * PAD)
        c.text(meta, 24, MUTED, lines=1, x=PAD)
        c.y = max(c.y + 14, top + 118)
    c.y = max(c.y, H - 110)
    c.d.text((PAD, H - 90), "TinyFish Search · Fetch · Browser, Bright Data", font=font(24), fill=MUTED)
    return c.save(r.dir / "cards" / "1_research.png")


def analysis(r: Run) -> Path:
    ins, charts = r.read("insights.json"), r.read("charts.json", {})
    c = Card(r, "2 · analysis", f"Trend: {ins['template']['name']}")
    themes = charts.get("themes") or [{"label": t["name"], "value": t["weight"]} for t in ins["themes"]]
    for t in themes[:3]:
        c.bar(t["label"], t["value"], 10)
    c.y += 30
    c.text("3 content ideas", 36, bold=True)
    c.y += 6
    for n, idea in enumerate(ins.get("ideas", [])[:3], 1):
        top = c.panel(0)
        c.text(f"{n}. {idea['title']}", 30, bold=True, lines=2, x=PAD, width=W - 2 * PAD)
        c.text(f"“{idea['hook']}”", 26, MUTED, lines=2, x=PAD, width=W - 2 * PAD)
        c.y = max(c.y + 14, top + 118)
    return c.save(r.dir / "cards" / "2_analysis.png")


def video(r: Run, v: int) -> Path:
    info = r.read(f"video_v{v}.json")
    c = Card(r, f"3 · draft v{v}", f"Draft v{v}: {info['seconds']:.0f}s vertical reel")
    frames = [r.dir / f for f in info["frames"]]
    picks = [frames[i] for i in (0, len(frames) // 2, len(frames) - 1)] if len(frames) >= 3 else frames
    fw = (W - 2 * PAD - 2 * 20) // 3
    fh = int(fw * 16 / 9)
    for i, p in enumerate(picks):
        im = Image.open(p).convert("RGB").resize((fw, fh))
        c.img.paste(im, (PAD + i * (fw + 20), c.y))
    c.y += fh + 30
    c.text(f"{info.get('format', 'video')} · {info.get('mode', '')} · {info.get('engine', '')}".strip(" ·"), 28, MUTED, lines=1)
    c.text(info["transcript"].replace(" / ", " · "), 28, lines=4)
    return c.save(r.dir / "cards" / f"3_video_v{v}.png")


def qa(r: Run, v: int) -> Path:
    q = r.read(f"qa_v{v}.json")
    verdict = "PASSED" if q["passed"] else "needs changes"
    c = Card(r, f"4 · persona QA v{v}", f"QA v{v}: {q['avg_score']}/10, {verdict}")
    for rv in q["reviews"]:
        top = c.panel(176)
        c.d.text((PAD, c.y), rv["persona"][:34], font=font(30, True), fill=FG)
        score = rv["score_1_10"]
        c.d.text((W - PAD - 130, c.y - 4), f"{score}/10", font=font(40, True), fill=GOOD if score >= 7 else BAD)
        c.y += 46
        c.text(f"Fix: {rv['top_fix']}", 24, MUTED, lines=3, x=PAD, width=W - 2 * PAD)
        c.y = top + 192
    c.y += 6
    for b in q["blocking"][:3]:
        c.text("• " + b.replace("[MUST] ", ""), 24, BAD, lines=2)
    if q["passed"]:
        c.text("No blocking issues. Ready for your approval.", 30, GOOD, bold=True)
    c.d.text((PAD, H - 70), "Synthetic personas from public comments: hypotheses, not audience validation", font=font(22), fill=MUTED)
    return c.save(r.dir / "cards" / f"4_qa_v{v}.png")


def publish(r: Run) -> Path:
    pub = r.read("publish.json")
    c = Card(r, "5 · ready to post", "Final reel, ready for your approval" if pub.get("status") != "needs_human"
             else "QA didn't pass: needs a human call")
    frames = r.read(f"video_v{pub['version']}.json")["frames"] if pub.get("version") else []
    if frames:
        im = Image.open(r.dir / frames[0]).convert("RGB").resize((380, 676))
        c.img.paste(im, (PAD, c.y))
        y0, c.y = c.y, c.y
        copy = pub.get("copy") or {}
        caption = copy.get("reels_caption") or copy.get("tiktok_caption") if isinstance(copy, dict) else str(copy)
        tags = " ".join(copy.get("hashtags", [])[:6]) if isinstance(copy, dict) else ""
        c.text("Instagram Reels caption", 24, MUTED, lines=1, x=PAD + 410, width=W - 2 * PAD - 410)
        c.text(str(caption or ""), 28, lines=10, x=PAD + 410, width=W - 2 * PAD - 410)
        if tags:
            c.text(tags, 24, MUTED, lines=2, x=PAD + 410, width=W - 2 * PAD - 410)
        c.y = max(c.y, y0 + 700)
    if pub.get("qa_flags"):
        c.text("QA flagged: " + "; ".join(f.replace("[MUST] ", "").split(" (")[0] for f in pub["qa_flags"][:2]), 24, BAD, lines=3)
    c.text("Reply APPROVE to post. Posting is simulated in this demo.", 28, FG, bold=True, lines=2)
    return c.save(r.dir / "cards" / "5_publish.png")


def build(r: Run, stage: str = "all") -> list[Path]:
    out = []
    latest = max((v for v in range(1, 4) if r.exists(f"video_v{v}.json")), default=0)
    for s in (STAGES if stage == "all" else [stage]):
        try:
            if s == "research" and r.exists("evidence.json"):
                out.append(research(r))
            elif s == "analysis" and r.exists("insights.json"):
                out.append(analysis(r))
            elif s == "video" and latest:
                out.append(video(r, latest))
            elif s == "qa":  # revisions are rendered inside QA, so send the latest draft's card too
                for v in range(1, 4):
                    if r.exists(f"qa_v{v}.json"):
                        if v > 1 and r.exists(f"video_v{v}.json"):
                            out.append(video(r, v))
                        out.append(qa(r, v))
            elif s == "publish" and r.exists("publish.json"):
                out.append(publish(r))
        except Exception as e:  # a card must never break the pipeline
            r.log("cards", f"{s} card failed: {type(e).__name__}: {e}", level="warn")
    return out


# ── compact charts for iMessage app-card bubbles (3:2 JPEG; iOS overlays imageTitle/imageSubtitle on them) ──
CW, CH, CP = 1200, 800, 70


def _chart(rows: list[tuple[str, float, str]], vmax: float, path: Path, good_at: float | None = None) -> Path:
    """Horizontal bars: label above, bar, value at right. Paper/ink; colour only when good_at is given."""
    img = Image.new("RGB", (CW, CH), BG)
    d = ImageDraw.Draw(img)
    rows = rows[:4]
    step = (CH - 2 * CP) // max(len(rows), 1)
    for i, (label, value, shown) in enumerate(rows):
        y = CP + i * step + (step - 120) // 2
        vw = d.textlength(shown, font=font(56, True))
        label = " ".join(clean(label).split())
        while label and d.textlength(label, font=font(44, True)) > CW - 2 * CP - vw - 40:
            label = label[:-2].rstrip() + "…"
        d.text((CP, y), label, font=font(44, True), fill=FG)
        colour = FG if good_at is None else (GOOD if value >= good_at else BAD)
        d.text((CW - CP - vw, y - 6), shown, font=font(56, True), fill=colour)
        full = CW - 2 * CP
        d.rectangle((CP, y + 74, CP + full, y + 86), fill=TRACK)
        d.rectangle((CP, y + 74, CP + max(int(full * value / max(vmax, 1e-9)), 8), y + 86), fill=colour)
    path.parent.mkdir(parents=True, exist_ok=True)
    img.save(path, "JPEG", quality=88)
    return path


def chart_research(r: Run) -> Path:
    posts = (r.read("charts.json", {}) or {}).get("social_top") or []
    cut = lambda t: t.rsplit(" ", 1)[0].rstrip(" .,-") + "…" if len(t) >= 36 else t  # labels arrive cut at 36 chars
    rows = [(cut(p["label"].split(": ", 1)[-1]), p.get("likes") or 0, f"{p.get('likes') or 0:,}") for p in posts[:4]]
    if not rows:
        ev = r.read("evidence.json")
        rows = [(t["title"], 1, "") for t in ev["threads"][:4]]
    return _chart(rows, max(v for _, v, _ in rows) or 1, r.dir / "cards" / "chart_research.jpg")


def chart_analysis(r: Run) -> Path:
    ins = r.read("insights.json")
    rows = [(t["name"], t["weight"], f"{t['weight']}/10") for t in ins["themes"][:3]]
    return _chart(rows, 10, r.dir / "cards" / "chart_analysis.jpg")


def chart_qa(r: Run, v: int) -> Path:
    q = r.read(f"qa_v{v}.json")
    rows = [(rv["persona"], rv["score_1_10"], f"{rv['score_1_10']}/10") for rv in q["reviews"]]
    return _chart(rows, 10, r.dir / "cards" / f"chart_qa_v{v}.jpg", good_at=7)
