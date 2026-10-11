"""Command line for the harness. Progress goes to stderr; stdout gets one JSON line.

Usage:
    uv run --project video vidgen render spec.json --campaign c1     # -> runs/c1/video_vN.mp4 (+ .json .srt .jpg)
    uv run --project video vidgen make brainrot --campaign c1 --script "..." --query "..." [--title "..."]
    uv run --project video vidgen images "elon musk shocked" -n 6 [--license cc]
    uv run --project video vidgen footage fetch subway | footage list
    uv run --project video vidgen tts "hello there" --out hello.mp3
    uv run --project video vidgen voices | credits | formats
    uv run --project video vidgen ad talking-head --campaign c1 --brand B --trend "..." --hook "..." --line "..." --cta "..." --ref person.png
    uv run --project video vidgen template make --campaign c1 --hook "..." --line "..." --line "..." --cta "..."  # demo
    uv run --project video vidgen vizard make --campaign c1 --prompt "..." --ref ref1.png --ref ref2.png  # 20-25s, with sound
    uv run --project video vidgen vizard create --brief "..." --material URL_OR_PATH --aspect 9:16 --duration 30
    uv run --project video vidgen vizard status <project_id> --wait 600 [--download --campaign c1]

Failures print {"ok": false, "error": ...} and exit 1. Secrets (ElevenLabs) are resolved
by the tool itself from env, video/.env or the macOS Keychain; never pass them as flags.
"""

import argparse
import json
import sys
from pathlib import Path

import httpx

from . import ads, footage, images, templates, vizard
from .config import VidgenError, runs_dir
from .render import FORMATS, estimate_chars, next_version, render
from .tts import ElevenLabs


def emit(obj: dict) -> None:
    print(json.dumps(obj, ensure_ascii=False))


def _out_path(args) -> Path:
    if args.out:
        return Path(args.out).expanduser().resolve()
    return next_version(runs_dir() / args.campaign)


def _add_out(p: argparse.ArgumentParser) -> None:
    out = p.add_mutually_exclusive_group(required=True)
    out.add_argument("--campaign", help="campaign id; writes runs/<campaign>/video_vN.mp4 (next free N)")
    out.add_argument("--out", help="write the mp4 here instead")
    p.add_argument("--dry-run", action="store_true", help="validate the spec and report the TTS character cost")


def _summary(meta: dict) -> dict:
    return {"ok": True, "path": meta["path"], "format": meta["format"], "duration": meta["duration"],
            "captions": meta["captions"], "thumbnail": meta["thumbnail"], "meta": meta["path"][:-4] + ".json",
            "tts_chars": meta["tts_chars"], "tts_cached": meta["tts_cached"],
            "render_seconds": meta["render_seconds"]}


def main() -> int:
    parser = argparse.ArgumentParser(prog="vidgen", description="Short-form video generation for the GTM harness.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    r = sub.add_parser("render", help="render a JSON spec (file path, or - for stdin)")
    r.add_argument("spec")
    _add_out(r)

    m = sub.add_parser("make", help="render straight from flags; the script is split into one beat per sentence")
    m.add_argument("format", choices=sorted(FORMATS))
    m.add_argument("--script", required=True, help="narration text")
    m.add_argument("--title", help="hook / post title (read aloud first for story and listicle)")
    m.add_argument("--query", help="image search used for every beat (default: the beat's own text)")
    m.add_argument("--gameplay", default="minecraft", help=f"preset ({', '.join(footage.PRESETS)}) or a video path")
    m.add_argument("--voice", help="ElevenLabs voice name or id (default: miles)")
    m.add_argument("--speed", type=float, help="0.7-1.2")
    m.add_argument("--music", help="audio path, URL, or a YouTube search")
    m.add_argument("--license", default="any", choices=sorted(images.LICENSES))
    _add_out(m)

    i = sub.add_parser("images", help="search Bing (Openverse fallback) and download images")
    i.add_argument("query")
    i.add_argument("-n", type=int, default=6)
    i.add_argument("--license", default="any", choices=sorted(images.LICENSES),
                   help="any = no filter; cc = Creative Commons; commercial = free to use commercially")
    i.add_argument("--refresh", action="store_true", help="ignore the cache and search again")

    f = sub.add_parser("footage", help="background gameplay clips")
    fsub = f.add_subparsers(dest="action", required=True)
    fsub.add_parser("list")
    ff = fsub.add_parser("fetch")
    ff.add_argument("name", help=f"preset ({', '.join(footage.PRESETS)}) or a new name")
    ff.add_argument("--query", help="YouTube search to use instead of the preset's")
    ff.add_argument("--url", help="exact video URL")
    ff.add_argument("--start", type=int, default=60)
    ff.add_argument("--length", type=int, default=180)

    t = sub.add_parser("tts", help="ElevenLabs voiceover with word timings")
    t.add_argument("text")
    t.add_argument("--voice")
    t.add_argument("--speed", type=float, default=1.0)
    t.add_argument("--out", help="copy the mp3 here")

    sub.add_parser("voices", help="ElevenLabs voices on the account")
    sub.add_parser("credits", help="ElevenLabs characters left this cycle")
    sub.add_parser("formats", help="video formats and what they look like")

    ad = sub.add_parser("ad", help="B2C short (22s): talking-head, product or brainrot, from ref images")
    ad.add_argument("format", choices=sorted(ads.FORMATS))
    ad.add_argument("--brand", required=True)
    ad.add_argument("--trend", required=True, help="the trend this rides, from the analysis")
    ad.add_argument("--hook", required=True, help="first 3 seconds, <= 8 words")
    ad.add_argument("--line", action="append", default=[], help="script line, <= 7 words; repeatable (3-5)")
    ad.add_argument("--cta", required=True)
    ad.add_argument("--ref", action="append", default=[],
                    help="reference image (person for talking-head, product shot...) from your image generation")
    ad.add_argument("--person", help="no --ref? describe the on-camera person; Codex generates the image")
    ad.add_argument("--product", help="no --ref? describe the product shot; Codex generates the image")
    ad.add_argument("--mode", choices=["demo", "vizard"], default="demo",
                    help="demo: instant captioned clip; vizard: animated + voiced (slow, credits), demo on failure")
    ad.add_argument("--wait", type=int, default=900, help="vizard mode: seconds before falling back to demo")
    ad_out = ad.add_mutually_exclusive_group(required=True)
    ad_out.add_argument("--campaign", help="campaign id; writes runs/<campaign>/video_vN.mp4 (next free N)")
    ad_out.add_argument("--out", help="write the mp4 here instead")

    tp = sub.add_parser("template", help="demo: caption one of five pre-rendered 22s clips (no generation)")
    tsub = tp.add_subparsers(dest="action", required=True)
    tsub.add_parser("list", help="the five templates and whether they're built")
    tb = tsub.add_parser("build", help="render the base clips into video/templates/ (one-time, host)")
    tb.add_argument("--force", action="store_true")
    tm = tsub.add_parser("make", help="burn hook + caption lines + CTA onto a template")
    tm.add_argument("--template", default="auto", help=f"auto (stable pick from the text) or one of "
                    f"{', '.join(templates.TEMPLATES)}")
    tm.add_argument("--hook", required=True, help="first 3 seconds, punchy (<= 8 words)")
    tm.add_argument("--line", action="append", default=[], help="caption line, <= 7 words; repeatable (3-5 is best)")
    tm.add_argument("--cta", default="Try it free", help="last 3.5 seconds")
    tm_out = tm.add_mutually_exclusive_group(required=True)
    tm_out.add_argument("--campaign", help="campaign id; writes runs/<campaign>/video_vN.mp4 (next free N)")
    tm_out.add_argument("--out", help="write the mp4 here instead")

    v = sub.add_parser("vizard", help="Vizard Agent, an AI video editor (optional; uses Vizard credits)")
    vsub = v.add_subparsers(dest="action", required=True)
    vl = vsub.add_parser("login", help="one-time OAuth sign-in; saves video/.vizard/session.json")
    vl.add_argument("--no-browser", action="store_true", help="only print the sign-in URL")
    vsub.add_parser("account", help="plan, credits left, top-up URL")
    vp = vsub.add_parser("projects", help="recent projects")
    vp.add_argument("--limit", type=int, default=10)
    vc = vsub.add_parser("create", help="start a project (returns at once with the project id)")
    vc.add_argument("--brief", required=True, help="goal, audience, platform, style, brand rules, what each material is")
    vc.add_argument("--material", action="append", default=[], help="URL or local file (uploaded); repeatable")
    vc.add_argument("--aspect", default="9:16")
    vc.add_argument("--duration", type=int, help="target length in seconds")
    vc.add_argument("--tier", choices=["flash", "pro", "max", "ultra"], help="default: the plan's default tier")
    vs = vsub.add_parser("status", help="project state; --wait blocks until a question, delivery or failure")
    vs.add_argument("project_id", type=int)
    vs.add_argument("--wait", type=int, default=0, help="seconds to wait")
    vs.add_argument("--download", action="store_true", help="on delivery, save the videos to runs/<campaign>/")
    vs.add_argument("--campaign")
    vk = vsub.add_parser("make", help="reference images + prompt -> finished 20-25s video with sound (blocks)")
    vk.add_argument("--prompt", required=True, help="what the video says and shows: hook, message, CTA, style")
    vk.add_argument("--ref", action="append", default=[],
                    help="reference image path or URL (e.g. from your image generation); repeatable")
    vk.add_argument("--seconds", type=int, default=22, help=f"target length, clamped to "
                    f"{vizard.MIN_SECONDS}-{vizard.MAX_SECONDS}")
    vk.add_argument("--aspect", default="9:16")
    vk.add_argument("--tier", choices=["flash", "pro", "max", "ultra"], help="default: the plan's default tier")
    vk.add_argument("--wait", type=int, default=900, help="seconds to wait for delivery")
    vk_out = vk.add_mutually_exclusive_group(required=True)
    vk_out.add_argument("--campaign", help="campaign id; writes runs/<campaign>/video_vN.mp4 (next free N)")
    vk_out.add_argument("--out", help="write the mp4 here instead")
    vm = vsub.add_parser("send", help="answer the editor's question, or request a revision")
    vm.add_argument("project_id", type=int)
    vm.add_argument("--message", required=True)
    vm.add_argument("--answer", action="append", help="one per part of a multi-part question, in order")
    vm.add_argument("--material", action="append", default=[])

    args = parser.parse_args()
    try:
        if args.cmd in ("render", "make"):
            if args.cmd == "render":
                raw = sys.stdin.read() if args.spec == "-" else Path(args.spec).read_text()
                spec = json.loads(raw)
            else:
                spec = {"format": args.format, "script": args.script, "gameplay": args.gameplay,
                        "license": args.license}
                for k in ("title", "query", "voice", "speed", "music"):
                    if getattr(args, k) is not None:
                        spec[k] = getattr(args, k)
            if args.dry_run:
                emit({"ok": True, "dry_run": True, "format": spec.get("format", "brainrot"),
                      "tts_chars": estimate_chars(spec)})
                return 0
            emit(_summary(render(spec, _out_path(args))))
        elif args.cmd == "images":
            found = images.acquire(args.query, n=args.n, license=args.license, refresh=args.refresh)
            emit({"ok": True, "query": args.query, "count": len(found),
                  "images": [{k: x[k] for k in ("path", "url", "page", "width", "height", "engine")} for x in found]})
        elif args.cmd == "footage":
            if args.action == "list":
                emit({"ok": True, "cached": footage.cached(), "presets": footage.PRESETS})
            else:
                path = footage.fetch(args.name, query=args.query, url=args.url, start=args.start, length=args.length)
                emit({"ok": True, "name": path.stem, "path": str(path)})
        elif args.cmd == "tts":
            sp = ElevenLabs().speak(args.text, voice=args.voice, speed=args.speed)
            path = sp.audio
            if args.out:
                path = Path(args.out).expanduser()
                path.write_bytes(sp.audio.read_bytes())
            emit({"ok": True, "path": str(path), "duration": sp.duration, "words": len(sp.words),
                  "chars": sp.chars, "cached": sp.cached})
        elif args.cmd == "voices":
            emit({"ok": True, "voices": ElevenLabs().voices()})
        elif args.cmd == "credits":
            emit({"ok": True, **ElevenLabs().credits()})
        elif args.cmd == "ad":
            emit(ads.make(args.format, args.brand, args.trend, args.hook, args.line, args.cta, args.ref,
                          _out_path(args), mode=args.mode, wait=args.wait, person=args.person,
                          product=args.product))
        elif args.cmd == "template":
            if args.action == "list":
                emit({"ok": True, "seconds": templates.SECONDS, "templates": templates.available()})
            elif args.action == "build":
                emit({"ok": True, "built": templates.build(force=args.force)})
            else:
                emit(templates.make(args.template, args.hook, args.line, args.cta, _out_path(args)))
        elif args.cmd == "vizard":
            if args.action == "login":
                emit({"ok": True, **vizard.login(open_browser=not args.no_browser)})
            elif args.action == "account":
                emit({"ok": True, **vizard.call("get_account", {})})
            elif args.action == "projects":
                emit({"ok": True, **vizard.call("list_projects", {"limit": args.limit})})
            elif args.action == "create":
                body = {"brief": args.brief, "aspect_ratio": args.aspect}
                if args.material:
                    body["materials"] = vizard.materials(args.material)
                if args.duration:
                    body["target_duration_seconds"] = args.duration
                if args.tier:
                    body["tier"] = args.tier
                emit({"ok": True, **vizard.call("create_video_project", body)})
            elif args.action == "status":
                st = vizard.call("get_project_status", {"project_id": args.project_id, "wait_seconds": args.wait},
                                 timeout=args.wait + 120)
                if args.download and st.get("state") == "delivered":
                    if not args.campaign:
                        raise VidgenError("--download needs --campaign")
                    st["saved"] = vizard.download(st, runs_dir() / args.campaign, f"vizard_{args.project_id}")
                emit({"ok": True, **st})
            elif args.action == "make":
                result = vizard.make(args.prompt, args.ref, _out_path(args), seconds=args.seconds,
                                     aspect=args.aspect, tier=args.tier, wait=args.wait)
                emit(result)
                return 0 if result["ok"] else 1
            elif args.action == "send":
                body = {"project_id": args.project_id, "message": args.message}
                if args.answer:
                    body["answers"] = args.answer
                if args.material:
                    body["materials"] = vizard.materials(args.material)
                emit({"ok": True, **vizard.call("send_to_project", body)})
        elif args.cmd == "formats":
            emit({"ok": True, "formats": FORMATS, "gameplay_presets": sorted(footage.PRESETS)})
    except (VidgenError, OSError, ValueError, KeyError, httpx.HTTPError) as e:
        emit({"ok": False, "error": f"{type(e).__name__}: {e}" if not isinstance(e, VidgenError) else str(e)})
        return 1
    return 0
