# /// script
# requires-python = ">=3.11"
# ///
"""Write video/film.toml from the sorted takes (footage/index.json) and the screen recordings.

usage (repo root):
  uv run video/tools/build_film.py [--ring FILE] [--ring-in S] [--ring-sfx FILE] [--imessage FILE] [--coach TEXT] [--music FILE]
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
SFX = FOOT / "sfx"
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
        parts.append({"file": rel(dst), "dur": round(d, 2), "src": t["file"], "src_in": round(max(0, a), 3),
                      "words": [{"w": w["w"], "s": round(w["s"] - a, 2)} for w in ws[i:j]]})
    return parts


FILL = "--no-fill" not in args   # stand in for missing V lines with silent, music-only beats


def vo_or_silent(cid: str, dur: float, splits: list[str] = ()) -> list[dict] | None:
    parts = vo_parts(cid, list(splits))
    if parts:
        return parts
    return [{"file": None, "dur": dur, "words": []}] if FILL else None


def word_at(part: dict, phrase: str, default: float) -> float:
    i = find(part.get("words", []), phrase)
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


def cam_for(p: dict | None, at: float, pos: str = "br") -> dict:
    """Face-cam bubble from the on-camera take a V line was cut from (Ishaan's takes only)."""
    if not p or not p.get("src") or "/ishaan/" not in str(Path(p["src"]).resolve()):
        return {}
    c = {"file": rel(p["src"]), "in": round(max(0.0, p["src_in"] - at), 2), "until": round(at + p["dur"] - 0.2, 2)}
    if pos != "br":
        c["pos"] = pos
    return {"cam": c}


def vo_list(p: dict, at: float = 0.3) -> list[dict]:
    return [{"file": p["file"], "at": at}] if p.get("file") else []


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
    if vo_list(part):
        kw["vo"] = vo_list(part)
        kw.update(cam_for(part, 0.3))
    kw.update(extra)
    if kw.get("caption") is None:
        kw.pop("caption", None)
    seg(label, **kw)


# Kinetic type per clip: (anchor phrase, lines, options). A beat lands as its anchor word is spoken.
L, B, A, M, H = "light", "bold", "accent", "mark", "huge"
KIN = {
    "C2A": [("technology problem", [("not a", L), ("technology", B), ("problem", L)], {}),
            ("finding problem", [("a", L), ("finding", A), ("problem.", B)], {"punch": True}),
            ("50", [("one directory:", L), ("50,000", H), ("tools", L)], {}),
            ("vendors pay", [("vendors pay", L), ("for placement", B)], {}),
            ("nobody helps", [("nobody", A), ("helps you", L), ("set it up", B)], {})],
    "C3": [("is life", [("everything", L), ("is", L), ("LIVE", H)], {"punch": True}),
           ("real site", [("the real", L), ("site", B)], {}),
           ("real agent", [("the real", L), ("agent", B)], {}),
           ("real Maryland", [("a real", L), ("Maryland", A), ("business", B)], {}),
           ("only reads", [("it only reads", L), ("public", B), ("websites", M)], {})],
    "C5": [("one question", [("we started from", L), ("one question", B)], {}),
           ("trust", [("what would it take", L), ("to trust", B), ("an AI tool?", A)], {"punch": True}),
           ("three parts", [("three", H), ("parts", L)], {}),
           ("catalog", [("1  a checked", L), ("catalog", B)], {}),
           ("agent that", [("2  an", L), ("agent", B), ("that does the work", L)], {}),
           ("safety", [("3  safety rules", L), ("in code", M)], {"punch": True})],
    "C6": [("tested", [("we tested it", L), ("like an owner", B)], {}),
           ("real websites", [("real websites", B), ("the live product", L)], {}),
           ("iMessage showed", [("bug:", A), ("raw formatting", B), ("in iMessage", L)], {}),
           ("reply showed", [("bug:", A), ("replies sent", B), ("twice", B)], {}),
           ("fixed both", [("fixed both", M), ("today", L)], {"punch": True})],
    "C7": [("Is this", [("is this", L), ("technically", B), ("possible?", B)], {}),
           ("running right", [("it's running", L), ("right now.", A)], {"punch": True})],
    # Dylan (anchors use Whisper's spellings: "company in" Hagerstown, "of person" checks)
    "C1": [("Dave runs", [("Dave runs a", L), ("two-van", B), ("HVAC company", L)], {}),
           ("company in", [("in", L), ("Hagerstown", A)], {}),
           ("under a", [("under a", L), ("furnace", B)], {}),
           ("phone is", [("his phone is", L), ("ringing", H)], {"punch": True}),
           ("Dave is made", [("Dave is", L), ("made up", B)], {}),
           ("missed call", [("the missed call", L), ("isn't.", M)], {"punch": True})],
    "C2B": [("Mainstreet AI", [("so we built", L), ("MainStreet AI", B)], {}),
            ("Think Angie", [("Angie's List", A), ("for AI tools", B)], {"punch": True}),
            ("reads your", [("it reads", L), ("your business", B)], {}),
            ("finds the jobs", [("finds the jobs", B), ("AI can take on", L)], {}),
            ("compares", [("compares", L), ("checked", A), ("tools", B)], {}),
            ("say yes", [("you say", L), ("yes", M)], {}),
            ("sets one", [("it sets one", L), ("up for you", A)], {"punch": True})],
    "C4": [("Every directory", [("every directory", L), ("stops at a list", B)], {}),
           ("one step", [("we go", L), ("one step", A), ("further", B)], {}),
           ("set the tool", [("and set", L), ("the tool up", B)], {}),
           ("never without", [("never without", L), ("the owner's", L), ("yes", M)], {"punch": True})],
    "C14": [("Why couldn't", [("why couldn't", L), ("a big AI company", B), ("do this?", L)], {}),
            ("They could", [("they could build", L), ("the chat", B)], {}),
            ("hard part", [("the", L), ("hard part", A)], {"punch": True}),
            ("catalog of", [("a catalog", B), ("a person checks", L), ("every week", L)], {}),
            ("Partners", [("partners", B), ("owners already trust", L)], {}),
            ("actually setting", [("actually", L), ("setting it up", M)], {"punch": True})],
    "C15": [("Mainstreet AI", [("that's", L), ("MainStreet AI", B)], {}),
            ("find the", [("we find", L), ("the AI tools", B)], {}),
            ("check them", [("check them", B)], {}),
            ("set them", [("set them up", A)], {"punch": True}),
            ("live right", [("live", H), ("right now", L)], {}),
            ("try it", [("try it with", L), ("your business", M)], {}),
            ("thanks for", [("thanks for", L), ("watching", B)], {})],
}


def kin_beats(cid: str, t: dict, t_in: float) -> list[dict]:
    ws = t["words"]
    out = []
    for phrase, lines, o in KIN.get(cid, []):
        i = find(ws, phrase)
        if i is None:
            print(f"  kin: {cid} anchor not found: {phrase!r}")
            continue
        out.append({"at": round(max(0.05, ws[i]["s"] - t_in - 0.04), 2), "lines": [list(x) for x in lines], **o})
    return sorted(out, key=lambda b: b["at"])


def clip(cid: str, lower: dict | None = None, panel: dict | None = None, start: str | None = None, **extra) -> None:
    t = take(cid)
    if not t:
        return
    a, b = clip_inout(t)
    i = find(t["words"], start) if start else None
    if i is not None:   # open on a later sentence (the earlier ones play elsewhere)
        a = round(t["words"][i]["s"] - 0.3, 2)
    kw = {"kind": "clip", "file": rel(t["file"]), "in": a, "out": b}
    beats = kin_beats(cid, t, a) if not panel else []
    if i is not None:
        beats = [bt for bt in beats if bt["at"] > 0.06]
    if beats:
        kw.update(kin=beats, reframe=[1.18, -170], kin_x=1262, kin_y=190)
        if SFX.exists():
            kw["sfx"] = [{"file": rel(SFX / "pop.wav"), "at": bt["at"], "gain_db": -22} for bt in beats]
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
    r_in = float(opt("--ring-in") or 0.0)
    kw = {"in": r_in, "out": round(min(r_in + 8.0, media_len(Path(ring))), 2)}
    has_audio = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a", "-show_entries", "stream=index",
                                "-of", "csv=p=0", ring], capture_output=True, text=True).stdout.strip() != ""
    if has_audio:
        kw["audio"] = True
    c1 = take("C1")
    c1_cut = None
    if c1:   # Dylan's first two sentences play over the ringing phone, then we cut to his face
        ws = c1["words"]
        i = find(ws, "Dave is made")
        if i:
            dst = VO_DIR / "C1-ring.wav"
            d = cut_audio(c1["file"], c1["line_start"] - 0.15, ws[i - 1]["e"] + 0.2, dst)
            kw["vo"] = [{"file": rel(dst), "at": 0.15}]
            kw["dur"] = round(max(kw["out"] - kw["in"], d + 0.35), 2)
            c1_cut = "Dave is made"
    if opt("--ring-sfx"):
        kw["sfx"] = [{"file": rel(opt("--ring-sfx")), "at": 0.0, "gain_db": -16 if c1_cut else -9}]
    seg("ring", kind="broll", file=rel(ring), **kw)
else:
    c1_cut = None
    missing.append("--ring (ringing-phone B-roll)")
clip("C1", lower=DYLAN, start=c1_cut)

v1 = vo_parts("V1", ["Census"]) or ([{"file": None, "dur": 3.4}, {"file": None, "dur": 4.6}] if FILL else None)
HIT = [{"file": rel(SFX / "hit.wav"), "at": 0.1, "gain_db": -14}] if SFX.exists() else []
if v1:
    kw = {"vo": vo_list(v1[0])} if v1[0].get("file") else {"dur": v1[0]["dur"]}
    seg("V1a", kind="card", style="number", figure="27%", line="of calls to home-services businesses go unanswered",
        source="Source: Invoca, call-tracking data", sfx=HIT, **kw)
    if len(v1) > 1:
        kw = {"vo": vo_list(v1[1])} if v1[1].get("file") else {"dur": v1[1]["dur"]}
        seg("V1b", kind="card", style="pair",
            left={"figure": "1 in 5", "line": "U.S. businesses used AI in the past two weeks"},
            right={"figure": "22%", "line": "of firms not planning to use AI don't know what it can do"},
            source="Source: U.S. Census Bureau, Business Trends and Outlook Survey", sfx=HIT, **kw)

# C2: split screen, A = Ishaan (left), B = Dylan (right); each take holds two lines split by the longest pause.
def two_lines(t: dict, after: str | None = None) -> list[tuple[float, float]]:
    ws = line_words(t)
    if len(ws) < 2:
        return [(t["line_start"], t["line_end"])]
    i = find(ws, after) if after else None
    if i is not None and i < len(ws) - 1:   # pinned split: the end of the first line, by word
        s2 = max(ws[i + 1]["s"], ws[i + 1]["e"] - 0.45)   # Whisper stretches the first word over the pause
        return [(ws[0]["s"], ws[i]["e"]), (s2, ws[-1]["e"])]
    gaps = [(ws[i + 1]["s"] - ws[i]["e"], i) for i in range(len(ws) - 1)]
    g, i = max(gaps)
    if g < 0.6:
        return [(ws[0]["s"], ws[-1]["e"])]
    return [(ws[0]["s"], ws[i]["e"]), (ws[i + 1]["s"], ws[-1]["e"])]


ta, tb = take("C2A"), take("C2B")
if ta and tb:
    # No split screen: cut between full-frame faces, one line each, only the speaker's picture and voice.
    la, lb = two_lines(ta, after="Ishan"), two_lines(tb, after="Forge")   # Dylan pauses longer mid-line 2 than after line 1
    seq = [(ta, "C2A", la[0], ISHAAN), (tb, "C2B", lb[0], DYLAN)]
    seq += [(ta, "C2A", la[1], None)] if len(la) > 1 else []
    seq += [(tb, "C2B", lb[1], None)] if len(lb) > 1 else []
    for n, (t, cid, (a, b), low) in enumerate(seq):
        a0, b0 = round(max(0.0, a - 0.25), 2), round(min(t["duration"], b + 0.35), 2)
        kw = {"kind": "clip", "file": rel(t["file"]), "in": a0, "out": b0}
        beats = [bt for bt in kin_beats(cid, t, a0) if 0.06 < bt["at"] < (b0 - a0) - 0.4]
        if beats:
            kw.update(kin=beats, reframe=[1.18, -170], kin_x=1262, kin_y=190)
            if SFX.exists():
                kw["sfx"] = [{"file": rel(SFX / "pop.wav"), "at": bt["at"], "gain_db": -22} for bt in beats]
        if low:
            kw["lower_third"] = low
        seg(f"C2.{n + 1}", **kw)
elif ta:
    clip("C2A")
    missing.append("C2B (Dylan's C2): C2 runs as Ishaan alone")
else:
    missing.append("C2 split needs both C2 takes (Ishaan's and Dylan's); tag them C2A / C2B with --pick or rename")

# ---- Part 1. The MVP ----------------------------------------------------------------------------
section(1, "Proof of concept: the MVP", "Text it or use the web: live agent, a real Maryland business")
clip("C3", lower=ISHAAN)
# iMessage first: it's the front door; the web is the view its link opens
v8 = vo_parts("V8")
IMSG = {"kind": "card", "style": "imessage", "contact": "MainStreet AI", "title": "Just text it.",
        "subtitle": "No app, no login. The link opens the web view.", 
        "note": "Demo note: our iMessage provider's free plan only answers numbers we approve, so iMessage is shown "
                "here as a live demo and is not in the shareable link. Opening it to everyone needs a paid plan "
                "(about $100). The web app link works for anyone.", "messages": [
            {"from": "me", "type": True, "at": 1.6, "text": "I run a hair salon in Westminster MD, what AI could help me?"},
            {"from": "them", "typing": 1.4, "at": 3.6, "text": "Here are four jobs AI can take off your plate at the salon:"},
            {"from": "them", "at": 4.6, "list": ["Online booking and reminders (about 3 hrs a week)",
                                                 "Social posts about your work (about 2 hrs a week)",
                                                 "Replies to Google and Yelp reviews (about 1 hr a week)",
                                                 "Texts to past clients (about 1 hr a week)"]},
            {"from": "them", "at": 6.2, "text": "I'd start with booking. Want me to compare a few tools for it?"},
            {"from": "them", "at": 7.6, "link": {"title": "Your salon's AI plan", "url": "mainstreet-ai-five.vercel.app"}}]}
if v8:
    IMSG["vo"] = vo_list(v8[0], 0.4)
    IMSG["dur"] = round(max(11.0, v8[0]["dur"] + 1.0), 2)
else:
    IMSG["dur"] = 11.0
if SFX.exists():
    IMSG["sfx"] = [{"file": rel(SFX / ("send.wav" if m["from"] == "me" else "receive.wav")), "at": m["at"], "gain_db": -16}
                   for m in IMSG["messages"]]
seg("V8", **IMSG)
v2 = vo_parts("V2")
screen("V2", "intake", "focus box", "results", v2[0] if v2 else None)
v3 = vo_parts("V3")
screen("V3", "intake", "results", None, v3[0] if v3 else None)
v4 = vo_or_silent("V4", 9.0)
screen("V4", "deck", "compare open", "trust close", v4[0] if v4 else None,
       caption=None if v4 and v4[0].get("file") else "Compare tools side by side, and see why we trust each one")
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
v7 = vo_or_silent("V7", 4.5)
screen("V7", "helper", None, None, v7[0] if v7 else None,
       caption=None if v7 and v7[0].get("file") else "Prefer a person? A vetted local helper can set it up")

# ---- Part 2. How we approached building it ------------------------------------------------------
section(2, "How we approached building it", "A checked catalog, an agent that does the work, rules in code")
clip("C5")
v9 = vo_parts("V9", ["which is an agentic", "It can only"])
if v9:
    keep = [v9[0], v9[2]] if len(v9) == 3 else v9   # the middle part is an ad-lib
    at, vos = 0.4, []
    for part in keep:
        vos.append({"file": part["file"], "at": round(at, 2)})
        at += part["dur"] + 0.1
    seg("V9", kind="card", style="image", file="../docs/video/architecture.png", vo=vos)
v10 = vo_or_silent("V10", 6.0)
if v10:
    kw = {"vo": vo_list(v10[0], 0.4)} if v10[0].get("file") else {"dur": v10[0]["dur"]}
    seg("V10", kind="card", style="image", file="../docs/video/catalog-pipeline.png", **kw)
v11 = vo_parts("V11")
if v11:
    p = v11[0]
    seg("V11", kind="card", style="bullets", title="Safety lives in code, not in a prompt", check=True, vo=vo_list(p, 0.4), **cam_for(p, 0.4), items=[
        {"text": "No account without the owner's yes", "at": 0.6},
        {"text": "Websites can carry instructions, so the rule moved into code", "at": word_at(p, "website", 4.0) + 0.4},
        {"text": "The owner's answer sits in a folder the agent can only read", "at": word_at(p, "folder", 8.0) + 0.4},
        {"text": "Sign-up won't start without a yes for that exact tool", "at": word_at(p, "won't", 10.0) + 0.4},
        {"text": "No open web, no payment details, hard spending caps", "at": word_at(p, "No open", 13.0) + 0.4},
    ])
clip("C6")

# ---- Part 3. The next 16 weeks ------------------------------------------------------------------
section(3, "How we'd tackle it in 16 weeks", "Four blocks of four weeks")
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

# ---- Part 4. Evidence -------------------------------------------------------------------------
section(4, "Evidence it's technically possible and valuable", "It runs today, and it saves owners time")
clip("C7")
v12 = vo_parts("V12")
if v12:
    p = v12[0]
    seg("V12", kind="card", style="bullets", title="Proof it works: today's live runs", check=True, vo=vo_list(p, 0.4), **cam_for(p, 0.4), items=[
        {"text": "A diner, an HVAC company and a salon: each under a minute", "at": 0.8},
        {"text": "261 candidate tools in, 85 approved", "at": word_at(p, "catalog", 5.0) + 0.4},
        {"text": "A planted instruction to break the rules: read and ignored", "at": word_at(p, "planted", 9.0) + 0.4},
        {"text": "A real sign-up: stopped at the human check, handed to the owner", "at": word_at(p, "setup agent", 14.0) + 0.4},
    ])
v13 = vo_or_silent("V13", 8.0)
if v13:
    p = v13[0]
    kw = {"vo": vo_list(p, 0.4)} if p.get("file") else {"dur": p["dur"]}
    seg("V13", kind="card", style="bullets", title="Why it's worth it", check=False, **kw, items=[
        {"text": "More than 1 in 4 home-services calls go unanswered", "at": 0.8},
        {"text": "About 4 hours a week back for the salon (our agent's estimate)", "at": word_at(p, "salon", 6.0) + 0.3},
        {"text": "Owners not using AI say they don't know what it can do", "at": word_at(p, "Census", 10.0) + 0.3},
        {"text": "Finding, checking and setting up: the gap we fill", "at": word_at(p, "Finding", 14.0) + 0.3},
    ])
if v13 and not v13[0].get("file"):   # silent stand-in: reveal the four lines faster
    for k, it in enumerate(segs[-1]["items"]):
        it["at"] = round(0.6 + 1.5 * k, 2)
if take("C8"):
    clip("C8")
elif "C8" in missing:
    missing.remove("C8")

# ---- Close --------------------------------------------------------------------------------------
clip("C15", lower=ISHAAN)
coach = opt("--coach")
credits = {"kind": "card", "style": "credits", "title": "MainStreet AI", "names": ["Team Forge", "Ishaan Kalra and Dylan"],
           "url": URL, "dur": 6.0}
if coach:
    credits["coach"] = coach
seg("credits", **credits)

# ---- transitions: slide into screens, zoom into cards, whoosh on each -----------------------------
for i in range(1, len(segs)):
    k, prev = segs[i], segs[i - 1]
    if k.get("style") == "section" or prev.get("style") == "section" or k.get("kind") == "split" or "fade" in k:
        continue
    trans = "slide" if k["kind"] in ("screen",) else "zoom" if k["kind"] == "card" else None
    if not trans:
        continue
    k["fade"], k["trans"] = 0.3, trans
    if SFX.exists():
        k.setdefault("sfx", []).insert(0, {"file": rel(SFX / "whoosh.wav"), "at": -0.05 if False else 0.0, "gain_db": -18})

# ---- write ------------------------------------------------------------------------------------
lines = ["# Generated by video/tools/build_film.py from footage/index.json. Edit freely; rerun overwrites.", ""]
if opt("--music"):
    lines += [f"music = {tv({'file': rel(opt('--music')), 'gain_db': float(opt('--music-gain') or -9)})}", ""]
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
