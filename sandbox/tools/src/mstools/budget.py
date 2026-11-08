"""File-locked spend and count ledgers. A charge that would pass its cap raises and writes nothing."""
import fcntl
import json
from contextlib import contextmanager
from datetime import date
from pathlib import Path

from .cli import ToolError


class BudgetExceeded(ToolError):
    pass


@contextmanager
def _locked(ledger: Path):
    ledger.parent.mkdir(parents=True, exist_ok=True)
    lock = ledger.with_suffix(ledger.suffix + ".lock")
    with open(lock, "a") as fh:
        fcntl.flock(fh, fcntl.LOCK_EX)
        data = json.loads(ledger.read_text()) if ledger.exists() and ledger.stat().st_size else {}
        box = {"data": data, "dirty": False}
        try:
            yield box
            if box["dirty"]:
                tmp = ledger.with_suffix(ledger.suffix + ".tmp")
                tmp.write_text(json.dumps(box["data"], indent=1))
                tmp.replace(ledger)
        finally:
            fcntl.flock(fh, fcntl.LOCK_UN)


def charge(ledger: Path, key: str, usd: float, cap: float) -> float:
    with _locked(ledger) as box:
        usd_map = box["data"].setdefault("usd", {})
        now = float(usd_map.get(key, 0.0))
        if now + usd > cap + 1e-9:
            raise BudgetExceeded(f"Budget for {key} is spent: ${now:.2f} of ${cap:.2f} used, this needs ${usd:.2f} more.")
        usd_map[key] = round(now + usd, 6)
        box["dirty"] = True
        return usd_map[key]


def spent(ledger: Path, key: str) -> float:
    with _locked(ledger) as box:
        return float(box["data"].get("usd", {}).get(key, 0.0))


def bump_count(ledger: Path, key: str, limit: int, per_day: bool = False) -> int:
    k = f"{key}:{date.today().isoformat()}" if per_day else key
    with _locked(ledger) as box:
        counts = box["data"].setdefault("counts", {})
        n = int(counts.get(k, 0))
        if n >= limit:
            when = " today" if per_day else ""
            raise BudgetExceeded(f"Limit reached for {key}{when}: {limit}.")
        counts[k] = n + 1
        box["dirty"] = True
        return n + 1
