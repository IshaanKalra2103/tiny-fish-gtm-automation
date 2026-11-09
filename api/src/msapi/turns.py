"""Turns: queue per owner (one at a time) and globally (max_concurrent), translate agent events for the web."""
import asyncio
import json
import logging
import re
import secrets
from dataclasses import dataclass, field
from datetime import date
from pathlib import Path
from typing import AsyncIterator

from .runner import Runner
from .settings import Settings
from .workspaces import NotFound, Workspaces

log = logging.getLogger("msapi.turns")
TURN_RE = re.compile(r"^t_[0-9a-f]{12}$")
FAILED = "Something went wrong on my side. Please try again in a minute."

# Bash command prefix -> what the owner sees while it runs.
STATUS = [
    ("tf search", "Searching the web"),
    ("tf fetch", "Reading pages"),
    ("catalog needs", "Looking at what businesses like yours need"),
    ("catalog match", "Checking our vetted tools"),
    ("catalog get", "Looking up a tool"),
    ("preview make", "Making a short preview video. This takes a few minutes."),
    ("approval request", "Asking for your OK"),
    ("approval status", "Checking your answer"),
    ("tf agent-start", "Starting the setup browser"),
    ("tf agent-wait", "Setting it up in a cloud browser"),
    ("tf agent-status", "Checking on the setup"),
    ("inbox create", "Making an inbox for the sign-up email"),
    ("inbox wait", "Waiting for the confirmation email"),
    ("inbox read", "Reading the confirmation email"),
]
# Bash command prefix -> record kind that changes when it succeeds.
FILES = {"approval request": "approval", "preview make": "preview"}


class LimitReached(Exception):
    pass


def _text(content) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(c.get("text", "") for c in content if isinstance(c, dict))
    return ""




def plain(text: str) -> str:
    """Drop markdown bold and headings: the web bubble and iMessage both show them as raw symbols."""
    text = re.sub(r"\*\*(.+?)\*\*", r"\1", text)
    text = re.sub(r"__(.+?)__", r"\1", text)
    return re.sub(r"(?m)^#{1,6}\s+", "", text)


class Translator:
    """stream-json events -> UI events: status{text}, files{kinds}, done{reply}, error{message}."""

    def __init__(self):
        self.pending: dict[str, str] = {}

    def __call__(self, ev: dict) -> list[dict]:
        t = ev.get("type")
        out: list[dict] = []
        if t == "assistant":
            # Assistant text is not shown: it is the agent talking to itself, and its last text repeats the reply.
            for c in (ev.get("message") or {}).get("content") or []:
                if c.get("type") == "tool_use" and c.get("name") == "Bash":
                    cmd = ((c.get("input") or {}).get("command") or "").strip()
                    label = next((s for p, s in STATUS if cmd.startswith(p)), None)
                    if label:
                        out.append({"type": "status", "text": label})
                    m = re.match(r"ws save (\w+)", cmd)
                    kind = m.group(1) if m else next((k for p, k in FILES.items() if cmd.startswith(p)), None)
                    if kind:
                        self.pending[c.get("id")] = kind
        elif t == "user":
            content = (ev.get("message") or {}).get("content")
            for c in content if isinstance(content, list) else []:
                if c.get("type") == "tool_result" and c.get("tool_use_id") in self.pending:
                    kind = self.pending.pop(c["tool_use_id"])
                    if not c.get("is_error") and re.search(r'"ok":\s*true', _text(c.get("content"))):
                        out.append({"type": "files", "kinds": [kind]})
        elif t == "result":
            if ev.get("is_error") or ev.get("subtype") != "success":
                out.append({"type": "error", "message": FAILED, "detail": str(ev.get("result") or ev.get("subtype"))[:500]})
            else:
                out.append({"type": "done", "reply": plain(ev.get("result") or "")})
        elif t == "runner_error":
            out.append({"type": "error", "message": FAILED, "detail": str(ev.get("message"))[:500]})
        return out


@dataclass
class Turn:
    id: str
    owner_id: str
    channel: str
    events: list[dict] = field(default_factory=list)
    started: bool = False
    done: bool = False
    changed: asyncio.Event = field(default_factory=asyncio.Event)


class TurnManager:
    def __init__(self, runner: Runner, ws: Workspaces, settings: Settings):
        self.runner, self.ws, self.s = runner, ws, settings
        self.sem = asyncio.Semaphore(settings.max_concurrent)
        self.locks: dict[str, asyncio.Lock] = {}
        self.turns: dict[str, Turn] = {}
        self.tasks: set[asyncio.Task] = set()
        self.counts: dict[tuple[str, str], int] = {}

    def _file(self, turn: Turn, suffix: str = ".jsonl") -> Path:
        return self.ws.owner_dir(turn.owner_id) / "turns" / f"{turn.id}{suffix}"

    def _emit(self, turn: Turn, ev: dict) -> None:
        public = {k: v for k, v in ev.items() if k != "detail"}
        turn.events.append(public)
        f = self._file(turn)
        f.parent.mkdir(parents=True, exist_ok=True)
        with open(f, "a") as fh:
            fh.write(json.dumps(ev) + "\n")
        if ev["type"] in ("done", "error"):
            turn.done = True
        turn.changed.set()
        turn.changed = asyncio.Event()

    def _raw(self, turn: Turn, ev: dict) -> None:
        f = self._file(turn, ".raw.jsonl")
        new = not f.exists()
        with open(f, "a") as fh:
            fh.write(json.dumps(ev) + "\n")
        if new:
            f.chmod(0o600)

    def start(self, owner_id: str, text: str, channel: str = "web", log_text: str | None = None) -> str:
        self.ws.require(owner_id)
        key = (owner_id, date.today().isoformat())
        if self.counts.get(key, 0) >= self.s.turns_per_owner_day:
            raise LimitReached("That's a lot for one day. Please come back tomorrow.")
        self.counts[key] = self.counts.get(key, 0) + 1
        turn = Turn(id="t_" + secrets.token_hex(6), owner_id=owner_id, channel=channel)
        self.turns[turn.id] = turn
        self.ws.add_message(owner_id, "owner", log_text or text, channel)
        lock = self.locks.setdefault(owner_id, asyncio.Lock())
        if lock.locked() or self.sem.locked():
            waiting = sum(1 for t in self.turns.values() if not t.done and not t.started and t.id != turn.id)
            self._emit(turn, {"type": "queued", "position": waiting + 1})
        task = asyncio.create_task(self._run(turn, text))
        self.tasks.add(task)
        task.add_done_callback(self.tasks.discard)
        return turn.id

    def active_turn(self, owner_id: str) -> str | None:
        return next((t.id for t in self.turns.values() if t.owner_id == owner_id and not t.done), None)

    async def _run(self, turn: Turn, text: str) -> None:
        oid = turn.owner_id
        try:
            async with self.locks[oid]:
                async with self.sem:
                    turn.started = True
                    self._emit(turn, {"type": "status", "text": "Starting your assistant"})
                    sid, resume = self.ws.session(oid)
                    prompt = f"[channel={turn.channel} owner={oid} link={self.s.web_url}/b/{oid}]\n{text}"
                    tr, terminal = Translator(), None
                    async for raw in self.runner.run(oid, prompt, sid, resume):
                        self._raw(turn, raw)
                        if raw.get("type") == "result":
                            self.ws.mark_started(oid)
                        for ui in tr(raw):
                            if ui["type"] in ("done", "error"):
                                terminal = terminal or ui
                            else:
                                self._emit(turn, ui)
                    terminal = terminal or {"type": "error", "message": FAILED, "detail": "no result event"}
                    if terminal["type"] == "done":
                        self.ws.add_message(oid, "agent", terminal["reply"], turn.channel)
                    self._emit(turn, terminal)
        except Exception as e:  # never leave a turn hanging
            log.exception("turn %s failed", turn.id)
            if not turn.done:
                self._emit(turn, {"type": "error", "message": FAILED, "detail": repr(e)[:500]})

    def _load(self, turn_id: str) -> Turn:
        """A turn from before a restart: replay its file; if it never finished, it never will."""
        if not TURN_RE.match(turn_id or ""):
            raise NotFound(turn_id)
        hits = list(self.ws.root.glob(f"o_*/turns/{turn_id}.jsonl"))
        if not hits:
            raise NotFound(turn_id)
        evs = [json.loads(line) for line in hits[0].read_text().splitlines() if line.strip()]
        evs = [{k: v for k, v in e.items() if k != "detail"} for e in evs]
        if not evs or evs[-1]["type"] not in ("done", "error"):
            evs.append({"type": "error", "message": "This request was interrupted. Please send it again."})
        return Turn(id=turn_id, owner_id=hits[0].parent.parent.name, channel="web", events=evs, started=True, done=True)

    def get(self, turn_id: str) -> Turn:
        return self.turns.get(turn_id) or self._load(turn_id)

    async def events(self, turn_id: str, heartbeat: float = 15.0) -> AsyncIterator[dict | None]:
        """Every UI event of the turn from the start, then live ones; None is a heartbeat."""
        turn = self.get(turn_id)
        i = 0
        while True:
            while i < len(turn.events):
                yield turn.events[i]
                i += 1
            if turn.done:
                return
            changed = turn.changed
            try:
                await asyncio.wait_for(changed.wait(), heartbeat)
            except TimeoutError:
                yield None

    async def wait(self, turn_id: str, timeout: float) -> dict | None:
        try:
            async with asyncio.timeout(timeout):
                async for ev in self.events(turn_id):
                    if ev and ev["type"] in ("done", "error"):
                        return ev
        except TimeoutError:
            return None
        return None
