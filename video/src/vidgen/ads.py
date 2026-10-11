"""B2C GTM shorts (20-25s) riding a trend: talking-head UGC, product ads, brainrot.

The harness agent makes the reference images (people, product) with its own image generation
(e.g. Codex) and passes them as --ref. `demo` mode captions an image-built clip instantly;
`vizard` mode has Vizard animate the person, voice the script and edit, falling back to demo.
"""

from pathlib import Path

from . import refs as refgen, templates, vizard
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


def make(fmt: str, brand: str, trend: str, hook: str, lines: list[str], cta: str, refs: list[str], out: Path,
         mode: str = "demo", seconds: int = 22, wait: int = 900, person: str | None = None,
         product: str | None = None) -> dict:
    if fmt not in FORMATS:
        raise VidgenError(f"format must be one of {', '.join(FORMATS)}")
    refs = [r for r in refs if r]
    if not refs:  # no refs passed: have Codex draw them (person first, so talking-head uses it as the face)
        for i, desc in enumerate(d for d in (person, product) if d):
            refs.append(str(refgen.generate(f"{desc}. Context: {brand}, riding the trend '{trend}'",
                                            out.parent / "refs" / f"{out.stem}_ref{i + 1}")))
    if mode == "vizard":
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
    image = next((Path(r).expanduser() for r in refs if r and Path(r).expanduser().is_file()), None)
    res = (templates.make(fmt, hook, lines, cta, out, image=image) if image
           else templates.make("auto", hook, lines, cta, out))
    res.update({"format": fmt, "mode": "demo"})
    if fallback:
        res["vizard"] = fallback  # project id / question / error, so the agent can follow up later
    return res
