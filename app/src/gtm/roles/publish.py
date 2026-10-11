"""Publishing: package the approved draft and stop at the human approval gate. Posting itself is simulated.

Paperclip mode: files a board approval; Paperclip re-wakes this role with wakeReason=approval_approved.
Local mode: `gtm approve <run>` flips the gate.
"""

from pydantic import BaseModel
import hashlib
from datetime import datetime, timezone

from .. import config, llm
from ..run import Run

ROLE = "publish"


class PostCopy(BaseModel):
    tiktok_caption: str
    reels_caption: str
    shorts_title: str
    hashtags: list[str]
    best_time_utc: str


def fingerprint(r: Run, version: int) -> str:
    digest = hashlib.sha256()
    for name in (f"video_v{version}.mp4", f"script_v{version}.json", "qa.json"):
        path = r.dir / name
        if not path.is_file():
            raise ValueError(f"Cannot approve: missing {name}")
        digest.update(name.encode())
        with path.open("rb") as f:
            for chunk in iter(lambda: f.read(1024 * 1024), b""):
                digest.update(chunk)
    return digest.hexdigest()


def run(r: Run, approved: bool = False, approval: dict | None = None) -> str:
    qa = r.read("qa.json")
    pkg = r.read("publish.json")
    if not qa or not qa.get("passed"):
        raise ValueError("Passing QA is required before preparing or approving a package")
    v = qa["final_version"]
    current_hash = fingerprint(r, v)
    if pkg and (pkg.get("version") != v or pkg.get("artifact_hash") != current_hash):
        raise ValueError("Publish package is stale; regenerate it and request a new approval")
    if pkg and approved:
        if pkg.get("approval_id") and (not approval or approval.get("id") != pkg["approval_id"] or approval.get("status") != "approved"):
            raise ValueError("This campaign requires its verified Paperclip board approval")
        pkg.update(status="ready_to_publish", note="Approved by a human. Publishing is simulated in this demo.",
                   approved_at=datetime.now(timezone.utc).isoformat(), approval=approval or {"source": "local-cli"})
        r.write("publish.json", pkg)
        r.log(ROLE, f"approved -> v{pkg['version']} is ready to publish (simulated)")
        return f"Approved: video_v{pkg['version']}.mp4 is ready to publish (simulated)"
    if pkg:
        return f"publish.json already {pkg['status']}"

    if approved:
        raise ValueError("Prepare the publish package before approving it")
    s = r.read(f"script_v{v}.json")
    ev = r.read("evidence.json")
    utm = f"{ev['brief']['brand_url']}?utm_source={{platform}}&utm_medium=short_video&utm_campaign={r.id}"
    copy = llm.parse(r, ROLE, "fast", "Write platform-native captions for a developer audience. No hype.",
                     [llm.text(f"Script: {s}\nLink (keep the {{platform}} placeholder): {utm}")], PostCopy)
    pkg = {"version": v, "video": f"video_v{v}.mp4", "qa_passed": qa["passed"], "artifact_hash": current_hash,
           "status": "awaiting_approval" if qa["passed"] else "needs_human",
           "copy": copy.model_dump(), "link": utm, "simulated": True}
    r.write("publish.json", pkg)
    r.log(ROLE, f"publish.json: v{v} {pkg['status']}; approve with `gtm approve {r.id}` or on the Paperclip board")
    return f"Packaged video_v{v}.mp4 + captions; status {pkg['status']}"
