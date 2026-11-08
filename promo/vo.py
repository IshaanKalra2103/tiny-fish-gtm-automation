# /// script
# dependencies = ["httpx"]
# ///
"""Loopcast promo voiceover: one ElevenLabs take, then each line is re-spaced onto the DMflo reference's line starts.

uv run vo.py take        # TTS (cached by text+settings) -> build/vo_take.mp3 + build/vo_take.json (word timings)
uv run vo.py place       # cut the take at line boundaries, place each line at its target start -> build/vo.wav + build/vo_words.json

Key comes from the Keychain (ELEVENLABS_API_KEY) and is never printed.
"""
import base64, hashlib, json, pathlib, subprocess, sys
import httpx

HERE = pathlib.Path(__file__).parent
B = HERE / "build"
VOICE = "EXAVITQu4vr4xnSDxMaL"  # Sarah, the voice the earlier Loopcast cut shipped with
MODEL = "eleven_multilingual_v2"
SETTINGS = {"stability": 0.4, "similarity_boost": 0.8, "style": 0.25, "use_speaker_boost": True, "speed": 1.15}

# (target start in seconds = the reference VO's line start, text)
LINES = [
    (0.10, "Your rival's reel just went viral."),
    (2.06, "What format? Can we copy it? By Friday?"),
    (4.25, "It's 1 AM and you're still pasting links in a doc."),
    (7.48, "Every trend you miss is reach you lose."),
    (10.36, "Meet Loopcast, your content loop on autopilot."),
    (13.62, "Text it your brand and a niche, and boom,"),
    (16.74, "a sourced, scripted reel lands in your texts."),
    (19.44, "Even better, it grades its own drafts, then waits for your yes."),
    (23.70, "Behind it, four TinyFish primitives."),
    (26.26, "Search finds this week's reels and threads."),
    (29.80, "Fetch reads them. Agent clicks through YouTube."),
    (32.64, "Browser grabs the pixels. From TikTok to TechCrunch,"),
    (36.34, "yes, even Reddit."),
    (37.70, "Watch it all from iMessage or the dashboard."),
    (41.04, "Or just run one command."),
    (43.94, "Research, script, render, review, right from your terminal."),
    (48.24, "Twenty-seven cents a run. Free to fork."),
    (50.74, "Loopcast. Every trend, turned into a reel."),
]
END = 57.5


def key():
    return subprocess.run(["security", "find-generic-password", "-s", "ELEVENLABS_API_KEY", "-w"],
                          capture_output=True, text=True, check=True).stdout.strip()


def words_from_alignment(a):
    out, buf, s0, e0 = [], "", 0.0, 0.0
    for ch, s, e in zip(a["characters"], a["character_start_times_seconds"], a["character_end_times_seconds"]):
        if ch.isspace():
            if buf: out.append({"w": buf, "s": s0, "e": e0}); buf = ""
            continue
        if not buf: s0 = s
        buf += ch; e0 = e
    if buf: out.append({"w": buf, "s": s0, "e": e0})
    return out


def take():
    text = " ".join(t for _, t in LINES)
    h = hashlib.sha256(json.dumps([text, VOICE, MODEL, SETTINGS]).encode()).hexdigest()[:16]
    mp3, meta = B / f"vo_take_{h}.mp3", B / f"vo_take_{h}.json"
    if not mp3.exists():
        r = httpx.post(f"https://api.elevenlabs.io/v1/text-to-speech/{VOICE}/with-timestamps",
                       params={"output_format": "mp3_44100_128"}, headers={"xi-api-key": key()},
                       json={"text": text, "model_id": MODEL, "voice_settings": SETTINGS}, timeout=300)
        if r.status_code != 200:
            sys.exit(f"ElevenLabs {r.status_code}: {r.text[:400]}")
        d = r.json()
        mp3.write_bytes(base64.b64decode(d["audio_base64"]))
        meta.write_text(json.dumps({"text": text, "words": words_from_alignment(d["alignment"])}))
    for p, q in ((mp3, B / "vo_take.mp3"), (meta, B / "vo_take.json")):
        q.unlink(missing_ok=True); q.symlink_to(p.name)
    print(json.dumps({"ok": True, "chars": len(text), "take": str(mp3)}))


def place():
    """Split the take into lines by word count, then lay each line down at max(target, prev_end + 0.12)."""
    words = json.loads((B / "vo_take.json").read_text())["words"]
    i, segs = 0, []
    for target, text in LINES:
        n = len(text.split())
        ws = words[i:i + n]; i += n
        segs.append((target, ws))
    assert i == len(words), (i, len(words))
    src = B / "vo_take.mp3"
    parts, placed, cursor = [], [], 0.0
    for k, (target, ws) in enumerate(segs):
        a = max(0.0, ws[0]["s"] - 0.06)
        # end of this line in the take: halfway into the pause before the next line
        b = (ws[-1]["e"] + segs[k + 1][1][0]["s"]) / 2 if k + 1 < len(segs) else ws[-1]["e"] + 0.5
        b = min(b, ws[-1]["e"] + 0.18)
        start = max(target, cursor + 0.12)
        parts.append((a, b, start))
        for w in ws:
            placed.append({"w": w["w"], "s": round(w["s"] - a + start, 3), "e": round(w["e"] - a + start, 3), "line": k})
        cursor = start + (b - a)
        drift = start - target
        print(f"L{k+1:02d} target {target:6.2f} start {start:6.2f} dur {b-a:5.2f} end {cursor:6.2f}"
              f"{'  DRIFT %+.2f' % drift if abs(drift) > 0.01 else ''}  {' '.join(w['w'] for w in ws)}")
    # ffmpeg: trim each line, delay it to its start, mix
    inputs, fl = [], []
    for k, (a, b, start) in enumerate(parts):
        fl.append(f"[0:a]atrim={a:.3f}:{b:.3f},asetpts=PTS-STARTPTS,afade=t=in:d=0.02,"
                  f"afade=t=out:st={b-a-0.04:.3f}:d=0.04,adelay={int(start*1000)}|{int(start*1000)}[l{k}]")
    fl.append("".join(f"[l{k}]" for k in range(len(parts))) + f"amix=inputs={len(parts)}:normalize=0,apad=whole_dur={END}[out]")
    subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", str(src), "-filter_complex", ";".join(fl), "-map", "[out]",
                    "-ar", "48000", "-ac", "2", "-t", str(END), str(B / "vo.wav")], check=True)
    (B / "vo_words.json").write_text(json.dumps(placed, indent=0))
    (B / "vo_words.js").write_text("window.VO_WORDS = " + json.dumps(placed) + ";\n")
    print(json.dumps({"ok": True, "out": str(B / "vo.wav"), "words": len(placed)}))


if __name__ == "__main__":
    B.mkdir(exist_ok=True)
    {"take": take, "place": place}[sys.argv[1]]()
