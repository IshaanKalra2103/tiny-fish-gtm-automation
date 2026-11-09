"""Owner workspaces on disk: one folder per owner, mounted at /work in that owner's sandbox."""
import json
import re
import secrets
import uuid
from datetime import datetime, timezone
from pathlib import Path

from mstools.ws import redact

OWNER_RE = re.compile(r"^o_[0-9a-f]{10}$")
TOOL_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


class NotFound(Exception):
    pass


class Gone(Exception):
    pass


def now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _read(p: Path):
    try:
        return json.loads(p.read_text())
    except (FileNotFoundError, json.JSONDecodeError):
        return None


def _write(p: Path, data, mode: int | None = None) -> None:
    p.parent.mkdir(parents=True, exist_ok=True)
    tmp = p.with_suffix(p.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1))
    if mode is not None:
        tmp.chmod(mode)
    tmp.replace(p)


class Workspaces:
    def __init__(self, root: Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    # owners
    def create_owner(self, source: str, channel: str = "web") -> str:
        oid = "o_" + secrets.token_hex(5)
        d = self.root / oid
        (d / "tmp").mkdir(parents=True)
        self.decisions_dir(oid).mkdir(parents=True, exist_ok=True)
        _write(d / "source.json", {"source": source, "channel": channel, "created_at": now()})
        return oid

    def owner_dir(self, owner_id: str) -> Path:
        if not OWNER_RE.match(owner_id or ""):
            raise NotFound(owner_id)
        return self.root / owner_id

    def decisions_dir(self, owner_id: str) -> Path:
        """Outside the owner folder and mounted read-only at /decisions, so only the API can say yes."""
        return self.root / "_decisions" / self.owner_dir(owner_id).name

    def exists(self, owner_id: str) -> bool:
        try:
            return (self.owner_dir(owner_id) / "source.json").exists()
        except NotFound:
            return False

    def require(self, owner_id: str) -> Path:
        if not self.exists(owner_id):
            raise NotFound(owner_id)
        return self.owner_dir(owner_id)

    # sessions: --session-id on the first turn, --resume after Claude has created it
    def session(self, owner_id: str) -> tuple[str, bool]:
        p = self.require(owner_id) / "session.json"
        s = _read(p)
        if not s:
            s = {"session_id": str(uuid.uuid4()), "started": False}
            _write(p, s)
        return s["session_id"], bool(s["started"])

    def mark_started(self, owner_id: str) -> None:
        p = self.require(owner_id) / "session.json"
        s = _read(p) or {}
        if not s.get("started"):
            _write(p, {**s, "started": True})

    # messages
    def add_message(self, owner_id: str, role: str, text: str, channel: str) -> None:
        with open(self.require(owner_id) / "messages.jsonl", "a") as f:
            f.write(json.dumps({"role": role, "text": text, "channel": channel, "at": now()}) + "\n")

    def messages(self, owner_id: str) -> list[dict]:
        p = self.require(owner_id) / "messages.jsonl"
        if not p.exists():
            return []
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()]

    # approvals: decided only here, never by the agent
    def pending_approval(self, owner_id: str, approval_id: str) -> dict:
        """The approval if it is still pending. Raises NotFound, or ValueError if it was already decided."""
        if not re.fullmatch(r"ap_[A-Za-z0-9]+", approval_id or ""):
            raise NotFound(approval_id)
        ap = _read(self.require(owner_id) / "approvals" / f"{approval_id}.json")
        if not ap:
            raise NotFound(approval_id)
        prior = _read(self.decisions_dir(owner_id) / f"{approval_id}.json")
        if prior or ap.get("status") != "pending":
            raise ValueError((prior or ap).get("status"))
        return ap

    def decide(self, owner_id: str, approval_id: str, decision: str) -> dict:
        """Flip a pending approval. Raises NotFound, or ValueError if it was already decided."""
        ap = self.pending_approval(owner_id, approval_id)
        p = self.owner_dir(owner_id) / "approvals" / f"{approval_id}.json"
        ap = {**ap, "status": "approved" if decision == "approve" else "rejected", "decided_at": now()}
        _write(self.decisions_dir(owner_id) / f"{approval_id}.json",
               {"id": approval_id, "tool_id": ap["tool_id"], "status": ap["status"], "decided_at": ap["decided_at"]})
        _write(p, ap)
        return ap

    # bundle for the web page
    def read_bundle(self, owner_id: str) -> dict:
        d = self.require(owner_id)
        src = _read(d / "source.json") or {}
        revealed = set(_read(d / ".revealed.json") or [])
        compares, previews, setups = {}, {}, {}
        for f in sorted(d.glob("compare_*.json")):
            if (c := _read(f)):
                compares[c.get("need_id", f.stem[8:])] = c
        for f in sorted(d.glob("preview_*.json")):
            if (pv := _read(f)):
                vf = pv.get("video_file")
                ok = vf and (d / vf).exists() and pv.get("status") == "completed"
                previews[pv["tool_id"]] = {**pv, "video_url": f"/media/{owner_id}/{vf}" if ok else None}
        for f in sorted(d.glob("setup_*.json")):
            if (s := _read(f)):
                has = bool(s.get("password")) and s["tool_id"] not in revealed
                rec = {k: v for k, v in redact(s).items() if k != "password"}
                setups[s["tool_id"]] = {**rec, "has_password": has}
        approvals = [a for f in sorted((d / "approvals").glob("*.json")) if (a := _read(f))] if (d / "approvals").exists() else []
        approvals.sort(key=lambda a: a.get("created_at", ""))
        return {
            "owner_id": owner_id,
            "source": src.get("source") or "",
            "profile": _read(d / "profile.json"),
            "needs": _read(d / "needs.json"),
            "compares": compares,
            "previews": previews,
            "setups": setups,
            "approvals": approvals,
            "messages": self.messages(owner_id),
        }

    def reveal_password(self, owner_id: str, tool_id: str) -> str:
        """Hand the password over once. Raises NotFound if there is none, Gone after the first read."""
        if not TOOL_RE.match(tool_id or ""):
            raise NotFound(tool_id)
        d = self.require(owner_id)
        s = _read(d / f"setup_{tool_id}.json")
        if not s or not s.get("password"):
            raise NotFound(tool_id)
        revealed = _read(d / ".revealed.json") or []
        if tool_id in revealed:
            raise Gone(tool_id)
        _write(d / ".revealed.json", revealed + [tool_id], mode=0o600)
        return s["password"]

    def media_path(self, owner_id: str, name: str) -> Path:
        if not re.fullmatch(r"preview_[a-z0-9-]+\.mp4", name or ""):
            raise NotFound(name)
        p = self.require(owner_id) / name
        if not p.exists():
            raise NotFound(name)
        return p

    # iMessage: the relay sends a hash of the phone number, never the number
    def owner_for_phone(self, from_hash: str) -> str:
        p = self.root / "_phones.json"
        phones = _read(p) or {}
        oid = phones.get(from_hash)
        if oid and self.exists(oid):
            return oid
        oid = self.create_owner("", channel="imessage")
        phones[from_hash] = oid
        _write(p, phones, mode=0o600)
        return oid
