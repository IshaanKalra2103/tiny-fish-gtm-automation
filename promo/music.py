# /// script
# dependencies = ["httpx"]
# ///
"""Score for the Loopcast promo via the ElevenLabs Music API (section-timed composition plan, 120 BPM, 2 s bars).

uv run music.py <tag>   -> build/music_<tag>.mp3
Section boundaries follow the cut: problem 4-10 s, "Meet Loopcast" drop at 10 s, end-card breakdown at 50 s,
final hit at 54 s ringing out to 57.5 s. Key is read from the Keychain, never printed.
"""
import json, pathlib, subprocess, sys
import httpx

BAR_MS = 2000  # 120 BPM, 4/4
B = pathlib.Path(__file__).parent / "build"
KEY = subprocess.run(["security", "find-generic-password", "-s", "ELEVENLABS_API_KEY", "-w"],
                     capture_output=True, text=True, check=True).stdout.strip()

BASE = ["upbeat playful tech product launch music", "modern funky electro-pop", "120 BPM", "C major",
        "instrumental", "tight punchy drums", "handclaps", "bouncy syncopated synth bass", "plucky marimba-like synth",
        "bright staccato synth chords", "clean polished wide mix", "advert music bed that sits under a voiceover"]
NEG = ["vocals", "singing", "choir", "spoken word", "rap", "lo-fi", "cinematic orchestra", "dubstep", "trap",
       "heavy distortion", "chiptune"]


def chunk(name, ms, styles, neg=(), text=None):
    return {"text": text or f"[{name}]", "duration_ms": int(ms), "positive_styles": BASE + styles,
            "negative_styles": NEG + list(neg), "context_adherence": "high"}


PLAN = {"chunks": [
    chunk("Intro", 2 * BAR_MS, ["light and bouncy", "plucks and claps", "kick on every beat", "playful"]),
    chunk("Problem", 3 * BAR_MS, ["darker minor feel", "low-pass filtered groove", "ticking hi-hats like a clock",
                                  "muted", "late-night tension", "riser into a drop on the final beat"],
          ["full bright chords"]),
    chunk("Main", 20 * BAR_MS, ["drop on the first beat", "full bright groove", "confident and fun",
                                "four-on-the-floor kick", "funky slap-style synth bass", "claps on 2 and 4",
                                "plucky lead hook", "steady energy, no breakdowns"], ["breakdown", "silence"]),
    chunk("Breakdown", 2 * BAR_MS, ["drums and bass drop out", "only soft warm synth chords and plucks",
                                    "airy", "building anticipation"], ["kick drum", "bass groove", "snare"]),
    chunk("Outro", 3500, ["one big final hit with kick, bass and full chord on the first beat",
                          "then the chord rings out and decays to silence"], ["groove continues", "new melody", "fade in"],
          "[Outro]\n{one final hit, then ring out}"),
]}

if __name__ == "__main__":
    tag = sys.argv[1] if len(sys.argv) > 1 else "a"
    B.mkdir(exist_ok=True)
    print("total ms", sum(c["duration_ms"] for c in PLAN["chunks"]))
    r = httpx.post("https://api.elevenlabs.io/v1/music", params={"output_format": "mp3_44100_128"},
                   headers={"xi-api-key": KEY, "Content-Type": "application/json"},
                   json={"composition_plan": PLAN, "model_id": "music_v2_5"}, timeout=600)
    if r.status_code != 200:
        sys.exit(f"HTTP {r.status_code} {r.text[:800]}")
    out = B / f"music_{tag}.mp3"
    out.write_bytes(r.content)
    print(json.dumps({"ok": True, "out": str(out), "kb": len(r.content) // 1024}))
