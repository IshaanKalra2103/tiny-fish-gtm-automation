# /// script
# requires-python = ">=3.11"
# dependencies = ["pyyaml>=6"]
# ///
"""Bootstrap the GTM company inside a running Paperclip (idempotent; safe to re-run).

    uv run harness/bootstrap.py            # uses http://localhost:3100

1. Claims the fresh instance with a local admin (credentials saved to harness/state/admin.json)
2. Mints a non-expiring board API key            -> harness/state/board.json
3. Creates/updates company, goal, project, and the agents from harness/org.yaml
4. Writes harness/state/integration.env for other services (Photon bridge, app/ dashboard)
"""

from __future__ import annotations

import http.cookiejar
import json
import os
import secrets
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
STATE = HERE / "state"
PUBLIC_URL = os.environ.get("PAPERCLIP_PUBLIC_URL", "http://localhost:3100").rstrip("/")
API = PUBLIC_URL + "/api"
CEO_MODEL = os.environ.get("GTM_CEO_MODEL", "claude-opus-5-5")


class Http:
    def __init__(self, token: str | None = None):
        self.token = token
        self.jar = http.cookiejar.CookieJar()
        self.opener = urllib.request.build_opener(urllib.request.HTTPCookieProcessor(self.jar))

    def call(self, method: str, path: str, body=None, ok=(200, 201, 202, 204)):
        headers = {"Accept": "application/json", "Origin": PUBLIC_URL}
        if self.token:
            headers["Authorization"] = f"Bearer {self.token}"
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(API + path, data=data, method=method, headers=headers)
        try:
            with self.opener.open(req, timeout=60) as r:
                status, raw = r.status, r.read()
        except urllib.error.HTTPError as e:
            status, raw = e.code, e.read()
        parsed = None
        if raw:
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = raw.decode(errors="replace")
        if status not in ok:
            raise RuntimeError(f"{method} {path} -> {status}: {str(parsed)[:600]}")
        return parsed


def log(msg: str) -> None:
    print(f"[bootstrap] {msg}", flush=True)


def load_json(p: Path) -> dict:
    return json.loads(p.read_text()) if p.exists() else {}


def save_json(p: Path, data: dict) -> None:
    STATE.mkdir(exist_ok=True)
    p.write_text(json.dumps(data, indent=2) + "\n")
    p.chmod(0o600)


def wait_healthy(timeout=180) -> dict:
    deadline = time.time() + timeout
    while True:
        try:
            return Http().call("GET", "/health")
        except Exception as e:  # noqa: BLE001
            if time.time() > deadline:
                sys.exit(f"Paperclip not healthy at {API}/health: {e}")
            time.sleep(2)


# ── auth ────────────────────────────────────────────────────────────────
def board_client() -> Http:
    board_file = STATE / "board.json"
    saved = load_json(board_file)
    if saved.get("token"):
        h = Http(saved["token"])
        try:
            h.call("GET", "/companies")
            log("reusing board API key from state/board.json")
            return h
        except RuntimeError:
            log("saved board key rejected; minting a new one")

    admin_file = STATE / "admin.json"
    admin = load_json(admin_file) or {
        "name": "GTM Admin",
        "email": os.environ.get("PAPERCLIP_ADMIN_EMAIL", "admin@gtm-harness.local"),
        "password": os.environ.get("PAPERCLIP_ADMIN_PASSWORD", secrets.token_urlsafe(18)),
    }
    save_json(admin_file, admin)

    s = Http()
    try:
        s.call("POST", "/auth/sign-up/email", admin)
        log(f"signed up {admin['email']}")
    except RuntimeError:
        s.call("POST", "/auth/sign-in/email", {"email": admin["email"], "password": admin["password"]})
        log(f"signed in {admin['email']}")

    health = s.call("GET", "/health")
    if health.get("bootstrapStatus") == "bootstrap_pending":
        s.call("POST", "/bootstrap/claim", {})
        log("claimed instance: admin is now instance_admin")

    key = s.call("POST", "/board-api-keys", {"name": "gtm-harness-bootstrap", "expiresAt": None})
    save_json(board_file, {"id": key["id"], "token": key["token"], "user": admin["email"]})
    log("minted board API key -> state/board.json")
    return Http(key["token"])


# ── instructions ────────────────────────────────────────────────────────
def ceo_instructions(org: dict, agents: list[dict]) -> str:
    roster = "\n".join(
        f"- **{a['name']}** ({a['title']}): {' '.join(a['capabilities'].split())}"
        for a in agents if a["key"] != "orchestrator"
    )
    ceo = next(a for a in agents if a["key"] == "orchestrator")
    return f"""# {ceo['name']}: {org['company']['name']}

You are the CEO / campaign orchestrator of an AI GTM automation company that runs on Paperclip.
Company goal: {' '.join(org['company']['goal'].split())}
You may be running on Claude Code or on Codex. Everything below works with either; use your
shell and the Paperclip API (env: PAPERCLIP_API_URL, PAPERCLIP_API_KEY, PAPERCLIP_RUN_ID).

## Your job
Campaign requests come from the board (the founder / marketing team): a Paperclip issue, or a chat
task from iMessage. Each request carries the **product context** (website, docs, audience, goals, brand
voice, competitors) and the **campaign settings** (platforms, budget/cadence, themes, approval
preferences). Ask for anything missing in one short question; otherwise default to TinyFish
(https://tinyfish.ai, niche "AI web agents / browser automation").

To run a campaign, create the stage tree (this is what `harness/campaign.py new` does):
1. A campaign issue whose description starts with the lines `brand_url: <url>`, `niche: <niche>`, `platforms: <list>`.
2. Seven child issues (`POST /api/companies/$PAPERCLIP_COMPANY_ID/issues` with `parentId`), assigned in order
   to the specialists below and chained with `blockedByIssueIds` (each blocked by the previous one):
{ceo['pipeline']}
   Paperclip wakes each specialist when its blocker is done. QA runs its own revise loop.
3. Never publish anything yourself. The Publishing Agent files a `request_board_approval`; only the
   board approves it (guardrail: explicit authorization before publishing).
4. Keep spend inside budgets. If a stage ends `blocked`, tell the board what is needed.
5. Report progress: post a short plan comment, and summarize the outcome when Analytics & Learning finishes
   (campaign status: `GET /api/companies/$PAPERCLIP_COMPANY_ID/issues?parentId=<campaign-id>`).

## When the task comes from iMessage (Photon chat channel)
When a task comes from the iMessage (Photon) chat channel you're talking with the founder and marketing
team on their phone. Text like a person: short, casual, plain text. No markdown, headings or bullet lists.
Keep each message to one or two sentences, and split longer answers into a few short texts. Lead with the
answer or the next action. For anything that changes work (a new campaign, approvals, publishing), confirm
what you'll do in one line, then do it through Paperclip tasks. Never publish without an approved board
approval. If someone sincerely asks whether you're a human, say you're the AI GTM agent.

## Your team (agent names to assign)
{roster}

## Shared memory
{org['shared_memory']}
## Tools you can run directly (bash, inside the harness container)
{org.get('tools', '')}
Always leave a comment on the issue you worked on.
"""


# ── main ────────────────────────────────────────────────────────────────
def main() -> None:
    org = yaml.safe_load((HERE / "org.yaml").read_text())
    defaults = org.get("defaults", {})
    health = wait_healthy()
    log(f"Paperclip healthy: version={health.get('version')} mode={health.get('deploymentMode')} "
        f"bootstrap={health.get('bootstrapStatus')}")

    h = board_client()

    # company
    c = org["company"]
    companies = h.call("GET", "/companies")
    company = next((x for x in companies if x["name"] == c["name"]), None)
    if company is None:
        company = h.call("POST", "/companies", {
            "name": c["name"], "description": " ".join(c["description"].split()),
            "budgetMonthlyCents": c["budget_monthly_cents"],
        })
        log(f"created company {company['name']} ({company['id']})")
    else:
        log(f"company exists: {company['name']} ({company['id']})")
    cid = company["id"]
    h.call("PATCH", f"/companies/{cid}/budgets", {"budgetMonthlyCents": c["budget_monthly_cents"]})

    # agents (CEO first so others can report to it)
    existing = {a["name"]: a for a in h.call("GET", f"/companies/{cid}/agents")
                if a.get("status") != "terminated"}
    agents = org["agents"]
    ids: dict[str, str] = {}
    for spec in sorted(agents, key=lambda a: a.get("reports_to") is not None):
        body = {
            "name": spec["name"],
            "title": spec["title"],
            "role": spec["role"],
            "capabilities": " ".join(spec["capabilities"].split()),
            "runtimeConfig": {"heartbeat": {
                "enabled": False, "intervalSec": 0, "wakeOnDemand": True, "maxConcurrentRuns": 1,
            }},
            "metadata": {"gtmKey": spec["key"], "managedBy": "harness/bootstrap.py"},
        }
        if spec.get("reports_to"):
            body["reportsTo"] = ids[spec["reports_to"]]
        adapter = spec.get("adapter", "process")
        if adapter == "claude_local":
            body["adapterType"] = "claude_local"
            body["adapterConfig"] = {
                "model": spec.get("model", CEO_MODEL), "cwd": "/workspace", "maxTurnsPerRun": 80,
                "dangerouslySkipPermissions": True, "timeoutSec": 1800,
            }
        elif adapter == "codex_local":
            body["adapterType"] = "codex_local"
            body["adapterConfig"] = {
                "cwd": "/workspace", "timeoutSec": 1800, "dangerouslyBypassApprovalsAndSandbox": True,
                **({"model": spec["model"]} if spec.get("model") else {}),
            }
        else:
            p = defaults["process"]
            body["adapterType"] = "process"
            body["adapterConfig"] = {
                "command": p["command"], "args": ["run", "gtm", "agent", spec["key"]],
                "cwd": p["cwd"], "timeoutSec": p["timeout_sec"],
            }
        if spec["key"] == "orchestrator":
            body["permissions"] = {"canCreateAgents": False}

        llm = adapter in ("claude_local", "codex_local")
        instructions = ceo_instructions(org, agents) if spec["key"] == "orchestrator" else None
        cur = existing.get(spec["name"])
        if cur is None:
            if llm and instructions:
                body["instructionsBundle"] = {"files": {"AGENTS.md": instructions}}
            cur = h.call("POST", f"/companies/{cid}/agents", body)
            log(f"created agent {spec['name']} [{adapter}] ({cur['id']})")
        else:
            patch = {k: v for k, v in body.items() if k != "permissions"}  # create-only field
            patch["replaceAdapterConfig"] = True
            if cur.get("adapterType") != adapter:
                patch["adapterType"] = adapter
            cur = h.call("PATCH", f"/agents/{cur['id']}", patch)
            if llm and instructions:
                try:
                    old = h.call("GET", f"/agents/{cur['id']}/instructions-bundle/file?path=AGENTS.md")
                except RuntimeError:
                    old = None
                if not old or old.get("content") != instructions:
                    h.call("PUT", f"/agents/{cur['id']}/instructions-bundle/file", {
                        "path": "AGENTS.md", "content": instructions,
                        "baseRevisionId": (old or {}).get("revision", {}).get("id"),
                    })
                    log(f"updated {spec['name']} AGENTS.md")
            log(f"updated agent {spec['name']} [{adapter}]")
        ids[spec["key"]] = cur["id"]
        budget = spec.get("budget_monthly_cents", defaults.get("budget_monthly_cents", 0))
        h.call("PATCH", f"/agents/{cur['id']}/budgets", {"budgetMonthlyCents": budget})

    # goal + project
    goals = h.call("GET", f"/companies/{cid}/goals")
    goal_title = "Publish-ready launch content from live trends"
    goal = next((g for g in goals if g["title"] == goal_title), None) or h.call(
        "POST", f"/companies/{cid}/goals", {
            "title": goal_title, "description": " ".join(c["goal"].split()),
            "level": "company", "status": "active", "ownerAgentId": ids["orchestrator"],
        })
    projects = h.call("GET", f"/companies/{cid}/projects")
    proj_name = "GTM Campaigns"
    project = next((p for p in projects if p["name"] == proj_name), None) or h.call(
        "POST", f"/companies/{cid}/projects", {
            "name": proj_name, "description": "One issue tree per campaign (trend -> publish -> learn).",
            "goalIds": [goal["id"]], "leadAgentId": ids["orchestrator"], "status": "in_progress",
        })
    log(f"goal {goal['id']} / project {project['id']}")

    board = load_json(STATE / "board.json")
    me = h.call("GET", "/cli-auth/me")
    state = {
        "apiUrl": API, "publicUrl": PUBLIC_URL, "companyId": cid, "companyName": company["name"],
        "boardUserId": me["userId"],
        "goalId": goal["id"], "projectId": project["id"], "agents": ids,
    }
    save_json(STATE / "paperclip.json", state)
    env = (
        f"PAPERCLIP_API_URL={API}\n"
        f"PAPERCLIP_API_URL_FROM_CONTAINERS=http://host.docker.internal:3100/api\n"
        f"PAPERCLIP_BOARD_API_KEY={board['token']}\n"
        f"PAPERCLIP_COMPANY_ID={cid}\n"
        f"PAPERCLIP_BOARD_USER_ID={me['userId']}\n"
        f"PAPERCLIP_PROJECT_ID={project['id']}\n"
        f"PAPERCLIP_GOAL_ID={goal['id']}\n"
        + "".join(f"PAPERCLIP_AGENT_{k.upper()}={v}\n" for k, v in ids.items())
    )
    (STATE / "integration.env").write_text(env)
    (STATE / "integration.env").chmod(0o600)
    log("wrote state/paperclip.json and state/integration.env")
    print(json.dumps(state, indent=2))


if __name__ == "__main__":
    main()
