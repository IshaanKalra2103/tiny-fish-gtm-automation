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


NO_TEXT = "No text, captions, logos or watermarks on screen."
HANDS_OFF = "The product stays closed the whole time: nobody opens, pours, squeezes, sprays or applies it."

# Two ~11s clips joined into one ad: (opening, closing). Filled: who, brand, setting, a, b.
# Each clip is a precise shot: setting, subject, exact action, forbidden actions, camera, light, continuity.
SCENES = {
    "talking-head": (
        "Subject: {who}. Vertical 9:16 selfie video this person films on a phone held at arm's length. "
        "Setting: {setting}. They stand still, facing the camera. Action: the creator holds the {brand} product in one hand beside "
        "their face, label facing the camera, and talks directly into the lens with small natural hand gestures. "
        f"{HANDS_OFF} Dialogue: \"{{a}}\". Camera: steady handheld, eye level, medium close-up from the chest up, "
        f"face and product both in frame. Lighting: soft natural daylight. Style: realistic TikTok UGC. {NO_TEXT}",
        "Subject: {who}. Continuation of the same selfie video: the same person, same outfit, same location ({setting}), same daylight. "
        "Action: they bring the {brand} product toward the lens for a two-second close-up of the label, then lower "
        "it back beside their face and smile while talking. "
        f"{HANDS_OFF} Dialogue: \"{{b}}\". Camera: steady handheld, eye level, medium close-up from the chest up. "
        f"Style: realistic TikTok UGC. {NO_TEXT}"),
    "product": (
        "Vertical 9:16 studio product commercial. The {brand} product stands upright and alone on a clean, "
        "seamless light backdrop. Camera: slow dolly-in toward the label, then a slow quarter orbit around the "
        f"product. Lighting: soft key light with one gentle highlight sweeping across the packaging. No people, no "
        f"hands. {HANDS_OFF} Voiceover: \"{{a}}\". {NO_TEXT}",
        "Vertical 9:16 product commercial, same product as before, now placed in {setting}, styled neatly with a "
        "few matching props. Camera: slow push-in that ends on a centred hero shot of the label, product sharp and "
        f"fully in frame. Soft natural light. No people, no hands. {HANDS_OFF} Voiceover: \"{{b}}\". {NO_TEXT}"),
    "brainrot": (
        "Vertical 9:16 fast-paced meme-style selfie video. Setting: {setting}. Subject: {who}. Action: the creator "
        "reacts to the camera with big, funny, exaggerated expressions, then holds up the {brand} product like a "
        f"surprising discovery. {HANDS_OFF} Camera: quick punch-in zooms, handheld energy. Voiceover: \"{{a}}\". "
        f"{NO_TEXT}",
        "Continuation of the same meme video: same creator, outfit and location ({setting}). Action: they point at the "
        "{brand} product, nod with an over-the-top approving face, and end holding it centred and still toward "
        f"the lens. {HANDS_OFF} Camera: quick punch-in zooms. Voiceover: \"{{b}}\". {NO_TEXT}"),
}

SETTINGS = [  # product category hints -> a setting where the product makes sense
    (("shampoo", "hair", "shower", "skin", "soap", "body", "lotion", "beauty", "makeup", "serum", "deodorant"),
     "a bright, tidy modern bathroom with a large mirror and a white vanity behind them"),
    (("coffee", "tea", "snack", "food", "drink", "kitchen", "cook", "protein", "cereal"),
     "a bright, tidy home kitchen with a marble counter behind them"),
    (("shoe", "sneaker", "run", "fitness", "gym", "workout", "athletic"),
     "a bright gym with equipment softly blurred behind them"),
]


def setting_for(*hints: str) -> str:
    text = " ".join(hints).lower()
    for words, place in SETTINGS:
        if any(w in text for w in words):
            return place
    return "a bright, tidy, modern living room with soft daylight from a window behind them"


def make(fmt: str, brand: str, trend: str, hook: str, lines: list[str], cta: str, refs: list[str], out: Path,
         mode: str = "demo", seconds: int = 22, wait: int = 900, person: str | None = None,
         product: str | None = None, setting: str | None = None) -> dict:
    if fmt not in FORMATS:
        raise VidgenError(f"format must be one of {', '.join(FORMATS)}")
    refs = [r for r in refs if r]
    if not refs and mode != "fal":  # no refs passed: have Codex draw them (person first, so talking-head uses it as the face)
        for i, desc in enumerate(d for d in (person, product) if d):
            refs.append(str(refgen.generate(f"{desc}. Context: {brand}, riding the trend '{trend}'",
                                            out.parent / "refs" / f"{out.stem}_ref{i + 1}")))
    if mode == "fal":
        half = max(1, (len(lines) + 1) // 2)
        fill = {"who": person or "a relatable creator in their 20s", "brand": brand,
                "setting": setting or setting_for(brand, trend, person or "", " ".join(lines)),
                "a": " ".join([hook, *lines[:half]]), "b": " ".join([*lines[half:], cta])}
        try:
            with tempfile.TemporaryDirectory() as tmp:
                ref_urls = [fal.upload(r) for r in refs[:3]]
                prompts = [p.format(**fill) for p in SCENES[fmt]]
                if ref_urls:  # product refs from research: keep the real product's look
                    cite = ", ".join(f"Image {i + 1}" for i in range(len(ref_urls)))
                    prompts = [f"{p} The {brand} product must look exactly like the product in {cite}: same shape, "
                               f"colours, packaging and label." for p in prompts]
                clips = fal.generate(prompts, Path(tmp), seconds=seconds / 2, refs=ref_urls or None)
                base = fal.join(clips, Path(tmp) / "joined.mp4")
                res = templates.make_from_video(base, fmt, hook, lines, cta, out, tag=brand)
            return {**res, "format": fmt, "mode": "fal", "model": fal.REF_MODEL if ref_urls else fal.MODEL,
                    "refs": len(ref_urls)}
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
