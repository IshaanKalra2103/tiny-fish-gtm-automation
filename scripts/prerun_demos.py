# /// script
# requires-python = ">=3.12"
# dependencies = ["httpx>=0.27"]
# ///
"""Run the five demo businesses through the live API ahead of time (plan Task 13).

Per slug: create an owner from its demo-site URL, ask what to try first, compare tools for the
top 3 needs, ask for one preview of the best tool for the top need, then write a static demo
bundle into web/data/demo/<slug>.json with its mp4s in web/public/demo-media/<slug>/.

    uv run scripts/prerun_demos.py [--api http://127.0.0.1:8787] [--slugs coffee,hvac] [--force]
                                   [--out web/data/demo] [--media-dir web/public/demo-media]
    uv run scripts/prerun_demos.py --index-only     # just regenerate web/data/demo/index.ts

A slug is skipped when <out>/<slug>.json already exists and was written by this script (it has a
`media` map), unless --force. A bundle that fails validation is written to
<out>/incomplete/<slug>.json instead, so it is not shown on /demo and the slug is retried next run.
Exit status is 1 if any slug misses a check.
"""
from __future__ import annotations

import argparse
import copy
import json
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable, Iterator

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_OUT = ROOT / "web" / "data" / "demo"
DEFAULT_MEDIA = ROOT / "web" / "public" / "demo-media"
URLS_FILE = ROOT / "demo-sites" / "URLS.md"
WEB_CATALOG = ROOT / "web" / "data" / "catalog.json"

# Cards on /demo, in page order. Moved here from the hand-written index.ts, which is now generated.
BUSINESSES = [
    {"slug": "diner", "name": "Route 40 Diner", "place": "Ellicott City, MD", "kind": "Restaurant"},
    {"slug": "coffee", "name": "Bean & Brick Coffee", "place": "Frederick, MD", "kind": "Coffee shop"},
    {"slug": "hvac", "name": "Two Vans Heating & Cooling", "place": "Hagerstown, MD", "kind": "HVAC"},
    {"slug": "landscaping", "name": "Chesapeake Green Landscaping", "place": "Annapolis, MD", "kind": "Landscaping"},
    {"slug": "salon", "name": "Main Street Shears", "place": "Westminster, MD", "kind": "Hair salon"},
]
EXPECTED_TYPE = {"diner": "restaurant", "coffee": "coffee_shop", "hvac": "hvac",
                 "landscaping": "landscaping", "salon": "salon"}
KIND_LABEL = {"restaurant": "Restaurant", "coffee_shop": "Coffee shop", "hvac": "HVAC",
              "landscaping": "Landscaping", "salon": "Hair salon", "other": "Small business"}

SLUG_RE = re.compile(r"^[a-z0-9][a-z0-9-]*$")
LIVE_OWNER_RE = re.compile(r"\bo_[0-9a-f]{10}\b")
# Keys that must never reach a public bundle. has_password is a flag, kept and forced to False.
SECRET_KEY_RE = re.compile(r"(?i)^(password|passwd|pwd|pass|secret|client_secret|api_key|apikey|"
                           r"access_token|refresh_token|auth_token|otp|verification_code)$")
TURN_TIMEOUT = 15 * 60.0
QUEUE_TIMEOUT = 30 * 60.0

_print_lock = threading.Lock()


def say(slug: str, msg: str) -> None:
    with _print_lock:
        print(f"[{datetime.now().strftime('%H:%M:%S')}] {slug:<12} {msg}", flush=True)


# ---------------------------------------------------------------- pure parts (tested)

def parse_urls(text: str) -> dict[str, str]:
    """demo-sites/URLS.md lines like '- coffee: https://...' -> {slug: url}, in file order."""
    return {m.group(1): m.group(2) for m in re.finditer(r"(?m)^- ([a-z0-9-]+): (https?://\S+)\s*$", text)}


def strip_secrets(obj):
    """Copy of obj without any password-like key, at any depth."""
    if isinstance(obj, dict):
        return {k: strip_secrets(v) for k, v in obj.items() if not SECRET_KEY_RE.match(str(k))}
    if isinstance(obj, list):
        return [strip_secrets(v) for v in obj]
    return obj


def secret_paths(obj, path: str = "") -> list[str]:
    if isinstance(obj, dict):
        out = [f"{path}.{k}" for k in obj if SECRET_KEY_RE.match(str(k))]
        for k, v in obj.items():
            out += secret_paths(v, f"{path}.{k}")
        return out
    if isinstance(obj, list):
        return [p for i, v in enumerate(obj) for p in secret_paths(v, f"{path}[{i}]")]
    return []


def demo_media_path(slug: str, tool_id: str) -> str:
    return f"/demo-media/{slug}/{tool_id}.mp4"


def to_demo_bundle(bundle: dict, slug: str) -> tuple[dict, dict[str, str]]:
    """API owner bundle -> (static demo bundle, {tool_id: API video path to download}).

    owner_id becomes demo-<slug> everywhere (also inside agent replies that quote the live page link),
    previews point at /demo-media/<slug>/<tool_id>.mp4, previews without a video are dropped,
    `media` maps tool_id to that path, and password-like keys are removed.
    """
    b = strip_secrets(copy.deepcopy(bundle))
    live_id = b.get("owner_id") or ""
    b.pop("active_turn", None)
    downloads: dict[str, str] = {}
    previews: dict[str, dict] = {}
    for tool_id, pv in (b.get("previews") or {}).items():
        url = pv.get("video_url")
        if pv.get("status") != "completed" or not url:
            continue
        downloads[tool_id] = url
        previews[tool_id] = {**pv, "video_file": f"{tool_id}.mp4", "video_url": demo_media_path(slug, tool_id)}
    b["previews"] = previews
    b["media"] = {t: demo_media_path(slug, t) for t in previews}
    for s in (b.get("setups") or {}).values():
        if isinstance(s, dict):
            s["has_password"] = False
    demo_id = f"demo-{slug}"
    if live_id:
        b = json.loads(json.dumps(b).replace(live_id, demo_id))
    b["owner_id"] = demo_id
    return b, downloads


def drop_media(bundle: dict, tool_ids: Iterable[str]) -> dict:
    """Remove previews whose mp4 could not be downloaded."""
    gone = set(tool_ids)
    b = copy.deepcopy(bundle)
    b["previews"] = {t: p for t, p in (b.get("previews") or {}).items() if t not in gone}
    b["media"] = {t: p for t, p in (b.get("media") or {}).items() if t not in gone}
    return b


def top_needs(bundle: dict, n: int = 3) -> list[dict]:
    """The agent saves needs most important first; take its order as the ranking."""
    return list(((bundle.get("needs") or {}).get("items") or [])[:n])


def validate(bundle: dict, slug: str) -> list[str]:
    """Checks from plan Task 13 Step 2. Returns the misses; empty means the bundle is good."""
    misses: list[str] = []
    prof = bundle.get("profile") or {}
    btype = prof.get("business_type")
    if not btype:
        misses.append("no profile with a business type")
    elif slug in EXPECTED_TYPE and btype != EXPECTED_TYPE[slug]:
        misses.append(f"profile type is {btype}, expected {EXPECTED_TYPE[slug]}")
    items = (bundle.get("needs") or {}).get("items") or []
    if not 3 <= len(items) <= 5:
        misses.append(f"{len(items)} needs, want 3-5")
    compares = bundle.get("compares") or {}
    top = [n.get("need_id") for n in items[:3]]
    lacking = [nid for nid in top if not (compares.get(nid) or {}).get("options")]
    if lacking:
        misses.append("no compare for " + ", ".join(map(str, lacking)))
    elif len(top) < 3:
        misses.append(f"compares for {len(top)} of 3 top needs")
    media = bundle.get("media") or {}
    done = [t for t, p in (bundle.get("previews") or {}).items()
            if p.get("status") == "completed" and media.get(t) and p.get("video_url") == media[t]]
    if not done:
        misses.append("no completed preview with a video")
    if (paths := secret_paths(bundle)):
        misses.append("password-like key at " + ", ".join(paths))
    if bundle.get("owner_id") != f"demo-{slug}":
        misses.append(f"owner_id is {bundle.get('owner_id')}")
    if LIVE_OWNER_RE.search(json.dumps(bundle)):
        misses.append("live owner id left in bundle")
    return misses


def catalog_ids(path: Path) -> set[str] | None:
    """Tool ids in the web app's catalog.json, or None if it cannot be read."""
    try:
        return {t["id"] for t in json.loads(Path(path).read_text()).get("tools") or [] if t.get("id")}
    except (OSError, ValueError, AttributeError, KeyError, TypeError):
        return None


def unknown_tools(bundle: dict, ids: set[str] | None) -> list[str]:
    """Tool ids the bundle shows that the web catalog lacks. The web page renders those as nothing."""
    if ids is None:
        return []
    used = {o.get("tool_id") for c in (bundle.get("compares") or {}).values() for o in c.get("options") or []}
    used |= set((bundle.get("previews") or {}).keys())
    return sorted(t for t in used if t and t not in ids)


def is_generated(path: Path) -> bool:
    try:
        return isinstance(json.loads(path.read_text()).get("media"), dict)
    except (OSError, ValueError, AttributeError):
        return False


def should_skip(out_dir: Path, slug: str, force: bool) -> bool:
    """Skip a slug that already has a bundle from this script. A hand-made placeholder is replaced."""
    return not force and is_generated(Path(out_dir) / f"{slug}.json")


def sse_events(lines: Iterable[str]) -> Iterator[dict]:
    """`data: <json>` lines -> events. Comments (`: ping`) and blank lines are skipped."""
    for line in lines:
        if line.startswith("data:"):
            payload = line[5:].strip()
            if payload:
                try:
                    yield json.loads(payload)
                except ValueError:
                    continue


def _ident(slug: str) -> str:
    name = re.sub(r"[^A-Za-z0-9_]", "_", slug)
    return name if re.match(r"[A-Za-z_]", name) else f"_{name}"


def present_bundles(out_dir: Path) -> dict[str, dict]:
    """{slug: bundle} for every <slug>.json in out_dir, known slugs first in page order."""
    found: dict[str, dict] = {}
    for f in sorted(Path(out_dir).glob("*.json")):
        if SLUG_RE.match(f.stem):
            try:
                found[f.stem] = json.loads(f.read_text())
            except ValueError:
                continue
    order = [b["slug"] for b in BUSINESSES]
    return dict(sorted(found.items(), key=lambda kv: (order.index(kv[0]) if kv[0] in order else len(order), kv[0])))


def render_index(out_dir: Path) -> str:
    bundles = present_bundles(out_dir)
    cards = list(BUSINESSES)
    known = {b["slug"] for b in BUSINESSES}
    for slug, b in bundles.items():
        if slug not in known:
            p = b.get("profile") or {}
            place = ", ".join(x for x in (p.get("city"), p.get("state")) if x)
            cards.append({"slug": slug, "name": p.get("name") or slug, "place": place,
                          "kind": KIND_LABEL.get(p.get("business_type") or "other", "Small business")})
    imports = "\n".join(f'import {_ident(s)} from "./{s}.json";' for s in bundles)
    entries = "\n".join(
        f"  {s if _ident(s) == s else json.dumps(s)}: {_ident(s)} as unknown as OwnerBundle," for s in bundles)
    card_lines = "\n".join(
        "  { " + ", ".join(f"{k}: {json.dumps(c[k], ensure_ascii=False)}" for k in ("slug", "name", "place", "kind")) + " },"
        for c in cards)
    return (
        "// Generated by scripts/prerun_demos.py. Do not edit by hand:\n"
        "// add or replace <slug>.json here, then run `uv run scripts/prerun_demos.py --index-only`.\n"
        'import type { OwnerBundle } from "@/lib/types";\n'
        + (imports + "\n" if imports else "")
        + "\n"
        "export const demoBundles: Record<string, OwnerBundle> = {\n"
        + (entries + "\n" if entries else "")
        + "};\n\n"
        "export const DEMO_BUSINESSES: { slug: string; name: string; place: string; kind: string }[] = [\n"
        + card_lines + "\n"
        "];\n"
    )


def write_index(out_dir: Path) -> Path:
    p = Path(out_dir) / "index.ts"
    p.write_text(render_index(out_dir))
    return p


# ---------------------------------------------------------------- talking to the API

class Api:
    def __init__(self, base: str):
        import httpx

        self.base = base.rstrip("/")
        self.http = httpx.Client(base_url=self.base, timeout=httpx.Timeout(30.0))
        self.httpx = httpx

    def create_owner(self, source: str) -> str:
        r = self.http.post("/api/owners", json={"source": source})
        r.raise_for_status()
        return r.json()["owner_id"]

    def start_turn(self, owner_id: str, text: str) -> str:
        r = self.http.post(f"/api/owners/{owner_id}/turns", json={"text": text, "channel": "web"})
        r.raise_for_status()
        return r.json()["turn_id"]

    def bundle(self, owner_id: str) -> dict:
        r = self.http.get(f"/api/owners/{owner_id}")
        r.raise_for_status()
        return r.json()

    def wait_turn(self, turn_id: str, slug: str, timeout: float = TURN_TIMEOUT) -> dict:
        """Follow the SSE stream to the terminal event. The clock starts once the turn leaves the queue.
        The server replays every event on reconnect, so a dropped stream is simply reopened."""
        submitted, started = time.monotonic(), None
        last_status = ""
        while True:
            try:
                # read timeout > the 15 s heartbeat, so a silent server is noticed
                with self.http.stream("GET", f"/api/turns/{turn_id}/events",
                                      timeout=self.httpx.Timeout(30.0, read=60.0)) as r:
                    r.raise_for_status()
                    for ev in sse_events(r.iter_lines()):
                        t = ev.get("type")
                        if t != "queued" and started is None:
                            started = time.monotonic()
                        if t in ("done", "error"):
                            return ev
                        if t == "status" and ev.get("text") != last_status:
                            last_status = ev.get("text", "")
                            say(slug, f"  .. {last_status}")
                        if t == "queued":
                            say(slug, f"  .. queued, position {ev.get('position')}")
                        if self._late(submitted, started, timeout):
                            break
            except (self.httpx.HTTPError, OSError) as e:
                if isinstance(e, self.httpx.HTTPStatusError) and e.response.status_code == 404:
                    return {"type": "error", "message": "turn not found"}
                say(slug, f"  .. stream dropped ({type(e).__name__}), reconnecting")
                time.sleep(2)
            if self._late(submitted, started, timeout):
                where = "running" if started else "queued"
                return {"type": "error", "message": f"timed out after {timeout / 60:.0f} min ({where})"}

    @staticmethod
    def _late(submitted: float, started: float | None, timeout: float) -> bool:
        now = time.monotonic()
        return (now - started > timeout) if started else (now - submitted > QUEUE_TIMEOUT)

    def download(self, path: str, dest: Path) -> int:
        dest.parent.mkdir(parents=True, exist_ok=True)
        tmp = dest.with_suffix(".part")
        with self.http.stream("GET", path, timeout=self.httpx.Timeout(30.0, read=120.0)) as r:
            r.raise_for_status()
            with open(tmp, "wb") as fh:
                for chunk in r.iter_bytes():
                    fh.write(chunk)
        size = tmp.stat().st_size
        if size == 0:
            tmp.unlink()
            raise ValueError("empty file")
        tmp.replace(dest)
        return size


def run_turn(api: Api, slug: str, owner_id: str, text: str, timeout: float) -> dict:
    say(slug, f"turn: {text}")
    t0 = time.monotonic()
    try:
        tid = api.start_turn(owner_id, text)
    except api.httpx.HTTPStatusError as e:
        detail = e.response.text[:200]
        say(slug, f"  !! could not start turn: HTTP {e.response.status_code} {detail}")
        return {"type": "error", "message": f"HTTP {e.response.status_code}"}
    ev = api.wait_turn(tid, slug, timeout)
    took = time.monotonic() - t0
    if ev.get("type") == "done":
        reply = (ev.get("reply") or "").strip().replace("\n", " ")
        say(slug, f"  ok in {took:.0f}s: {reply[:120]}")
    else:
        say(slug, f"  !! {ev.get('message')} after {took:.0f}s")
    return ev


def run_slug(api: Api, slug: str, url: str, out_dir: Path, media_dir: Path, timeout: float,
             ids: set[str] | None = None) -> dict:
    """Returns a summary row. Never raises."""
    row = {"slug": slug, "status": "", "owner": "", "misses": [], "unknown": []}
    try:
        owner_id = api.create_owner(url)
        row["owner"] = owner_id
        say(slug, f"owner {owner_id} for {url}")
        turn_errors = []
        ev = run_turn(api, slug, owner_id, f"Here is my business: {url}. What should I try first?", timeout)
        if ev.get("type") != "done":
            turn_errors.append("first turn failed")
        needs = top_needs(api.bundle(owner_id))
        if not needs:
            say(slug, "  !! no needs saved, skipping compare and preview turns")
        for need in needs:
            ev = run_turn(api, slug, owner_id, f"Compare tools for {need.get('title') or need.get('need_id')}", timeout)
            if ev.get("type") != "done":
                turn_errors.append(f"compare turn for {need.get('need_id')} failed")
        if needs:
            top = needs[0].get("title") or needs[0].get("need_id")
            ev = run_turn(api, slug, owner_id, f"Show me a preview of the best tool for {top}", timeout)
            if ev.get("type") != "done":
                turn_errors.append("preview turn failed")
        bundle, downloads = to_demo_bundle(api.bundle(owner_id), slug)
        failed = []
        for tool_id, path in downloads.items():
            dest = Path(media_dir) / slug / f"{tool_id}.mp4"
            try:
                size = api.download(path, dest)
                say(slug, f"  saved {dest} ({size / 1e6:.1f} MB)")
            except Exception as e:  # noqa: BLE001 - report and drop that preview
                say(slug, f"  !! could not download {tool_id}: {type(e).__name__}")
                failed.append(tool_id)
        bundle = drop_media(bundle, failed)
        misses = validate(bundle, slug)
        row["misses"] = misses + [m for m in turn_errors if m not in misses]
        row.update(_counts(bundle))
        row["unknown"] = unknown_tools(bundle, ids)
        if misses:
            dest = Path(out_dir) / "incomplete" / f"{slug}.json"
            row["status"] = "incomplete"
        else:
            dest = Path(out_dir) / f"{slug}.json"
            row["status"] = "written"
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(json.dumps(bundle, indent=1, ensure_ascii=False) + "\n")
        say(slug, f"{row['status']}: {dest}")
    except Exception as e:  # noqa: BLE001 - one bad slug must not stop the others
        row["status"] = "crashed"
        row["misses"].append(f"{type(e).__name__}: {str(e)[:200]}")
        say(slug, f"!! {type(e).__name__}: {str(e)[:200]}")
    return row


def _counts(bundle: dict) -> dict:
    items = (bundle.get("needs") or {}).get("items") or []
    top = [n.get("need_id") for n in items[:3]]
    compares = bundle.get("compares") or {}
    previews = bundle.get("previews") or {}
    return {
        "type": (bundle.get("profile") or {}).get("business_type") or "-",
        "needs": len(items),
        "compares": f"{sum(1 for n in top if (compares.get(n) or {}).get('options'))}/3",
        "previews": sum(1 for p in previews.values() if p.get("status") == "completed"),
        "usd": sum(float(p.get("cost_usd") or 0) for p in previews.values()),
    }


def print_table(rows: list[dict]) -> None:
    cols = [("slug", 12), ("status", 11), ("type", 12), ("needs", 5), ("compares", 8), ("previews", 8), ("usd", 6)]
    print()
    print("  ".join(f"{c:<{w}}" for c, w in cols) + "  misses")
    print("  ".join("-" * w for _, w in cols) + "  ------")
    for r in rows:
        cells = []
        for c, w in cols:
            v = r.get(c, "-")
            v = f"{v:.2f}" if c == "usd" and isinstance(v, float) else v
            cells.append(f"{str(v):<{w}}")
        print("  ".join(cells) + "  " + ("; ".join(r["misses"]) or "none"))
    warn = [f"  {r['slug']}: {', '.join(r['unknown'])}" for r in rows if r.get("unknown")]
    if warn:
        print("\nWarning: tool ids not in web/data/catalog.json (their cards will not show on the page):")
        print("\n".join(warn))
    owners = [f"{r['slug']}={r['owner']}" for r in rows if r.get("owner")]
    if owners:
        print("\nLive owners (open /b/<id> against the local API to inspect): " + ", ".join(owners))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    ap.add_argument("--api", default="http://127.0.0.1:8787")
    ap.add_argument("--slugs", default="", help="comma list, default all in demo-sites/URLS.md")
    ap.add_argument("--force", action="store_true", help="re-run slugs that already have a bundle")
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="bundle dir (index.ts is written here)")
    ap.add_argument("--media-dir", type=Path, default=DEFAULT_MEDIA, help="mp4s go to <media-dir>/<slug>/")
    ap.add_argument("--parallel", type=int, default=2, help="slugs at once; the API runs 2 turns at a time")
    ap.add_argument("--turn-timeout", type=float, default=TURN_TIMEOUT, help="seconds per turn once it starts")
    ap.add_argument("--catalog", type=Path, default=WEB_CATALOG, help="web catalog, to warn about unknown tool ids")
    ap.add_argument("--index-only", action="store_true", help="only regenerate <out>/index.ts")
    a = ap.parse_args(argv)
    out = a.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    if a.index_only:
        p = write_index(out)
        print(f"wrote {p} with {', '.join(present_bundles(out)) or 'no bundles'}")
        return 0

    urls = parse_urls(URLS_FILE.read_text())
    slugs = [s.strip() for s in a.slugs.split(",") if s.strip()] or list(urls)
    unknown = [s for s in slugs if s not in urls]
    if unknown:
        print(f"Unknown slug(s): {', '.join(unknown)}. Known: {', '.join(urls)}", file=sys.stderr)
        return 2

    api = Api(a.api)
    try:
        api.http.get("/api/health").raise_for_status()
    except Exception as e:  # noqa: BLE001
        print(f"API not reachable at {a.api}: {type(e).__name__}", file=sys.stderr)
        return 2

    ids = catalog_ids(a.catalog)
    if ids is None:
        say("-", f"could not read {a.catalog}; skipping the tool id check")
    rows: dict[str, dict] = {}
    todo = []
    for s in slugs:
        if should_skip(out, s, a.force):
            b = json.loads((out / f"{s}.json").read_text())
            rows[s] = {"slug": s, "status": "skipped", "misses": validate(b, s), **_counts(b),
                       "unknown": unknown_tools(b, ids)}
            say(s, "bundle exists, skipping (use --force to redo)")
        else:
            todo.append(s)
    started = datetime.now(timezone.utc)
    with ThreadPoolExecutor(max_workers=max(1, a.parallel)) as pool:
        futures = {s: pool.submit(run_slug, api, s, urls[s], out, a.media_dir.resolve(), a.turn_timeout, ids)
                   for s in todo}
        for s, f in futures.items():
            rows[s] = f.result()

    p = write_index(out)
    print_table([rows[s] for s in slugs])
    mins = (datetime.now(timezone.utc) - started).total_seconds() / 60
    print(f"\nindex: {p} lists {', '.join(present_bundles(out)) or 'no bundles'}  ({mins:.1f} min)")
    bad = [s for s in slugs if rows[s]["misses"]]
    if bad:
        print(f"MISSES: {', '.join(bad)}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
