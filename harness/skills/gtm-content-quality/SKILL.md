---
name: gtm-content-quality
description: The creative and QA bar for GTM short videos. B2C trend-driven shorts of 20-25 s; picking talking-head, product ad or brainrot from the trend; precise shot prompts for video models; product reference images; caption and CTA layout that passes persona QA; evidence-backed claims; and what QA scores mean. Use when writing scripts or video prompts, choosing a format, changing vidgen or the video/QA roles, or judging a draft.
---

# Content quality

## What we make

- **Brand:** a B2C company (TinyFish is the default target).
- **Trend:** what's trending in that brand's niche right now, from the analysis.
- **Video:** one vertical 9:16 short, 1080x1920, **20-25 s** (22 s by default).
- **Content:** a hook, 3-5 caption lines and a CTA.

Pick the format from the trend:

| Trend type | Format |
|---|---|
| GRWM, routine, testimonial, "POV" | `talking-head`: a UGC creator holding the product, talking to camera |
| Unboxing, before/after, feature demo | `product`: a studio product ad, no people |
| Meme, story, "brainrot" | `brainrot`: an exaggerated creator reaction, or the ref over parkour |

For speed, demos use `vidgen ad ... --mode demo` or the five captioned templates (`vidgen template make`). Commands are in `video/SKILL.md`.

## Prompts for video models (fal, Vizard)

Write each clip as a precise shot description, never a vibe.

- **Setting that fits the product:** shampoo in a bathroom, coffee in a kitchen, sneakers in a gym. Always state the setting explicitly.
- **The exact action, plus forbidden actions.** For example: "holds the bottle beside their face, label to camera. Nobody opens, pours, squeezes or applies it."
- **Continuity across clips:** the same person, outfit, location and light.
- **Camera and light:** framing, height, movement, light source.
- **No text on screen.** Captions are added afterwards.
- **The person as asked:** age, gender and look from the brief. Write "they" in templates, never a hardcoded "she".

A bad example from a real run: a prompt said the creator "uses" the shampoo and gave no setting. The model had her rubbing shampoo into dry hair in the middle of a living room.

**Product references:** pass the real product image from research (the brand site or a store CDN packshot) with `--ref`. fal then switches to reference-to-video and matches the real packaging.

**Check the frames before calling a video done.** `video_vN.json` lists 8 QA frames. Look at them and confirm the scene makes physical sense.

## Layout that passes persona QA

These fixes come from three drafts that each failed 3 out of 3 personas:

- **Panels:** the person or product sits in its own top panel, and the captions get their own band below it. Captions never cover the product or the face.
- **Hook:** shown 0-3 s, at most 8 words.
- **Caption lines:** 3-5 of them, at most 7 words each.
- **CTA:** a button, shown for the last 3.5 s. The brand tag stays clear of it, even when the CTA wraps to two lines.
- **Product visibility:** the product is visible and readable for at least two seconds.

## Claims

- **Use only what the evidence supports.** Each script claim cites a URL from `evidence.json`.
- **Never invent anything:** no numbers, customers, results or testimonials.
- **Voice and allowed claims** come from `identity.json` when the identity stage ran.

## QA: what the scores mean

- **Personas:** three synthetic personas, grounded in real public comments (Bright Data samples). Their scores are **simulated hypotheses**, never "audience validation". Say so wherever scores appear.
- **Gates:** `GTM_QA_GATE=advisory` (the default) scores and flags every draft but never blocks. The best draft goes to the human approval with its flags. `strict` requires a pass before packaging. In strict mode, exhausted QA ends at `needs_human` and nothing publishes.
- **Revisions:** up to v3, driven by QA feedback. If QA blocks on "product not shown", the revision becomes a product ad and stays one. Re-rendering a talking-head can't fix that blocker.
- **Common blockers:** product not shown, captions covering content, claims not backed on screen, weak hook. Fix the cause in layout or format. Rewording the script alone has never fixed these.
