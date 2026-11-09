# /// script
# requires-python = ">=3.11"
# ///
"""Write video/film.toml from the sorted takes (footage/index.json) and the screen recordings.

usage (repo root):
  uv run video/tools/build_film.py [--ring FILE] [--imessage FILE] [--coach TEXT] [--music FILE]
                                   [--pick C4=path ...] [--skip C8]

Takes: the last take of each clip id (by file name) unless --pick names one. V lines are cut to
footage/vo/<id>.wav (slate removed); C clips get in/out around the line. Screens come from
footage/screens/<take>.webm + <take>.marks.json (written by the recorder). Prints the running order and
total length, and every clip it could not find.
"""
import json
import os
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FOOT = ROOT / "footage"
VO_DIR = FOOT / "vo"
SCR = FOOT / "screens"
OUT = Path(os.environ["FILM_OUT"]).resolve() if os.environ.get("FILM_OUT") else ROOT / "video" / "film.toml"
INDEX = Path(os.environ.get("FILM_INDEX") or FOOT / "index.json").resolve()
URL = "https://mainstreet-ai-five.vercel.app"

args = sys.argv[1:]


def opt(name: str, default=None):
    return args[args.index(name) + 1] if name in args else default


picks = dict(a.split("=", 1) for i, a in enumerate(args) if i > 0 and args[i - 1] == "--pick")
skip = {a for i, a in enumerate(args) if i > 0 and args[i - 1] == "--skip"}
missing: list[str] = []

takes: dict[str, list[dict]] = {}
for r in json.loads(INDEX.read_text()):
    if r["clip"]:
        cid = r["clip"]
        if cid == "C2":  # both say "camera two": Ishaan's files live in footage/ishaan, Dylan's in footage/dylan
            cid = "C2B" if "/dylan/" in r["file"].lower() else "C2A"
        takes.setdefault(cid, []).append(r)


def rel(p) -> str:
    return str(Path("..") / Path(p).resolve().relative_to(ROOT))


def take(cid: str) -> dict | None:
    if cid in skip:
        return None
    if cid in picks:
        f = str(Path(picks[cid]).resolve())
        for t in takes.get(cid, []):
            if str(Path(t["file"]).resolve()) == f:
                return t
        missing.append(f"{cid} (picked file not in index)")
        return None
    ts = sorted(takes.get(cid, []), key=lambda t: t["file"])
    if not ts:
        missing.append(cid)
        return None
    return ts[-1]


def norm(w: str) -> str:
    return re.sub(r"[^a-z0-9%]", "", w.lower())


def line_words(t: dict) -> list[dict]:
    return [w for w in t["words"] if w["s"] >= (t["line_start"] or 0) - 0.01]


def find(words: list[dict], phrase: str) -> int | None:
    toks = [norm(x) for x in phrase.split()]
    ws = [norm(w["w"]) for w in words]
    for i in range(len(ws) - len(toks) + 1):
        if all(ws[i + k].startswith(toks[k]) for k in range(len(toks))):
            return i
    return None


def cut_audio(src: str, a: float, b: float, dst: Path) -> float:
    dst.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-ss", f"{max(0, a):.3f}", "-to", f"{b:.3f}", "-i", src,
                    "-vn", "-ac", "2", "-ar", "48000", str(dst)], check=True)
    return b - max(0, a)


def vo_parts(cid: str, splits: list[str] = ()) -> list[dict] | None:
    """Cut a V line into parts at the given phrases. Each part: file, dur, words (times relative to part)."""
    t = take(cid)
    if not t:
        return None
    ws = line_words(t)
    idx = [0] + [i for i in (find(ws, p) for p in splits) if i] + [len(ws)]
    idx = sorted(set(idx))
    parts = []
    for n, (i, j) in enumerate(zip(idx, idx[1:])):
        a, b = ws[i]["s"] - 0.12, ws[j - 1]["e"] + 0.3
        dst = VO_DIR / f"{cid}{'' if len(idx) == 2 else chr(97 + n)}.wav"
        d = cut_audio(t["file"], a, b, dst)
        parts.append({"file": rel(dst), "dur": round(d, 2),
                      "words": [{"w": w["w"], "s": round(w["s"] - a, 2)} for w in ws[i:j]]})
    return parts


def word_at(part: dict, phrase: str, default: float) -> float:
    i = find(part["words"], phrase)
    return round(part["words"][i]["s"], 2) if i is not None else default


def clip_inout(t: dict) -> tuple[float, float]:
    return round(max(0.0, t["line_start"] - 0.35), 2), round(min(t["duration"], t["line_end"] + 0.5), 2)


def marks(name: str) -> dict[str, float]:
    p = (Path(name).with_suffix(".marks.json") if "/" in name else SCR / f"{name}.marks.json")
    if not p.exists():
        return {}
    out = {}
    for m in json.loads(p.read_text()):
        out.setdefault(m["label"].split(" http")[0].strip(), m["t"])
    return out


def frame_size(p: Path) -> tuple[int, int]:
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=width,height",
                        "-of", "csv=p=0", str(p)], capture_output=True, text=True)
    try:
        w, h = r.stdout.strip().split(",")[:2]
        return int(w), int(h)
    except ValueError:
        return 0, 0


def media_len(p: Path) -> float:
    r = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(p)],
                       capture_output=True, text=True)
    try:
        return float(r.stdout.strip())
    except ValueError:
        return 0.0


# ---- toml writing -------------------------------------------------------------------------------
def tv(v) -> str:
    if isinstance(v, bool):
        return "true" if v else "false"
    if isinstance(v, (int, float)):
        return f"{v:g}" if isinstance(v, float) else str(v)
    if isinstance(v, str):
        return json.dumps(v)
    if isinstance(v, list):
        return "[" + ", ".join(tv(x) for x in v) + "]"
    if isinstance(v, dict):
        return "{ " + ", ".join(f"{k} = {tv(x)}" for k, x in v.items()) + " }"
    raise TypeError(v)


segs: list[dict] = []
order: list[str] = []


def seg(label: str, **kw) -> None:
    segs.append(kw)
    order.append(label)


def vo_list(p: dict, at: float = 0.3) -> list[dict]:
    return [{"file": p["file"], "at": at}]


def screen(label: str, name: str, a: str | None, b: str | None, part: dict | None, caption: str | None = None,
           pad: float = 0.9, **extra) -> None:
    f = Path(name) if "/" in name else SCR / f"{name}.webm"
    if not f.exists() or part is None:
        missing.append(f"screen {name} / vo for {label}")
        return
    m, total = marks(name), media_len(f)
    if f.parent == SCR:                  # our captures end on ~1 s of a mis-scaled frame (the closing screenshot)
        total = max(0.5, total - 1.2)
    t0 = m.get(a, 0.0) if a else 0.0
    t1 = m.get(b, total) if b else total
    need = part["dur"] + pad
    span = max(0.5, t1 - t0)
    # Footage longer than the voice: fast-forward. Shorter: slow down to at most 0.6x, then hold the
    # last frame (prep pads with it), so a beat never runs into the next one's footage.
    speed = round(span / need, 2) if span >= need else round(max(0.6, span / need), 2)
    kw = {"kind": "screen", "file": rel(f), "in": round(t0, 2), "out": round(t1, 2)}
    if f.parent == SCR and frame_size(f) == (1920, 1080):   # rec_screens: 1440x810 page, grey-padded to 1080p
        kw["crop"] = [0, 0, 1440, 810]
    if span / speed < need - 0.05:
        kw["dur"] = round(need, 2)
    if speed < 0.95:
        kw["speed"] = speed
        if caption:
            kw["caption"] = caption
    elif speed > 1.05:
        kw["speed"] = speed
        kw["caption"] = caption or f"Sped up {speed:.0f}x" if speed >= 1.5 else caption
    elif caption:
        kw["caption"] = caption
    kw["vo"] = vo_list(part)
    kw.update(extra)
    if kw.get("caption") is None:
        kw.pop("caption", None)
    seg(label, **kw)


def clip(cid: str, lower: dict | None = None, panel: dict | None = None, **extra) -> None:
    t = take(cid)
    if not t:
        return
    a, b = clip_inout(t)
    kw = {"kind": "clip", "file": rel(t["file"]), "in": a, "out": b}
    if lower:
        kw["lower_third"] = lower
    if panel:
        kw["panel"] = panel
    kw.update(extra)
    seg(cid, **kw)


def section(n: int, title: str, sub: str = "") -> None:
    kw = {"kind": "card", "style": "section", "eyebrow": f"Part {n} of 4", "title": title}
    if sub:
        kw["subtitle"] = sub
    seg(f"section {n}", **kw)


DYLAN = {"name": "Dylan", "line": "Team Forge"}
ISHAAN = {"name": "Ishaan Kalra", "line": "Team Forge"}

# ---- Part 0. The problem ------------------------------------------------------------------------
ring = opt("--ring")
if ring:
    seg("ring", kind="broll", file=rel(ring), **{"in": 0.0, "out": round(min(4.0, media_len(Path(ring))), 2)}, audio=True)
else:
    missing.append("--ring (ringing-phone B-roll)")
clip("C1", lower=DYLAN)

v1 = vo_parts("V1", ["Census"])
if v1:
    seg("V1a", kind="card", style="number", figure="27%", line="of calls to home-services businesses go unanswered",
        source="Source: Invoca, call-tracking data", vo=vo_list(v1[0]))
    if len(v1) > 1:
        seg("V1b", kind="card", style="pair",
            left={"figure": "1 in 5", "line": "U.S. businesses used AI in the past two weeks"},
            right={"figure": "22%", "line": "of firms not planning to use AI don't know what it can do"},
            source="Source: U.S. Census Bureau, Business Trends and Outlook Survey", vo=vo_list(v1[1]))

# C2: split screen, A = Ishaan (left), B = Dylan (right); each take holds two lines split by the longest pause.
def two_lines(t: dict) -> list[tuple[float, float]]:
    ws = line_words(t)
    if len(ws) < 2:
        return [(t["line_start"], t["line_end"])]
    gaps = [(ws[i + 1]["s"] - ws[i]["e"], i) for i in range(len(ws) - 1)]
    g, i = max(gaps)
    if g < 0.6:
        return [(ws[0]["s"], ws[-1]["e"])]
    return [(ws[0]["s"], ws[i]["e"]), (ws[i + 1]["s"], ws[-1]["e"])]


ta, tb = take("C2A"), take("C2B")
if ta and tb:
    la, lb = two_lines(ta), two_lines(tb)
    seq = [("A", la[0]), ("B", lb[0])] + ([("A", la[1])] if len(la) > 1 else []) + ([("B", lb[1])] if len(lb) > 1 else [])
    at, side_lines = 0.3, {"A": [], "B": []}
    for s, (a, b) in seq:
        side_lines[s].append({"in": round(a - 0.1, 2), "out": round(b + 0.2, 2), "at": round(at, 2)})
        at += (b - a) + 0.3 + 0.35
    seg("C2", kind="split", dur=round(at + 0.4, 2), left={"file": rel(ta["file"]), "lines": side_lines["A"]},
        right={"file": rel(tb["file"]), "lines": side_lines["B"]})
else:
    missing.append("C2 split needs both C2 takes (Ishaan's and Dylan's); tag them C2A / C2B with --pick or rename")

# ---- Part 1. The MVP ----------------------------------------------------------------------------
section(1, "The MVP: a working product", "Live site, live agent, a real Maryland business")
clip("C3", lower=ISHAAN)
v2 = vo_parts("V2")
screen("V2", "intake", "focus box", "results", v2[0] if v2 else None)
v3 = vo_parts("V3")
screen("V3", "intake", "results", None, v3[0] if v3 else None)
v4 = vo_parts("V4")
screen("V4", "deck", "compare open", "trust close", v4[0] if v4 else None)
v5 = vo_parts("V5")
screen("V5", "deck", "preview open", "preview close", v5[0] if v5 else None)
clip("C4", lower=DYLAN)
v6 = vo_parts("V6", ["Then it makes", "At the end"])
if v6:
    screen("V6a", "approval", None, None, v6[0])
    if len(v6) > 1:
        screen("V6b", "setup-stream", "start", "captcha", v6[1], caption="The setup agent in a cloud browser")
    if len(v6) > 2:
        screen("V6c", "setup", "setup record", None, v6[2], caption="What the owner gets back")
v7 = vo_parts("V7")
screen("V7", "helper", None, None, v7[0] if v7 else None)
v8 = vo_parts("V8")
imsg = opt("--imessage")
if v8 and imsg:
    screen("V8", str(Path(imsg).resolve()), None, None, v8[0])
else:
    missing.append("V8 + --imessage (Dylan's iMessage screen recording)")

# ---- Part 2. How we approached building it ------------------------------------------------------
section(2, "How we approached building it", "A checked catalog, an agent that does the work, rules in code")
clip("C5")
v9 = vo_parts("V9")
if v9:
    seg("V9", kind="card", style="image", file="../docs/video/architecture.png", vo=vo_list(v9[0], 0.4))
v10 = vo_parts("V10")
if v10:
    seg("V10", kind="card", style="image", file="../docs/video/catalog-pipeline.png", vo=vo_list(v10[0], 0.4))
v11 = vo_parts("V11")
if v11:
    p = v11[0]
    seg("V11", kind="card", style="bullets", title="Safety lives in code, not in a prompt", check=True, vo=vo_list(p, 0.4), items=[
        {"text": "No account without the owner's yes", "at": 0.6},
        {"text": "Websites can carry instructions, so the rule moved into code", "at": word_at(p, "website", 4.0) + 0.4},
        {"text": "The owner's answer sits in a folder the agent can only read", "at": word_at(p, "folder", 8.0) + 0.4},
        {"text": "Sign-up won't start without a yes for that exact tool", "at": word_at(p, "won't", 10.0) + 0.4},
        {"text": "No open web, no payment details, hard spending caps", "at": word_at(p, "No open", 13.0) + 0.4},
    ])
clip("C6")

# ---- Part 3. Evidence -------------------------------------------------------------------------
section(3, "Evidence it works and is worth it")
clip("C7")
v12 = vo_parts("V12")
if v12:
    p = v12[0]
    seg("V12", kind="card", style="bullets", title="Tonight's real runs", check=True, vo=vo_list(p, 0.4), items=[
        {"text": "A diner, an HVAC company and a salon: each under a minute", "at": 0.8},
        {"text": "261 candidate tools in, 85 approved", "at": word_at(p, "catalog", 5.0) + 0.4},
        {"text": "A planted instruction to break the rules: read and ignored", "at": word_at(p, "planted", 9.0) + 0.4},
        {"text": "A real sign-up: stopped at the human check, handed to the owner", "at": word_at(p, "setup agent", 14.0) + 0.4},
    ])
v13 = vo_parts("V13")
if v13:
    p = v13[0]
    seg("V13", kind="card", style="bullets", title="Why it's worth it", check=False, vo=vo_list(p, 0.4), items=[
        {"text": "More than 1 in 4 home-services calls go unanswered", "at": 0.8},
        {"text": "About 4 hours a week back for the salon (our agent's estimate)", "at": word_at(p, "salon", 6.0) + 0.3},
        {"text": "Owners not using AI say they don't know what it can do", "at": word_at(p, "Census", 10.0) + 0.3},
        {"text": "Finding, checking and setting up: the gap we fill", "at": word_at(p, "Finding", 14.0) + 0.3},
    ])
if take("C8"):
    clip("C8")
elif "C8" in missing:
    missing.remove("C8")

# ---- Part 4. The next 16 weeks ------------------------------------------------------------------
section(4, "The next 16 weeks", "Four blocks of four weeks")
BLOCKS = [
    {"label": "Weeks 1-4", "title": "Real owners", "line": "20 Maryland businesses with the SBDC"},
    {"label": "Weeks 5-8", "title": "The catalog", "line": "Playbooks, owner reviews, monitoring"},
    {"label": "Weeks 9-12", "title": "Scale", "line": "Hosted sandboxes, sign-in, Spanish"},
    {"label": "Weeks 13-16", "title": "People", "line": "Local helpers and SBDC distribution"},
]
for k, cid in enumerate(["C9", "C10", "C11", "C12", "C13"]):
    shown = [dict(b, at=0.0 if i < k - 1 else 0.6) for i, b in enumerate(BLOCKS) if i < k]
    hidden = [dict(b, at=999.0) for i, b in enumerate(BLOCKS) if i >= k]
    clip(cid, panel={"title": "The next 16 weeks", "blocks": shown + hidden})
clip("C14")

# ---- Close --------------------------------------------------------------------------------------
clip("C15", lower=ISHAAN)
coach = opt("--coach")
credits = {"kind": "card", "style": "credits", "title": "MainStreet AI", "names": ["Team Forge", "Ishaan Kalra and Dylan"],
           "url": URL, "dur": 6.0}
if coach:
    credits["coach"] = coach
seg("credits", **credits)

# ---- write ------------------------------------------------------------------------------------
lines = ["# Generated by video/tools/build_film.py from footage/index.json. Edit freely; rerun overwrites.", ""]
if opt("--music"):
    lines += [f"music = {tv({'file': rel(opt('--music')), 'gain_db': -26})}", ""]
for label, s in zip(order, segs):
    lines.append(f"# {label}")
    lines.append("[[seg]]")
    for k, v in s.items():
        lines.append(f"{k} = {tv(v)}")
    lines.append("")
OUT.write_text("\n".join(lines))
print(f"wrote {OUT.relative_to(ROOT)}: {len(segs)} segments")
print("order:", " ".join(order))
if missing:
    print("MISSING:", "; ".join(dict.fromkeys(missing)))
