"""ElevenLabs voiceover with per-word timings (they drive the captions and the cuts).

Results are cached by (text, voice, model, settings), so re-rendering a video
never spends characters twice.
"""

import base64
import hashlib
import json
import os
import re
from dataclasses import asdict, dataclass
from pathlib import Path

import httpx

from .config import CACHE, VidgenError, probe_duration, secret

API = "https://api.elevenlabs.io"
DEFAULT_MODEL = os.environ.get("ELEVENLABS_MODEL", "eleven_multilingual_v2")
FALLBACK_VOICE = "TX3LPaxmHKxFdv7VOQHJ"  # Liam, premade "Energetic, Social Media Creator"
VOICE_ID = re.compile(r"^[A-Za-z0-9]{20}$")


@dataclass
class Word:
    text: str
    start: float
    end: float


@dataclass
class Speech:
    audio: Path
    words: list[Word]
    duration: float
    voice_id: str
    chars: int
    cached: bool


def words_from_alignment(chars: list[str], starts: list[float], ends: list[float]) -> list[Word]:
    """Group ElevenLabs character timings into whitespace-separated words."""
    words: list[Word] = []
    buf, w_start, w_end = "", 0.0, 0.0
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if buf:
                words.append(Word(buf, w_start, w_end))
                buf = ""
            continue
        if not buf:
            w_start = s
        buf += ch
        w_end = e
    if buf:
        words.append(Word(buf, w_start, w_end))
    return words


class ElevenLabs:
    def __init__(self, api_key: str | None = None):
        key = api_key or secret("ELEVENLABS_API_KEY")
        if not key:
            raise VidgenError("no ElevenLabs key: set ELEVENLABS_API_KEY (harness/.env) or add it to the Keychain")
        self.http = httpx.Client(base_url=API, headers={"xi-api-key": key}, timeout=180)

    def voices(self) -> list[dict]:
        r = self.http.get("/v2/voices", params={"page_size": 100})
        r.raise_for_status()
        return [{"voice_id": v["voice_id"], "name": v["name"], "category": v.get("category"),
                 **{k: (v.get("labels") or {}).get(k) for k in ("gender", "accent", "age")}}
                for v in r.json()["voices"]]

    def credits(self) -> dict:
        r = self.http.get("/v1/user/subscription")
        r.raise_for_status()
        d = r.json()
        return {"tier": d["tier"], "used": d["character_count"], "limit": d["character_limit"],
                "remaining": d["character_limit"] - d["character_count"]}

    def resolve_voice(self, voice: str | None) -> str:
        """A voice id, or a name from the account ("miles", "liam", ...). Default: ELEVENLABS_VOICE_ID,
        then the Keychain's ELEVENLABS_VOICE_MILES, then a voice named "miles", then Liam."""
        voice = voice or secret("ELEVENLABS_VOICE_ID") or secret("ELEVENLABS_VOICE_MILES") or "miles"
        if VOICE_ID.match(voice):
            return voice
        want = voice.lower()
        voices = self.voices()
        for v in voices:
            if v["name"].lower() == want or v["name"].lower().split(" ")[0] == want:
                return v["voice_id"]
        for v in voices:
            if v["name"].lower().startswith(want):
                return v["voice_id"]
        if voice == "miles":
            return FALLBACK_VOICE
        raise VidgenError(f"no ElevenLabs voice named {voice!r}; run `vidgen voices`")

    def speak(self, text: str, voice: str | None = None, model: str | None = None, speed: float = 1.0,
              stability: float = 0.45, style: float = 0.0) -> Speech:
        text = " ".join(text.split())
        voice_id = self.resolve_voice(voice)
        settings = {"stability": stability, "similarity_boost": 0.8, "style": style,
                    "use_speaker_boost": True, "speed": max(0.7, min(1.2, speed))}
        model = model or DEFAULT_MODEL
        key = hashlib.sha256(json.dumps([text, voice_id, model, settings]).encode()).hexdigest()[:20]
        mp3, meta = CACHE / "tts" / f"{key}.mp3", CACHE / "tts" / f"{key}.json"
        if mp3.exists() and meta.exists():
            words = [Word(**w) for w in json.loads(meta.read_text())["words"]]
            return Speech(mp3, words, probe_duration(mp3), voice_id, len(text), cached=True)

        r = self.http.post(f"/v1/text-to-speech/{voice_id}/with-timestamps",
                           params={"output_format": "mp3_44100_128"},
                           json={"text": text, "model_id": model, "voice_settings": settings})
        if r.status_code != 200:
            raise VidgenError(f"ElevenLabs TTS {r.status_code}: {r.text[:300]}")
        d = r.json()
        a = d["alignment"]
        words = words_from_alignment(a["characters"], a["character_start_times_seconds"],
                                     a["character_end_times_seconds"])
        mp3.parent.mkdir(parents=True, exist_ok=True)
        mp3.write_bytes(base64.b64decode(d["audio_base64"]))
        meta.write_text(json.dumps({"text": text, "voice_id": voice_id, "model": model,
                                    "words": [asdict(w) for w in words]}))
        return Speech(mp3, words, probe_duration(mp3), voice_id, len(text), cached=False)
