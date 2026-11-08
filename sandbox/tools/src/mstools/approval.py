"""approval: ask the owner to approve a setup. Returns at once; the agent then ends its turn."""
import argparse
import uuid
from datetime import datetime, timezone

from .cli import ToolError, run
from .ws import load, save


def _main(a: argparse.Namespace) -> dict:
    if a.cmd == "request":
        aid = "ap_" + uuid.uuid4().hex[:10]
        save("approval", {"id": aid, "tool_id": a.tool, "summary": a.summary, "status": "pending",
                          "created_at": datetime.now(timezone.utc).isoformat()})
        return {"approval_id": aid, "status": "pending",
                "message": "Approval requested. End your turn now; the owner will decide."}
    data = load("approval", a.id)
    if data is None:
        raise ToolError(f"No approval with id '{a.id}'.")
    return {"approval": data}


def main() -> None:
    p = argparse.ArgumentParser(prog="approval", description="Request or check an owner approval.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("request")
    r.add_argument("--tool", required=True)
    r.add_argument("--summary", required=True)
    s = sub.add_parser("status")
    s.add_argument("id")
    run(_main, p)


if __name__ == "__main__":
    main()
