"""Review: a human approves or rejects each pending record. Interactive loop, or --approve/--reject/--agent-setup ids."""
import os
from datetime import datetime, timezone

from mstools.schemas import Signal
from mstools.trust import score_signals

from . import store


def _find(rid: str) -> tuple:
    for p in sorted(store.records_dir().glob("*.json")):
        rec = store.load_json(p)
        t = rec.get("tool")
        if t and (t["id"] == rid or rec["domain"] == rid):
            return p, rec
    raise SystemExit(f"No vetted record with id '{rid}'.")


def _rescore(tool: dict, human_approved: bool) -> None:
    sig = {k: Signal.model_validate(v) for k, v in tool["trust"]["signals"].items()}
    tool["trust"] = score_signals(sig, human_approved=human_approved).model_dump()


def decide(rec: dict, action: str, reviewer: str) -> dict:
    tool = rec["tool"]
    if action == "agent-setup":
        tool["setup"]["agent_setup"] = True
        tool["setup"]["playbook"] = tool["setup"].get("playbook") or f"setup-{tool['id']}"
        return rec
    tool["status"] = {"approve": "approved", "reject": "rejected"}[action]
    tool["reviewed_by"] = reviewer
    tool["reviewed_at"] = datetime.now(timezone.utc).isoformat(timespec="seconds")
    _rescore(tool, human_approved=action == "approve")
    return rec


def apply(approve: list[str], reject: list[str], agent_setup: list[str], reviewer: str) -> list[str]:
    done = []
    for action, ids in (("approve", approve), ("reject", reject), ("agent-setup", agent_setup)):
        for rid in ids:
            path, rec = _find(rid)
            store.save_json(path, decide(rec, action, reviewer))
            t = rec["tool"]
            done.append(f"{action}: {t['id']} -> status {t['status']}, badge {t['trust']['badge']}, "
                        f"score {t['trust']['score']}, agent_setup {t['setup']['agent_setup']}")
    return done


def show(rec: dict) -> str:
    t = rec["tool"]
    p = t["price"]
    price = ("free plan; " if p["free_plan"] else "") + (f"from ${p['from_usd_month']:g}/mo" if p["from_usd_month"] is not None else "no listed price")
    lines = [f"\n{t['name']} ({t['id']})  {t['url']}", f"  jobs: {', '.join(t['need_ids'])}   types: {', '.join(t['business_types'])}",
             f"  {t['what_it_does']}", f"  price: {price}  {p.get('pricing_url') or ''}",
             f"  trust: {t['trust']['score']}/100 ({t['trust']['badge']})"]
    for name, s in t["trust"]["signals"].items():
        lines.append(f"    {name:14} {s['points']:>2}/{s['max']:<2} {s['value'][:90]}  {s.get('evidence_url') or ''}")
    if t.get("sim_test"):
        st = t["sim_test"]
        lines.append(f"  simtest (simulated): {st['score']}/10 - {st['notes']}")
    return "\n".join(lines)


def interactive(reviewer: str) -> None:
    pending = [(p, r) for p in sorted(store.records_dir().glob("*.json")) if (r := store.load_json(p)).get("tool")
               and r["tool"]["status"] == "pending"]
    print(f"{len(pending)} pending records. Reviewer: {reviewer}")
    for path, rec in pending:
        print(show(rec))
        while True:
            k = input("  [a]pprove [r]eject [s]kip [x]agent-setup-on [q]uit > ").strip().lower()
            if k in ("a", "r"):
                store.save_json(path, decide(rec, "approve" if k == "a" else "reject", reviewer))
                break
            if k == "x":
                store.save_json(path, decide(rec, "agent-setup", reviewer))
                print("  agent setup on; now approve or reject.")
                continue
            if k == "s":
                break
            if k == "q":
                return


def reviewer_name() -> str:
    name = os.environ.get("MS_REVIEWER", "").strip()
    if not name:
        raise SystemExit("Set MS_REVIEWER to your name first.")
    return name
