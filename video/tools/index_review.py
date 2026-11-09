# /// script
# requires-python = ">=3.11"
# ///
"""Write an index.json (sort_footage format) for clips cut from one raw take by the review step.

usage: uv run video/tools/index_review.py <transcript.json> <clip-dir> [out.json]
Each chosen take in transcript.json["takes"] maps to <clip-dir>/<cid>.mov; words are shifted to clip time.
"""
import json
import sys
from pathlib import Path

tr = json.loads(Path(sys.argv[1]).read_text())
d = Path(sys.argv[2]).resolve()
out = Path(sys.argv[3]) if len(sys.argv) > 3 else d / "index.json"
root = Path(__file__).resolve().parents[2]
rows = []
for t in tr["takes"]:
    if not t.get("chosen"):
        continue
    f = d / f"{t['cid']}.mov"
    if not f.exists():
        print("missing", f)
        continue
    a, b = t["in"], t["out"]
    ws = [{"w": w["w"], "s": round(w["s"] - a, 2), "e": round(w["e"] - a, 2)} for w in tr["words"] if a <= w["s"] < b]
    rows.append({"file": str(f.relative_to(root)), "duration": round(b - a, 2), "clip": t["cid"], "text": t["text"],
                 "line_start": round(t["first"] - a, 2), "line_end": round(t["last"] - a, 2), "words": ws})
out.write_text(json.dumps(rows, indent=1))
print(f"{len(rows)} clips -> {out}")
