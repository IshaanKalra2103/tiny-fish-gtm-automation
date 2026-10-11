"""B2C GTM shorts (20-25s) riding a trend: talking-head UGC, product ads, brainrot.

The harness agent makes the reference images (people, product) with its own image generation
(e.g. Codex) and passes them as --ref. `demo` mode captions an image-built clip instantly;
`vizard` mode has Vizard animate the person, voice the script and edit, falling back to demo.
"""

from pathlib import Path

import tempfile

from . import fal, refs as refgen, templates, vizard
from .config import VidgenError

FORMATS = {
    "talking-head": ("UGC talking-head ad. The person in reference image 1 speaks straight to camera, "
                     "animated and lip-synced to a natural voiceover of the script; phone-shot, authentic feel; "
                     "bold word-by-word captions; any other references appear as quick cutaways."),
    "product": ("Product ad. Use the reference images (product shots, people using it) as the visuals with fast "
                "cuts and subtle motion; punchy voiceover of the script; bold captions; upbeat trending music."),
    "brainrot": ("Brainrot-style short. Split screen: top half the reference images with motion, bottom half "
                 "satisfying gameplay; fast voiceover of the script; huge word-by-word captions."),
}


SCENES = {  # two ~11s clips, joined: (opening, closing). {who} {brand} {trend} {a} {b} filled in.
    "talking-head": (
        "Vertical 9:16 handheld selfie UGC video. {who} talks excitedly straight to the camera about {brand}, "
        "holding the product up to the lens, riding the '{trend}' trend. She says: \"{a}\". Natural daylight, "
        "authentic TikTok creator style, clear speech, product label visible.",
        "Same creator, same room, continuing the selfie video: shows the {brand} product close up, uses it, "
        "then smiles at camera and says: \"{b}\". Natural daylight, authentic TikTok style, product visible."),
    "product": (
        "Vertical 9:16 premium product ad for {brand}, riding the '{trend}' trend: dynamic hero shots of the product, "
        "slow push-ins, light sweeps, fast rhythmic cuts, upbeat music. Voiceover: \"{a}\".",
        "Vertical 9:16 lifestyle shots of people happily using the {brand} product, then a final clean hero shot of "
        "the product on a simple background. Upbeat music. Voiceover: \"{b}\"."),
    "brainrot": (
        "Vertical 9:16 chaotic fast-paced meme-style TikTok video about {brand} and the '{trend}' trend: quick zooms, "
        "funny reactions, exaggerated expressions, energetic music. Voiceover: \"{a}\".",
        "Vertical 9:16 continuation of the chaotic meme video, ending on the {brand} product held to camera. "
        "Energetic music. Voiceover: \"{b}\"."),
}


def make(fmt: str, brand: str, trend: str, hook: str, lines: list[str], cta: str, refs: list[str], out: Path,
         mode: str = "demo", seconds: int = 22, wait: int = 900, person: str | None = None,
         product: str | None = None) -> dict:
    if fmt not in FORMATS:
        raise VidgenError(f"format must be one of {', '.join(FORMATS)}")
    refs = [r for r in refs if r]
    if not refs and mode != "fal":  # no refs passed: have Codex draw them (person first, so talking-head uses it as the face)
        for i, desc in enumerate(d for d in (person, product) if d):
            refs.append(str(refgen.generate(f"{desc}. Context: {brand}, riding the trend '{trend}'",
                                            out.parent / "refs" / f"{out.stem}_ref{i + 1}")))
    if mode == "fal":
        half = max(1, (len(lines) + 1) // 2)
        fill = {"who": person or "a relatable creator in their 20s", "brand": brand, "trend": trend,
                "a": " ".join([hook, *lines[:half]]), "b": " ".join([*lines[half:], cta])}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                clips = fal.generate([p.format(**fill) for p in SCENES[fmt]], Path(tmp), seconds=seconds / 2)
                base = fal.join(clips, Path(tmp) / "joined.mp4")
                res = templates.make_from_video(base, fmt, hook, lines, cta, out, tag=brand)
            return {**res, "format": fmt, "mode": "fal", "model": fal.MODEL}
        except VidgenError as e:
            fallback = {"error": f"fal: {e}"}
    elif mode == "vizard":
        script = " ".join([hook, *lines, cta])
        prompt = (f"{FORMATS[fmt]}\nBrand: {brand}. Trend it rides: {trend}.\n"
                  f"Script (say it, caption it): \"{script}\"\nHook in the first 2 seconds; end on the CTA.")
        try:
            res = vizard.make(prompt, refs, out, seconds=seconds, wait=wait)
            if res.get("ok"):
                return {**res, "format": fmt, "mode": "vizard"}
            fallback = res
        except VidgenError as e:
            fallback = {"error": str(e)}
    else:
        fallback = None
    if mode == "fal" and not refs and person:  # fal failed: demo needs a face, so have Codex draw it
        refs.append(str(refgen.generate(f"{person}. Context: {brand}, riding the trend '{trend}'",
                                        out.parent / "refs" / f"{out.stem}_ref1")))
    image = next((Path(r).expanduser() for r in refs if r and Path(r).expanduser().is_file()), None)
    res = (templates.make(fmt, hook, lines, cta, out, image=image, tag=brand) if image
           else templates.make("auto", hook, lines, cta, out, tag=brand))
    res.update({"format": fmt, "mode": "demo"})
    if fallback:
        res["vizard"] = fallback  # project id / question / error, so the agent can follow up later
    return res
