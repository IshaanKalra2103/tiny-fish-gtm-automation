# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Install harness/skills/* into Paperclip's company skill library and attach them per org.yaml (idempotent).

    uv run harness/sync_skills.py            # create/update the skills, attach them to agents listed under `skills:`
    uv run harness/sync_skills.py --check    # read-only: print what would change

bootstrap.py calls sync() at the end of every run. It has to: Paperclip keeps an agent's desired skills in
adapterConfig.paperclipSkillSync, which bootstrap's replaceAdapterConfig PATCH clears. Skills created inline are copies, so every file is compared and
re-sent on each sync; an agent picks up changes on its next run. Only LLM agents (codex_local, claude_local) load
skills; process agents ignore them, so their behaviour stays in app/ code and the repo's own SKILL.md files.
Prints one JSON line.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
SKILLS = HERE / "skills"


def log(msg: str) -> None:
    print(f"[skills] {msg}", file=sys.stderr, flush=True)


def local_skills() -> dict[str, dict]:
    """slug -> {name, description, files: {relpath: text}} for every harness/skills/<slug>/SKILL.md."""
    out = {}
    for md in sorted(SKILLS.glob("*/SKILL.md")):
        root = md.parent
        front = re.match(r"^---\n(.*?)\n---\n", md.read_text(), re.S)
        meta = yaml.safe_load(front.group(1)) if front else {}
        files = {p.relative_to(root).as_posix(): p.read_text() for p in sorted(root.rglob("*"))
                 if p.is_file() and not p.name.startswith(".") and "__pycache__" not in p.parts}
        out[root.name] = {"name": meta.get("name", root.name), "description": " ".join(str(meta.get("description", "")).split()),
                          "files": files}
    return out


def sync(call, cid: str, agent_ids: dict[str, str], org: dict, check: bool = False) -> dict:
    """call(method, path, body=None, ok=...) is bootstrap's Http.call (board token)."""
    mine = local_skills()
    remote = {s["slug"]: s for s in call("GET", f"/companies/{cid}/skills") or []}
    report = {"created": [], "updated": [], "attached": {}, "check": check}

    for slug, skill in mine.items():
        cur = remote.get(slug)
        if cur is not None and not cur.get("editable", True):
            raise RuntimeError(f"skill slug {slug!r} is taken by a read-only skill ({cur.get('key')})")
        if cur is None:
            report["created"].append(slug)
            if check:
                continue
            cur = call("POST", f"/companies/{cid}/skills", {
                "name": skill["name"], "slug": slug, "description": skill["description"],
                "markdown": skill["files"]["SKILL.md"],
            })
            remote[slug] = cur
            log(f"created {slug} ({cur.get('key')})")
        elif cur.get("description") != skill["description"] and not check:
            call("PATCH", f"/companies/{cid}/skills/{cur['id']}", {"description": skill["description"]})
        for path, text in skill["files"].items():
            have = call("GET", f"/companies/{cid}/skills/{cur['id']}/files?path={path}", ok=(200, 404))
            if isinstance(have, dict) and have.get("content") == text:
                continue
            report["updated"].append(f"{slug}/{path}")
            if not check:
                call("PATCH", f"/companies/{cid}/skills/{cur['id']}/files", {"path": path, "content": text})
                log(f"updated {slug}/{path}")

    for spec in org.get("agents", []):
        wanted = spec.get("skills") or []
        if not wanted or spec["key"] not in agent_ids:
            continue
        unknown = [s for s in wanted if s not in remote]
        if unknown and not check:
            raise RuntimeError(f"{spec['name']}: unknown skills {unknown} (add harness/skills/<slug>/SKILL.md)")
        agent_id = agent_ids[spec["key"]]
        have = set((call("GET", f"/agents/{agent_id}/skills") or {}).get("desiredSkills") or [])
        missing = [remote[s]["key"] if s in remote else s for s in wanted
                   if s not in remote or remote[s]["key"] not in have]
        if not missing:
            continue
        report["attached"][spec["key"]] = missing
        if not check:
            # "add" keeps the Paperclip core skills; "replace" would drop them.
            call("POST", f"/agents/{agent_id}/skills/sync", {"mode": "add", "desiredSkills": missing})
            log(f"attached {missing} to {spec['name']}")
    return report


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--check", action="store_true", help="read-only; report what would change")
    a = p.parse_args()
    try:
        state = json.loads((HERE / "state" / "paperclip.json").read_text())
        token = json.loads((HERE / "state" / "board.json").read_text())["token"]
    except FileNotFoundError:
        sys.exit(json.dumps({"ok": False, "error": "harness not bootstrapped; run uv run harness/bootstrap.py"}))

    def call(method: str, path: str, body=None, ok=(200, 201, 202, 204)):
        req = urllib.request.Request(
            state["apiUrl"] + path, method=method, data=json.dumps(body).encode() if body is not None else None,
            headers={"Authorization": f"Bearer {token}", "Accept": "application/json", "Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=60) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        if status not in ok:
            raise RuntimeError(f"{method} {path} -> {status}: {raw.decode(errors='replace')[:400]}")
        return json.loads(raw) if raw and status < 400 else None

    try:
        org = yaml.safe_load((HERE / "org.yaml").read_text())
        report = sync(call, state["companyId"], state["agents"], org, check=a.check)
    except (RuntimeError, OSError) as e:  # OSError covers URLError and a dropped connection (server restarting)
        print(json.dumps({"ok": False, "error": f"{type(e).__name__}: {e}"}))
        raise SystemExit(1)
    print(json.dumps({"ok": True, **report}))


if __name__ == "__main__":
    main()
