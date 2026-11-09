"""End-to-end check through the waker URL: health, POST /api/owners, one turn polled to done, with timings.

    uv run --no-project deploy/gcp/smoke.py [WAKER_URL] [--text "..."]

WAKER_URL defaults to the one in deploy/gcp/project.env. Stdlib only.
"""
import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ORIGIN = "https://mainstreet-ai-five.vercel.app"


def call(method: str, url: str, body: dict | None = None, timeout: float = 200) -> tuple[int, dict]:
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method,
                                 headers={"Content-Type": "application/json", "Origin": ORIGIN})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read() or b"{}")
    except urllib.error.HTTPError as e:
        return e.code, json.loads(e.read() or b"{}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?")
    ap.add_argument("--text", default="I run a bakery in Bowie MD, what should I try first? Keep it short.")
    ap.add_argument("--source", default="Sweet Rise Bakery, Bowie MD")
    a = ap.parse_args()
    url = a.url
    if not url:
        env = Path(__file__).with_name("project.env").read_text()
        url = next(line.split("=", 1)[1] for line in env.splitlines() if line.startswith("WAKER_URL="))
    url = url.rstrip("/")
    t0 = time.monotonic()
    el = lambda: f"{time.monotonic() - t0:6.1f}s"  # noqa: E731

    st, h = call("GET", f"{url}/api/health", timeout=30)
    print(f"{el()} health {st} {h}")
    st, o = call("POST", f"{url}/api/owners", {"source": a.source})
    print(f"{el()} POST /api/owners {st} {o}")
    if st != 200:
        return 1
    oid = o["owner_id"]
    st, t = call("POST", f"{url}/api/owners/{oid}/turns", {"text": a.text, "channel": "web"})
    print(f"{el()} POST /api/owners/{oid}/turns {st} {t}")
    if st != 200:
        return 1
    tid, after, got_done = t["turn_id"], 0, False
    while time.monotonic() - t0 < 1200:
        st, p = call("GET", f"{url}/api/turns/{tid}/poll?after={after}", timeout=60)
        if st != 200:
            print(f"{el()} poll {st} {p}")
            time.sleep(3)
            continue
        for ev in p["events"]:
            if ev.get("type") == "done":
                got_done = True
                print(f"{el()} done: {ev.get('reply', '')}")
            elif ev.get("type") == "error":
                print(f"{el()} error: {ev}")
            else:
                print(f"{el()} {ev.get('type')}: {ev.get('text') or ev.get('kinds') or ''}")
        after = p["next"]
        if p["done"]:
            print(f"{el()} turn finished ({'ok' if got_done else 'error'})")
            return 0 if got_done else 1
        time.sleep(2)
    print("timed out")
    return 1


if __name__ == "__main__":
    sys.exit(main())
