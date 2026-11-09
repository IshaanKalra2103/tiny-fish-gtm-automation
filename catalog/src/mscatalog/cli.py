"""mscatalog: run (discover -> read -> extract -> vet -> simtest), review, export, stats, report."""
import argparse
import time
from concurrent.futures import ThreadPoolExecutor

from . import discover, export, extract, read, review, simtest, stats, store, vet
from .queries import query_grid, query_meta

CLAUDE_WORKERS = 5
NET_WORKERS = 4


def _log(msg: str, t0: float) -> None:
    print(f"[{time.monotonic() - t0:6.0f}s] {msg}", flush=True)


def _pool(fn, items, workers, label, t0):
    done = 0
    out = []
    with ThreadPoolExecutor(workers) as ex:
        for r in ex.map(fn, items):
            done += 1
            out.append(r)
            if done % 10 == 0 or done == len(items):
                _log(f"{label}: {done}/{len(items)}", t0)
    return out


def cmd_run(a) -> None:
    t0 = time.monotonic()
    needs = store.load_needs()
    if a.rediscover or not store.candidates_path().exists():
        qs = query_grid(needs)
        _log(f"discover: {len(qs)} queries", t0)
        cands = discover.run(qs, meta=query_meta(needs), fetch_links=read.links_only)
        store.save_json(store.candidates_path(), [c.to_dict() for c in cands])
        _log(f"discover: {len(cands)} candidate domains", t0)
    cands = [discover.Candidate(**c) for c in store.load_json(store.candidates_path())]
    chosen = discover.select(cands, a.limit, needs.get("seeds"))
    _log(f"selected {len(chosen)} candidates (limit {a.limit})", t0)

    def need_read(c):
        p = store.pages_dir() / f"{c.domain}.json"
        return a.force or not p.exists() or not store.load_json(p).get("ok")

    _pool(lambda c: read.run(c), [c for c in chosen if need_read(c)], NET_WORKERS, "read", t0)

    def need_extract(c):
        p = store.records_dir() / f"{c.domain}.json"
        if not (store.pages_dir() / f"{c.domain}.json").exists():
            return False
        if a.force or not p.exists():
            return True
        reason = store.load_json(p).get("reason", "")  # retry reads that failed, never redo a judged record
        return reason == "no pages could be read" or reason.startswith(("extraction failed", "invalid extraction"))

    _pool(lambda c: extract.run(c.domain), [c for c in chosen if need_extract(c)], CLAUDE_WORKERS, "extract", t0)

    def rec(c):
        p = store.records_dir() / f"{c.domain}.json"
        return store.load_json(p) if p.exists() else {}

    to_vet = [c for c in chosen if rec(c).get("is_tool") and (a.force or a.revet or not rec(c).get("tool"))]
    _pool(lambda c: vet.run(c.domain), to_vet, NET_WORKERS, "vet", t0)

    to_sim = [c for c in chosen if (r := rec(c)).get("tool") and simtest.eligible(r) and (a.force or not r["tool"].get("sim_test"))]
    _pool(lambda c: simtest.run(c.domain), to_sim, CLAUDE_WORKERS, "simtest", t0)
    _log("run done", t0)
    print(stats.render())


def main() -> None:
    p = argparse.ArgumentParser(prog="mscatalog", description="Discover, vet, review and export the MainStreet AI tool catalog.")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run", help="discover -> read -> extract -> vet -> simtest (skips work already on disk)")
    r.add_argument("--limit", type=int, default=80, help="candidate domains to read and extract")
    r.add_argument("--rediscover", action="store_true", help="run the search grid again")
    r.add_argument("--force", action="store_true", help="redo stages even when their files exist")
    r.add_argument("--revet", action="store_true", help="recompute trust signals for every extracted tool (keeps review decisions)")
    rv = sub.add_parser("review", help="approve or reject pending records (interactive without flags)")
    rv.add_argument("--approve", default="", help="comma-separated tool ids")
    rv.add_argument("--reject", default="", help="comma-separated tool ids")
    rv.add_argument("--agent-setup", dest="agent_setup", default="", help="comma-separated tool ids to allow agent setup")
    sub.add_parser("export", help="write approved tools to catalog/catalog.json, sandbox/ and web/data/")
    sub.add_parser("stats", help="pipeline counts and approved coverage")
    rp = sub.add_parser("report", help="write the human review sheet (docs/catalog-review.md)")
    rp.add_argument("--out", default=str(store.REPO / "docs" / "catalog-review.md"))
    a = p.parse_args()

    if a.cmd == "run":
        cmd_run(a)
    elif a.cmd == "review":
        ids = {k: [x.strip() for x in getattr(a, k).split(",") if x.strip()] for k in ("approve", "reject", "agent_setup")}
        who = review.reviewer_name()
        if any(ids.values()):
            for line in review.apply(ids["approve"], ids["reject"], ids["agent_setup"], who):
                print(line)
        else:
            review.interactive(who)
    elif a.cmd == "export":
        for path in export.run():
            print(f"wrote {path}")
    elif a.cmd == "stats":
        print(stats.render())
    elif a.cmd == "report":
        from . import report
        print(f"wrote {report.write(a.out)}")


if __name__ == "__main__":
    main()
