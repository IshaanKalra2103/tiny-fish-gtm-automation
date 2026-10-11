"""Analytics & Learning: turn this run's QA history into durable learnings that the next run's analysis reads.

Real engagement isn't available (publishing is simulated), so learnings come from QA failures and fixes, clearly
labelled as simulated-persona evidence.
"""

import json
from datetime import datetime, timezone

from .. import config
from ..run import Run

ROLE = "learn"


def run(r: Run) -> str:
    qa = r.read("qa.json")
    versions = [r.read(f"qa_v{v['version']}.json") for v in qa["versions"]]
    failures = sorted({b.split(" (")[0] for v in versions for b in v["blocking"]})
    final = r.read(f"script_v{qa['final_version']}.json")
    entry = {
        "run": r.id, "at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "niche": r.brief["niche"], "drafts": len(versions), "passed": qa["passed"],
        "score_path": [v["avg_score"] for v in versions],
        "recurring_failures": failures,
        "winning_hook": final["hook"] if qa["passed"] else None,
        "what_fixed_it": final.get("changes_from_previous"),
        "evidence_type": "simulated personas (not real engagement)",
    }
    memory = json.loads(config.MEMORY_FILE.read_text()) if config.MEMORY_FILE.exists() else []
    memory = [item for item in memory if item.get("run") != r.id] + [entry]
    config.MEMORY_FILE.parent.mkdir(parents=True, exist_ok=True)
    config.MEMORY_FILE.write_text(json.dumps(memory, indent=2))
    r.write("learnings.json", entry)
    msg = f"learnings: {len(failures)} failure types recorded; memory now holds {len(memory)} run(s)"
    r.log(ROLE, msg)
    return msg
