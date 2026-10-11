"""One execution lifecycle for local runs and Paperclip workers."""

from datetime import datetime, timezone

from .contract import ORDER, OUTPUTS


class StageBlocked(RuntimeError):
    pass


def record(run, role, status, summary="", **extra):
    state = run.read("workflow.json", {"schema_version": 1, "run": run.id, "stages": {}})
    state["stages"][role] = {"status": status, "summary": summary, **extra}
    state.update(status=status, current_stage=role, updated_at=datetime.now(timezone.utc).isoformat())
    if role == "learn" and status == "done":
        state["status"] = "complete"
    run.write("workflow.json", state)


def require_outputs(run, role):
    missing = [name for name in OUTPUTS[role] if not run.exists(name)]
    if missing:
        raise StageBlocked(f"{role} missing artifacts: {', '.join(missing)}")
    if role == "qa" and not run.read("qa.json").get("passed"):
        raise StageBlocked("QA exhausted its revisions without passing; review qa.json before retrying")
    if role == "publish" and run.read("publish.json").get("status") != "ready_to_publish":
        raise StageBlocked("Human approval is required before learning/completion")
    if role == "publish":
        from .roles.publish import fingerprint
        pkg = run.read("publish.json")
        qa = run.read("qa.json", {})
        if not qa.get("passed") or pkg.get("version") != qa.get("final_version") or pkg.get("artifact_hash") != fingerprint(run, pkg["version"]):
            raise StageBlocked("Approved artifacts changed; a new package and approval are required")


def execute(run, role, worker):
    with run.exclusive():
        state = run.read("workflow.json", {}).get("stages", {}).get(role, {})
        if state.get("status") == "done":
            require_outputs(run, role)
            return state.get("summary", f"{role} already done")
        record(run, role, "running")
        try:
            if role != ORDER[0]:
                require_outputs(run, ORDER[ORDER.index(role) - 1])
            run.log(role, "started")
            summary = worker(run)
            # Publish produces a package first, then pauses at the human gate.
            if role == "publish" and run.read("publish.json", {}).get("status") == "awaiting_approval":
                record(run, role, "awaiting_approval", summary)
            else:
                require_outputs(run, role)
                record(run, role, "done", summary)
            return summary
        except Exception as exc:
            record(run, role, "blocked", str(exc))
            raise
