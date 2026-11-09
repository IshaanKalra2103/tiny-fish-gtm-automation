"""ws: save and read typed records in the owner workspace (spec §6.4)."""
import argparse
import json
import os
import re
import sys
from pathlib import Path

from . import config
from .cli import ToolError, run
from .schemas import APPROVAL_ID_PATTERN, ID_PATTERN, KINDS

REDACTED = "***"


def check_id(value: str | None, what: str = "tool id", pattern: str = ID_PATTERN) -> str:
    """Ids from the model become file names, so they are checked before any path is built."""
    if not isinstance(value, str) or not re.fullmatch(pattern, value):
        raise ToolError(f"'{value}' is not a valid {what}. Use the id exactly as the catalog gives it "
                        "(lowercase letters, digits and dashes).")
    return value


def _inside(work: Path, path: Path) -> Path:
    """Second wall: whatever the id, the file must land inside the workspace."""
    if not path.resolve().is_relative_to(work.resolve()):
        raise ToolError("That record would be saved outside your workspace, so it was not saved.")
    return path


def path_for(kind: str, data: dict, work: Path) -> Path:
    if kind == "profile":
        return work / "profile.json"
    if kind == "needs":
        return work / "needs.json"
    if kind == "compare":
        return _inside(work, work / f"compare_{check_id(data['need_id'], 'job id')}.json")
    if kind == "preview":
        return _inside(work, work / f"preview_{check_id(data['tool_id'])}.json")
    if kind == "setup":
        return _inside(work, work / f"setup_{check_id(data['tool_id'])}.json")
    if kind == "approval":
        return _inside(work, work / "approvals" / f"{check_id(data['id'], 'approval id', APPROVAL_ID_PATTERN)}.json")
    raise ToolError(f"Unknown kind '{kind}'. Use one of: {', '.join(KINDS)}.")


def find(kind: str, id: str | None, work: Path) -> Path:
    keyed = {"compare": "need_id", "preview": "tool_id", "setup": "tool_id", "approval": "id"}
    if kind in keyed:
        if not id:
            raise ToolError(f"'{kind}' needs --id ({keyed[kind]}).")
        return path_for(kind, {keyed[kind]: id}, work)
    return path_for(kind, {}, work)


def redact(data: dict) -> dict:
    return {**data, "password": REDACTED} if data.get("password") else data


def save(kind: str, data: dict, work: Path | None = None) -> Path:
    if kind not in KINDS:
        raise ToolError(f"Unknown kind '{kind}'. Use one of: {', '.join(KINDS)}.")
    work = work or config.work()
    record = KINDS[kind].model_validate(data).model_dump()
    path = path_for(kind, record, work)
    if kind == "setup" and record.get("password") in (None, REDACTED) and path.exists():
        record["password"] = json.loads(path.read_text()).get("password")
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(record, indent=1))
    if kind == "setup":
        os.chmod(tmp, 0o600)
    tmp.replace(path)
    return path


def load(kind: str, id: str | None = None, work: Path | None = None) -> dict | None:
    path = find(kind, id, work or config.work())
    return json.loads(path.read_text()) if path.exists() else None


def _main(a: argparse.Namespace) -> dict:
    if a.cmd == "save":
        if a.kind == "approval":
            raise ToolError("Approvals are made with `approval request` and decided only by the owner.")
        raw = sys.stdin.read() if a.file == "-" else Path(a.file).read_text()
        try:
            data = json.loads(raw)
        except json.JSONDecodeError as e:
            raise ToolError(f"That file is not valid JSON: {e}")
        p = save(a.kind, data)
        return {"path": str(p), "data": redact(json.loads(p.read_text()))}
    data = load(a.kind, a.id)
    if data is None:
        raise ToolError(f"No saved {a.kind}{' for ' + a.id if a.id else ''} yet.")
    return {"data": redact(data)}


def main() -> None:
    p = argparse.ArgumentParser(prog="ws", description="Save or read owner workspace records.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("save", help="ws save <kind> <file|->")
    s.add_argument("kind", choices=list(KINDS))
    s.add_argument("file")
    g = sub.add_parser("get", help="ws get <kind> [--id X]")
    g.add_argument("kind", choices=list(KINDS))
    g.add_argument("--id")
    run(_main, p)


if __name__ == "__main__":
    main()
