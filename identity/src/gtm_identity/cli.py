"""Product identity + PMF tools for the harness. Progress goes to stderr; stdout gets one JSON line.

    identity collect   --campaign C --brand https://www.tinyfish.ai/     # evidence.json + screenshots + draft board
    identity schema    --kind identity|pmf                               # the JSON schema the agent must write
    identity validate  --campaign C --kind identity|pmf                  # check the agent's file
    identity moodboard --campaign C                                       # moodboard.png (uses identity.json if valid)
    identity market    --campaign C [--niche "AI browser agents" ...]     # market.json (niches from identity.json)

Everything goes to runs/<campaign>/identity/. GTM_RUNS_DIR moves runs/.
"""

import argparse
import json
import os
import sys
import traceback
from pathlib import Path

from dotenv import load_dotenv

from . import collect as collect_mod
from . import market as market_mod
from . import moodboard, schema

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # identity/
PROJECT_ROOT = PACKAGE_ROOT.parent  # /workspace inside the harness container


def folder(campaign: str) -> Path:
    return Path(os.environ.get("GTM_RUNS_DIR", PROJECT_ROOT / "runs")) / campaign / "identity"


def read(path: Path) -> dict | None:
    return json.loads(path.read_text()) if path.exists() else None


def main() -> int:
    p = argparse.ArgumentParser(prog="identity", description="Product identity + PMF tools for the GTM harness.")
    sub = p.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("collect", help="read the brand's site: copy, rendered type and colors, screenshots")
    c.add_argument("--campaign", required=True)
    c.add_argument("--brand", required=True, help="brand homepage URL")
    c.add_argument("--max-pages", type=int, default=6, help="subpages to read (pricing, product, customers, ...)")
    c.add_argument("--no-browser", action="store_true", help="skip screenshots and rendered styles (Fetch only, free)")
    s = sub.add_parser("schema", help="print the JSON schema for identity.json or pmf.json")
    s.add_argument("--kind", choices=sorted(schema.MODELS), required=True)
    v = sub.add_parser("validate", help="check identity.json or pmf.json")
    v.add_argument("--campaign", required=True)
    v.add_argument("--kind", choices=sorted(schema.MODELS), required=True)
    m = sub.add_parser("moodboard", help="render moodboard.png")
    m.add_argument("--campaign", required=True)
    k = sub.add_parser("market", help="search each niche for trends, community talk, pains, competitors, short videos")
    k.add_argument("--campaign", required=True)
    k.add_argument("--niche", action="append", help="niche to scan (repeatable); default: niches in identity.json")
    k.add_argument("--days", type=int, default=30, help="recency window")
    k.add_argument("--read", type=int, default=3, help="community threads to read per niche (Fetch, free)")
    args = p.parse_args()
    load_dotenv(PACKAGE_ROOT / ".env")

    if args.cmd == "schema":
        print(json.dumps(schema.MODELS[args.kind].model_json_schema()))
        return 0

    out = folder(args.campaign)
    try:
        if args.cmd == "collect":
            ev = collect_mod.collect(args.brand, out, max_pages=args.max_pages, browser=not args.no_browser)
            (out / "evidence.json").write_text(json.dumps(ev, indent=2, ensure_ascii=False))
            board = moodboard.render(ev, None, out, out / "moodboard_draft.png")
            result = {"evidence": str(out / "evidence.json"), "draft_moodboard": str(board),
                      "pages": len(ev["pages"]), "screenshots": len(ev["screenshots"]), "fonts": ev["fonts"],
                      "palette": [c["hex"] for c in ev["palette"]], "errors": len(ev["errors"]),
                      "next": f"write {out / 'identity.json'} (see `identity schema --kind identity`)"}

        elif args.cmd == "validate":
            problems = schema.validate(args.kind, out / f"{args.kind}.json")
            print(json.dumps({"ok": not problems, "file": str(out / f"{args.kind}.json"), "problems": problems}))
            return 1 if problems else 0

        elif args.cmd == "moodboard":
            ev = read(out / "evidence.json")
            if ev is None:
                raise RuntimeError(f"run `identity collect --campaign {args.campaign}` first")
            ident = read(out / "identity.json")
            if ident is not None and schema.validate("identity", out / "identity.json"):
                raise RuntimeError("identity.json is invalid; run `identity validate --kind identity`")
            board = moodboard.render(ev, ident, out, out / ("moodboard.png" if ident else "moodboard_draft.png"))
            result = {"moodboard": str(board), "final": ident is not None}

        elif args.cmd == "market":
            ident = read(out / "identity.json") or {}
            niches = [{"name": n, "search_terms": [n]} for n in args.niche] if args.niche else ident.get("niches")
            if not niches:
                raise RuntimeError("pass --niche, or write identity.json with niches first")
            report = market_mod.scan(niches, out, category=ident.get("category"), days=args.days, read=args.read)
            (out / "market.json").write_text(json.dumps(report, indent=2, ensure_ascii=False))
            result = {"market": str(out / "market.json"),
                      "niches": {n["name"]: n["signals"] for n in report["niches"]},
                      "next": f"write {out / 'pmf.json'} (see `identity schema --kind pmf`)"}
    except Exception as e:
        traceback.print_exc(file=sys.stderr)
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        return 1

    print(json.dumps({"ok": True, **result}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
