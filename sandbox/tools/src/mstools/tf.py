"""tf: TinyFish search, fetch and agent runs for the sandbox agent, with the owner's budget enforced."""
import argparse
import json
import os
import time
from pathlib import Path

from . import config, tinyfish
from .budget import BudgetExceeded, charge, spent
from .cli import ToolError, log, run

DEFAULT_MAX_STEPS = 45
MAX_STEPS = int(config.CAPS["setup"] / config.AGENT_USD_PER_STEP)  # $1.00 per setup -> 62; spec says about 60


def _save_run(info: dict) -> None:
    d = config.work() / "runs"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{info['run_id']}.json").write_text(json.dumps(info, indent=1, default=str))


def outcome(info: dict) -> str:
    status = info["status"].upper()
    if status == "COMPLETED":
        res = info.get("result")
        if not res or (isinstance(res, dict) and (res.get("blocked") or res.get("needs_owner"))):
            return "needs_owner"
        return "done"
    if status in ("FAILED", "CANCELLED"):
        return "failed"
    return "running"


def _main(a: argparse.Namespace) -> dict:
    if a.cmd == "search":
        domains = [d.strip() for d in (a.domains or "").split(",") if d.strip()]
        return {"hits": tinyfish.search(a.query, domains or None)}
    if a.cmd == "fetch":
        docs, failed = tinyfish.fetch(a.urls)
        if failed:
            log(f"could not read: {', '.join(failed)}")
        return {"docs": docs, "failed": failed}
    if a.cmd == "agent-start":
        steps = max(1, min(a.max_steps, MAX_STEPS))
        reserve = round(steps * config.AGENT_USD_PER_STEP, 4)
        ledger, cap = config.owner_budget(), config.CAPS["tinyfish_owner"]
        if spent(ledger, "tinyfish_owner") + reserve > cap + 1e-9:
            raise ToolError("Not enough budget left for a setup run. Tell the owner and offer a local helper instead.")
        schema = json.loads(Path(a.schema).read_text()) if a.schema else None
        try:
            run_id = tinyfish.queue_agent(a.url, a.goal, schema, steps)
        except Exception as e:
            raise ToolError(f"TinyFish could not start the run: {e}")
        try:
            charge(ledger, "tinyfish_owner", reserve, cap)
        except BudgetExceeded as e:
            raise ToolError(str(e))
        _save_run({"run_id": run_id, "status": "PENDING", "url": a.url, "max_steps": steps, "reserved_usd": reserve})
        return {"run_id": run_id, "max_steps": steps, "reserved_usd": reserve,
                "next": f"tf agent-wait {run_id}"}
    # agent-wait / agent-status
    poll = float(os.environ.get("MS_POLL_SECONDS", "5"))
    deadline = time.time() + (a.timeout if a.cmd == "agent-wait" else 0)
    seen_stream = False
    while True:
        try:
            info = tinyfish.get_run(a.run_id)
        except Exception as e:
            raise ToolError(f"Could not read run {a.run_id}: {e}")
        if info.get("streaming_url") and not seen_stream:
            seen_stream = True
            _save_run(info)
            log(f"watch live: {info['streaming_url']}")
        out = outcome(info)
        if out != "running" or time.time() >= deadline:
            break
        log(f"{a.run_id}: {info['status']}")
        time.sleep(poll)
    _save_run(info)
    resp = {"status": info["status"], "outcome": out, "result": info.get("result"),
            "error": info.get("error"), "streaming_url": info.get("streaming_url")}
    if out == "running":
        resp["next"] = f"Still running. Call tf agent-wait {a.run_id} again."
    return resp


def main() -> None:
    p = argparse.ArgumentParser(prog="tf", description="TinyFish web tools.")
    sub = p.add_subparsers(dest="cmd", required=True)
    s = sub.add_parser("search")
    s.add_argument("query")
    s.add_argument("--domains")
    f = sub.add_parser("fetch")
    f.add_argument("urls", nargs="+")
    st = sub.add_parser("agent-start")
    st.add_argument("--url", required=True)
    st.add_argument("--goal", required=True)
    st.add_argument("--schema")
    st.add_argument("--max-steps", dest="max_steps", type=int, default=DEFAULT_MAX_STEPS)
    w = sub.add_parser("agent-wait")
    w.add_argument("run_id")
    w.add_argument("--timeout", type=int, default=540)
    t = sub.add_parser("agent-status")
    t.add_argument("run_id")
    run(_main, p)


if __name__ == "__main__":
    main()
