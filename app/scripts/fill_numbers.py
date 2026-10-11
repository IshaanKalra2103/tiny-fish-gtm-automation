"""Fill RUN_* placeholders in deliverables/README.md and launch-post.md from a finished run's files.

usage: uv run python scripts/fill_numbers.py <run-id>
"""

import json
import sys

from gtm import config

ROOT = config.ROOT / "deliverables"


def main(run_id: str) -> None:
    rd = config.RUNS_DIR / run_id
    load = lambda n, d=None: json.loads((rd / n).read_text()) if (rd / n).exists() else d
    ev, costs, timings, qa = load("evidence.json"), load("costs.json"), load("timings.json", {}), load("qa.json")
    calls = costs["calls"]
    social = sum(len(v) for v in ev["social_search"].values())
    yt = ev["youtube"]
    versions = qa["versions"]
    path = " → ".join(f"v{v['version']} {v['avg_score']}/10{' ✓' if v['passed'] else ''}" for v in versions)
    minutes = round(sum(timings.values()) / 60, 1)
    qa_line = (f"Draft 1 scored {versions[0]['avg_score']}/10 and failed, so it rewrote and re-rendered itself: {path}."
               if len(versions) > 1 else f"It scored {versions[0]['avg_score']}/10.")
    rows = [
        ("Target", f"{ev['brief']['brand_url']} · niche \"{ev['brief']['niche']}\""),
        ("TinyFish Search", f"{calls.get('search', {}).get('calls', 0)} queries → {len(ev['threads'])} threads, {len(ev['news'])} news, {social} TikTok/Reel URLs"),
        ("TinyFish Fetch", f"{calls.get('fetch', {}).get('calls', 0)} batch call(s), {len(ev['threads']) + 1} pages read as Markdown"),
        ("TinyFish Agent", f"{len(yt['videos'])} YouTube Shorts via {yt.get('source')} ({yt.get('steps', '?')} steps, ${calls.get('agent', {}).get('usd', 0):.2f})"),
        ("TinyFish Browser", f"{len(ev.get('shots', []))} phone-framed screenshots (${calls.get('browser', {}).get('usd', 0):.3f})"),
        ("Bright Data", ", ".join(f"{p}: {s.get('posts', 0)} posts" if s.get("ok") else f"{p}: not configured (personas fell back to Fetch threads)"
                                  for p, s in ev.get("brightdata", {}).items())),
        ("QA path", path),
        ("TinyFish spend", f"${costs['tinyfish_usd']:.2f}"),
        ("Wall-clock", f"{minutes} min ({', '.join(f'{k} {v:.0f}s' for k, v in timings.items())})"),
    ]
    table = "| | |\n|---|---|\n" + "\n".join(f"| {k} | {v} |" for k, v in rows)
    subs = {"RUN_NUMBERS": table, "RUN_SOCIAL": str(social), "RUN_THREADS": str(len(ev["threads"])),
            "RUN_QA_LINE": qa_line, "RUN_COST": f"${costs['tinyfish_usd']:.2f}", "RUN_MINUTES": str(minutes)}
    for name in ("README.md", "launch-post.md"):
        p = ROOT / name
        text = p.read_text()
        for k, v in subs.items():
            text = text.replace(k, v)
        p.write_text(text)
    print(json.dumps({"ok": True, **{k: v for k, v in subs.items() if k != "RUN_NUMBERS"}}))


if __name__ == "__main__":
    main(sys.argv[1])
