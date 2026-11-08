"""catalog: the jobs for a business type, and approved tools that match a job (spec §4.4)."""
import argparse
import json

from . import config
from .cli import ToolError, run
from .schemas import Tool
from .trust import can_agent_setup


def load_catalog() -> dict:
    path = config.catalog_path()
    if not path.exists():
        raise ToolError(f"Catalog not found at {path}.")
    return json.loads(path.read_text())


def needs_for(cat: dict, business_type: str) -> list[dict]:
    ids = cat["type_needs"].get(business_type) or cat["type_needs"]["other"]
    by_id = {n["id"]: n for n in cat["needs"]}
    return [by_id[i] for i in ids if i in by_id]


def match(cat: dict, business_type: str, need: str, works_with: list[str], limit: int = 3) -> list[dict]:
    tools = [Tool.model_validate(t) for t in cat["tools"]]
    pool = [t for t in tools if t.status == "approved" and t.trust.badge != "unknown" and need in t.need_ids]
    typed = pool if business_type == "other" else [t for t in pool if business_type in t.business_types]
    if len(typed) < 2:  # too few for a comparison: top up with tools for the same job from other types
        typed += [t for t in pool if t not in typed]
    want = set(works_with)

    def key(t: Tool):
        usd = t.price.from_usd_month
        return (-len(want & set(t.integrations)), -t.trust.score, 0 if t.price.free_plan else 1, usd if usd is not None else 1e9)

    out = []
    for t in sorted(typed, key=key)[:limit]:
        out.append({
            "id": t.id, "name": t.name, "what_it_does": t.what_it_does, "price": t.price.model_dump(),
            "setup": t.setup.model_dump(), "works_with": t.integrations,
            "trust": {"score": t.trust.score, "badge": t.trust.badge},
            "sim_test": t.sim_test.model_dump() if t.sim_test else None, "can_setup": can_agent_setup(t),
        })
    return out


def _main(a: argparse.Namespace) -> dict:
    cat = load_catalog()
    if a.cmd == "needs":
        return {"needs": needs_for(cat, a.type)}
    if a.cmd == "match":
        ww = [w.strip() for w in (a.works_with or "").split(",") if w.strip()]
        tools = match(cat, a.type, a.need, ww, a.limit)
        if not tools:
            raise ToolError(f"No approved tools for '{a.need}' yet.")
        return {"tools": tools}
    for t in cat["tools"]:
        if t["id"] == a.tool_id and t["status"] == "approved":
            return {"tool": t}
    raise ToolError(f"No approved tool with id '{a.tool_id}'.")


def main() -> None:
    p = argparse.ArgumentParser(prog="catalog", description="Look up jobs and vetted tools.")
    sub = p.add_subparsers(dest="cmd", required=True)
    n = sub.add_parser("needs")
    n.add_argument("--type", required=True)
    m = sub.add_parser("match")
    m.add_argument("--type", required=True)
    m.add_argument("--need", required=True)
    m.add_argument("--works-with", dest="works_with")
    m.add_argument("--limit", type=int, default=3)
    g = sub.add_parser("get")
    g.add_argument("tool_id")
    run(_main, p)


if __name__ == "__main__":
    main()
