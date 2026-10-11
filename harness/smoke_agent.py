# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Harness smoke test: a process agent that proves the Paperclip <-> container loop.
Checks env injection, the run token, issue discovery, checkout, comment, done."""
import json
import os
import platform
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from paperclip_agent import PaperclipRun  # noqa: E402

pc = PaperclipRun.from_env()
issue = pc.current_issue()
if issue is None:
    print(json.dumps({"ok": True, "note": "no work"}))
    sys.exit(0)
pc.checkout(issue["id"])
campaign = pc.campaign_id(issue)
facts = {
    "issue": issue.get("identifier"), "campaign": campaign, "wake": pc.wake_context().get("wakeReason")
    or pc.wake_context().get("source"), "python": platform.python_version(), "uid": os.getuid(),
    "tinyfish_key_present": bool(os.environ.get("TINYFISH_API_KEY")),
    "uv_project_env": os.environ.get("UV_PROJECT_ENVIRONMENT"),
}
pc.done(issue["id"], "Harness smoke test OK\n\n```json\n" + json.dumps(facts, indent=2) + "\n```")
print(json.dumps({"ok": True, **facts}))
