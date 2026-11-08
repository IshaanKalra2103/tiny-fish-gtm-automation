"""One campaign run: a folder under runs/<id>/ that every role reads and writes (shared memory)."""

import json
import os
import re
import tempfile
import fcntl
from contextlib import contextmanager
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from . import config

_lock = threading.Lock()


class BudgetExceeded(RuntimeError):
    pass


class Run:
    def __init__(self, run_id: str):
        if not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_.-]*", run_id):
            raise ValueError("Invalid run id")
        self.id = run_id
        self.dir = config.RUNS_DIR / run_id
        self.dir.mkdir(parents=True, exist_ok=True)

    # ── files ───────────────────────────────────────────────────────────
    def path(self, name: str) -> Path:
        p = self.dir / name
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def read(self, name: str, default: Any = None) -> Any:
        p = self.dir / name
        return json.loads(p.read_text()) if p.exists() else default

    def write(self, name: str, obj: Any) -> Path:
        p = self.path(name)
        fd, tmp = tempfile.mkstemp(dir=p.parent, prefix=".write-")
        try:
            with os.fdopen(fd, "w") as f:
                f.write(json.dumps(obj, indent=2, ensure_ascii=False, default=str))
            os.replace(tmp, p)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return p

    @contextmanager
    def exclusive(self):
        """Prevent two worker processes from executing the same campaign concurrently."""
        with self.path(".worker.lock").open("a") as lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
            except BlockingIOError as exc:
                raise RuntimeError(f"Campaign {self.id} already has an active worker") from exc
            try:
                yield
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)

    def exists(self, name: str) -> bool:
        return (self.dir / name).exists()

    @property
    def brief(self) -> dict:
        return self.read("brief.json") or config.DEFAULT_BRIEF

    # ── activity log + cost ledger ──────────────────────────────────────
    def log(self, role: str, msg: str, **data: Any) -> None:
        entry = {"ts": datetime.now(timezone.utc).isoformat(timespec="seconds"), "role": role, "msg": msg, **data}
        with _lock, self.path("activity.jsonl").open("a") as f:
            f.write(json.dumps(entry, default=str) + "\n")
        print(f"[{role}] {msg}", file=sys.stderr, flush=True)

    def activity(self) -> list[dict]:
        p = self.dir / "activity.jsonl"
        return [json.loads(line) for line in p.read_text().splitlines() if line.strip()] if p.exists() else []

    def charge(self, primitive: str, usd: float, **data: Any) -> None:
        """Record TinyFish spend per primitive; stop the run at the budget cap (Paperclip-style hard stop)."""
        with _lock:
            ledger = self.read("costs.json", {"tinyfish_usd": 0.0, "calls": {}, "llm_tokens": 0})
            ledger["tinyfish_usd"] = round(ledger["tinyfish_usd"] + usd, 4)
            c = ledger["calls"].setdefault(primitive, {"calls": 0, "usd": 0.0})
            c["calls"] += 1
            c["usd"] = round(c["usd"] + usd, 4)
            ledger["llm_tokens"] += data.get("tokens", 0)
            self.write("costs.json", ledger)
        if ledger["tinyfish_usd"] > config.TINYFISH_BUDGET_USD:
            raise BudgetExceeded(f"TinyFish spend ${ledger['tinyfish_usd']} exceeds budget ${config.TINYFISH_BUDGET_USD}")
        if ledger["tinyfish_usd"] > 0.8 * config.TINYFISH_BUDGET_USD:
            self.log("harness", f"budget warning: ${ledger['tinyfish_usd']} of ${config.TINYFISH_BUDGET_USD} used")

    def timer(self, step: str):
        return _Timer(self, step)


class _Timer:
    def __init__(self, run: Run, step: str):
        self.run, self.step = run, step

    def __enter__(self):
        self.t0 = time.time()
        return self

    def __exit__(self, *exc):
        timings = self.run.read("timings.json", {})
        timings[self.step] = round(time.time() - self.t0, 1)
        self.run.write("timings.json", timings)
