"""Export: approved records into catalog/catalog.json (the Task 3 shape), copied to sandbox/ and web/data/."""
import shutil
from datetime import datetime, timezone

from mstools.schemas import Tool

from . import store


def build() -> dict:
    needs = store.load_needs()
    tools = [Tool.model_validate(r["tool"]).model_dump() for r in store.records()
             if r.get("tool") and r["tool"]["status"] == "approved"]
    tools.sort(key=lambda t: (t["need_ids"][0], -t["trust"]["score"]))
    return {"version": 1, "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "needs": [{"id": n["id"], "title": n["title"], "plain": n["plain"]} for n in needs["needs"]],
            "type_needs": needs["type_needs"], "tools": tools}


def run() -> list[str]:
    cat = build()
    out = store.CATALOG_DIR / "catalog.json"
    store.save_json(out, cat)
    targets = [store.REPO / "sandbox" / "catalog.json", store.REPO / "web" / "data" / "catalog.json"]
    for t in targets:
        t.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(out, t)
    return [str(out)] + [str(t) for t in targets]
