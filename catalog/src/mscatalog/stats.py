"""Stats: counts per stage, approved tools per job and type, and flags for thin coverage."""
from . import store


def render() -> str:
    needs = store.load_needs()
    cands = store.load_json(store.candidates_path()) if store.candidates_path().exists() else []
    pages = list(store.pages_dir().glob("*.json")) if store.pages_dir().exists() else []
    recs = store.records()
    tools = [r["tool"] for r in recs if r.get("tool")]
    by = lambda s: [t for t in tools if t["status"] == s]  # noqa: E731
    approved = by("approved")
    lines = [f"candidates {len(cands)}  read {len(pages)}  extracted {len(recs)} (tools {sum(1 for r in recs if r.get('is_tool'))})  "
             f"vetted {len(tools)}  approved {len(approved)}  rejected {len(by('rejected'))}  pending {len(by('pending'))}",
             f"badges (vetted): " + ", ".join(f"{b} {sum(1 for t in tools if t['trust']['badge'] == b)}" for b in ("verified", "caution", "unknown")),
             f"sim_test filled: {sum(1 for t in tools if t.get('sim_test'))}"]
    ids = [t["id"] for t in tools]
    dupes = sorted({i for i in ids if ids.count(i) > 1})
    lines += [f"duplicate ids: {', '.join(dupes)}" if dupes else "duplicate ids: none", ""]
    lines.append("tools per job (approved / vetted, any type):")
    for n in needs["needs"]:
        lines.append(f"  {n['id']:15} {sum(1 for t in approved if n['id'] in t['need_ids']):>3} / {sum(1 for t in tools if n['id'] in t['need_ids']):<3}")
    lines.append("tools per type (approved / vetted):")
    for bt in needs["type_needs"]:
        lines.append(f"  {bt:15} {sum(1 for t in approved if bt in t['business_types']):>3} / {sum(1 for t in tools if bt in t['business_types']):<3}")
    lines.append("type x default job (approved / vetted, same type):")
    flags = []
    for bt, jobs in needs["type_needs"].items():
        cells = []
        for j in jobs:
            a = sum(1 for t in approved if j in t["need_ids"] and (bt == "other" or bt in t["business_types"]))
            v = sum(1 for t in tools if j in t["need_ids"] and (bt == "other" or bt in t["business_types"]))
            cells.append(f"{j} {a}/{v}")
            if a < 2:
                flags.append(f"{bt}/{j} ({a} approved, {v} vetted)")
        lines.append(f"  {bt:15} " + "  ".join(cells))
    lines.append("")
    lines.append(f"FLAGS: {len(flags)} type/job pairs with fewer than 2 approved tools" + (":" if flags else ""))
    lines += [f"  {f}" for f in flags]
    return "\n".join(lines)
