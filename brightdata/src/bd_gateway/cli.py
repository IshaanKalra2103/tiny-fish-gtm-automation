"""Command line for the harness. Progress goes to stderr; stdout gets one JSON line.

Usage:
    uv run bd-gateway sample --campaign c1 --platform tiktok --keyword "AI agents"
    uv run bd-gateway sample --campaign c1 --platform tiktok --hashtag aitools
    uv run bd-gateway sample --campaign c1 --platform instagram --from-url https://www.instagram.com/<competitor>/
    uv run bd-gateway sample --campaign c1 --platform instagram --urls-file runs/c1/search_urls.txt
    uv run bd-gateway status <snapshot_id>
    uv run bd-gateway platforms

`sample` writes runs/<campaign>/social_<platform>.json, the shared-memory path the
Paperclip agents read. Set GTM_RUNS_DIR to put runs somewhere else.
"""

import argparse
import json
import os
import sys
from pathlib import Path

from dotenv import load_dotenv

from .gateway import PLATFORMS, BrightDataError, BrightDataGateway

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # brightdata/
PROJECT_ROOT = PACKAGE_ROOT.parent  # /workspace inside the harness container


def main() -> int:
    parser = argparse.ArgumentParser(prog="bd-gateway", description="Bright Data social samples for the GTM harness.")
    sub = parser.add_subparsers(dest="cmd", required=True)

    a = sub.add_parser("sample", aliases=["audience"], help="collect posts + top comments for analysis and persona QA")
    a.add_argument("--platform", default="tiktok", choices=sorted(PLATFORMS))
    find = a.add_mutually_exclusive_group(required=True)
    find.add_argument("--keyword", help="search the platform (not Instagram)")
    find.add_argument("--hashtag", help="search by hashtag (TikTok, YouTube)")
    find.add_argument("--from-url", help="recent posts from a profile, channel or subreddit URL")
    find.add_argument("--url", action="append", dest="urls", help="specific post URLs (repeatable)")
    find.add_argument("--urls-file", type=Path, help="file with one URL per line, e.g. TinyFish Search results; "
                                                     "URLs from other sites are skipped")
    a.add_argument("--posts", type=int, default=10, help="posts to collect")
    a.add_argument("--top", type=int, default=5, help="read comments under this many top posts (0 = none)")
    a.add_argument("--comments-per-post", type=int, default=20)
    out = a.add_mutually_exclusive_group(required=True)
    out.add_argument("--campaign", help="campaign id; output goes to runs/<campaign>/social_<platform>.json")
    out.add_argument("--out", type=Path, help="write the sample here instead")

    s = sub.add_parser("status", help="progress of an async snapshot")
    s.add_argument("snapshot_id")

    sub.add_parser("platforms", help="list supported platforms, dataset ids and search modes")

    args = parser.parse_args()
    load_dotenv(PACKAGE_ROOT / ".env")

    if args.cmd == "platforms":
        for name, p in PLATFORMS.items():
            print(json.dumps({"platform": name, "posts": p.posts_dataset, "comments": p.comments_dataset,
                              "find_by": sorted(p.discover) + ["urls"]}))
        return 0

    try:
        gw = BrightDataGateway()
        if args.cmd == "status":
            print(json.dumps({"snapshot_id": args.snapshot_id, "status": gw.progress(args.snapshot_id)}))
            return 0
        urls = args.urls
        if args.urls_file:
            urls = [line.strip() for line in args.urls_file.read_text().splitlines() if line.strip().startswith("http")]
        sample = gw.sample(args.platform, keyword=args.keyword, hashtag=args.hashtag, from_url=args.from_url,
                           urls=urls, posts=args.posts, comments_per_post=args.comments_per_post,
                           comment_on_top=args.top)
    except (BrightDataError, OSError) as e:
        print(json.dumps({"ok": False, "error": str(e)}))
        return 1

    runs = Path(os.environ.get("GTM_RUNS_DIR", PROJECT_ROOT / "runs"))
    path = args.out or runs / args.campaign / f"social_{args.platform}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(sample, indent=2, ensure_ascii=False))
    stats = {k: sample["stats"][k] for k in ("posts", "comments", "errors", "median_views", "median_engagement_rate")}
    print(json.dumps({"ok": True, "path": str(path), **stats, "seconds": sample["seconds"]}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
