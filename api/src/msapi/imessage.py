"""iMessage: the relay posts {from_hash, text}; we run a turn and hand back at most 3 texts plus the page link."""
import re
import time
from datetime import date

from .settings import Settings
from .turns import LimitReached, TurnManager
from .workspaces import Workspaces

MAX_TEXTS = 3


class RateLimited(Exception):
    pass


def split_texts(reply: str, link: str) -> list[str]:
    parts = [p.replace(link, "").strip() for p in re.split(r"\n\s*\n", reply or "")]
    parts = [p for p in parts if p]
    if len(parts) > MAX_TEXTS:
        parts = parts[: MAX_TEXTS - 1] + ["\n\n".join(parts[MAX_TEXTS - 1:])]
    return parts or ["Done. Everything is on your page."]


class IMessage:
    def __init__(self, ws: Workspaces, turns: TurnManager, settings: Settings):
        self.ws, self.turns, self.s = ws, turns, settings
        self.min_gap = settings.imessage_min_gap
        self.per_day = settings.imessage_per_day
        self.wait_s = settings.imessage_wait
        self.last: dict[str, float] = {}
        self.counts: dict[tuple[str, str], int] = {}

    async def handle(self, from_hash: str, text: str) -> dict:
        now = time.monotonic()
        if from_hash in self.last and now - self.last[from_hash] < self.min_gap:
            raise RateLimited("Give me a few seconds between texts.")
        key = (from_hash, date.today().isoformat())
        if self.counts.get(key, 0) >= self.per_day:
            raise RateLimited("That's all for today, try again tomorrow.")
        self.last[from_hash] = now
        self.counts[key] = self.counts.get(key, 0) + 1
        oid = self.ws.owner_for_phone(from_hash)
        link = f"{self.s.web_url}/b/{oid}"
        try:
            tid = self.turns.start(oid, text, "imessage")
        except LimitReached as e:  # busy owner, full queue, daily cap: the relay texts the detail back
            raise RateLimited(str(e))
        ev = await self.turns.wait(tid, self.wait_s)
        if ev is None:
            replies = ["Still working on that. I'll put everything on your page."]
        elif ev["type"] == "error":
            replies = ["Something went wrong on my side. Try again in a minute."]
        else:
            replies = split_texts(ev["reply"], link)
        return {"replies": replies, "link": link}
