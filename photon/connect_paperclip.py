#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Bind the Photon iMessage project to a harness agent via Paperclip's native chat channel.

Paperclip (>= v2026.916) ships an experimental `imessage-photon` chat provider: it streams
iMessages over gRPC (no public URL needed), turns each conversation into a task for the bound
agent, and sends the agent's replies back to the thread. Whichever runtime the agent uses
(Claude Code, Codex, ...) is the brain; this script only wires the channel. Idempotent.

    uv run photon/connect_paperclip.py                 # bind to the orchestrator
    uv run photon/connect_paperclip.py --agent qa      # bind to another org.yaml agent key
    uv run photon/connect_paperclip.py --status        # show the endpoint, change nothing

Reads harness/state/integration.env (written by harness/bootstrap.py) and photon/.env
(PROJECT_ID / PROJECT_SECRET from create-spectrum-project). Prints one JSON line; never
prints secrets. The Photon secret goes only to Paperclip, which stores it in its vault.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_ENV = ROOT / "harness" / "state" / "integration.env"
PHOTON_ENV = ROOT / "photon" / ".env"
PROVIDER = "imessage-photon"

# Applies to whichever agent/runtime is bound; keeps replies human-sized on a phone.
COMMUNICATION_INSTRUCTIONS = """\
You're talking with the founder and marketing team over iMessage. Text like a person: short, \
casual, plain text. No markdown, headings or bullet lists. Keep each message to one or two \
sentences, and split longer answers into a few short texts. Lead with the answer or the next \
action. For anything that changes work (a new campaign, approvals, publishing), confirm what \
you'll do in one line, then do it through Paperclip tasks. Never publish without an approved \
board approval. If someone sincerely asks whether you're a human, say you're the AI GTM agent."""


def read_env(path: Path) -> dict[str, str]:
    if not path.exists():
        fail(f"missing {path.relative_to(ROOT)}")
    env = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            key, _, value = line.partition("=")
            env[key.strip()] = value.strip().strip('"').strip("'")
    return env


def fail(error: str, **extra) -> None:
    print(json.dumps({"ok": False, "error": error, **extra}))
    sys.exit(1)


class Paperclip:
    def __init__(self, api_url: str, token: str):
        self.base = api_url.rstrip("/")
        self.token = token

    def call(self, method: str, path: str, body=None):
        data = json.dumps(body).encode() if body is not None else None
        req = urllib.request.Request(self.base + path, data=data, method=method, headers={
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        })
        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                raw = resp.read()
                return json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            fail(f"{method} {path} -> HTTP {e.code}", detail=e.read().decode(errors="replace")[:500])
        except urllib.error.URLError as e:
            fail(f"Paperclip unreachable at {self.base}: {e.reason}")


def summary(endpoint: dict) -> dict:
    return {
        "endpointId": endpoint.get("id"),
        "status": endpoint.get("status"),
        "setupStep": (endpoint.get("setup") or {}).get("step"),
        "allocation": endpoint.get("photonAllocation"),
        "assignedAgentId": endpoint.get("assignedAgentId"),
        "health": endpoint.get("healthMessage"),
        "lastError": endpoint.get("lastError"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", default="orchestrator", help="org.yaml agent key to bind (default: orchestrator)")
    parser.add_argument("--status", action="store_true", help="only report the current endpoint")
    parser.add_argument("--reconnect", action="store_true", help="re-send Photon credentials to an existing endpoint")
    args = parser.parse_args()

    harness = read_env(INTEGRATION_ENV)
    pc = Paperclip(harness["PAPERCLIP_API_URL"], harness["PAPERCLIP_BOARD_API_KEY"])
    company_id = harness["PAPERCLIP_COMPANY_ID"]

    existing = [e for e in pc.call("GET", f"/companies/{company_id}/chat-endpoints") or []
                if e.get("provider") == PROVIDER]
    if args.status:
        print(json.dumps({"ok": True, "endpoints": [summary(e) for e in existing]}))
        return

    agent_id = harness.get(f"PAPERCLIP_AGENT_{args.agent.upper()}")
    if not agent_id:
        fail(f"no PAPERCLIP_AGENT_{args.agent.upper()} in integration.env; rerun harness bootstrap")
    photon = read_env(PHOTON_ENV)
    project = {"projectId": photon["PROJECT_ID"], "projectSecret": photon["PROJECT_SECRET"]}

    pc.call("PATCH", "/instance/settings/experimental", {"enableChatConnectors": True})

    endpoint = next((e for e in existing if e.get("assignedAgentId") == agent_id), None)
    if endpoint is None:
        endpoint = pc.call("POST", f"/companies/{company_id}/chat-endpoints", {
            "provider": PROVIDER, "assignedAgentId": agent_id, "name": "iMessage (Photon)",
        })
    eid = endpoint["id"]

    if endpoint.get("status") != "active" or args.reconnect:
        inspection = pc.call("POST", f"/chat-endpoints/{eid}/photon/inspect", project)
        if not inspection.get("eligible"):
            fail("Photon project is not eligible for this channel", allocation=inspection.get("allocation"),
                 lines=[{k: line.get(k) for k in ("lineId", "eligible", "unavailableReason")}
                        for line in inspection.get("lines", [])])
        photon_config = ({"allocation": "shared", "projectId": project["projectId"]}
                         if inspection.get("allocation") == "shared" else
                         {"allocation": "dedicated", "projectId": project["projectId"],
                          "lineId": next(line["lineId"] for line in inspection["lines"] if line.get("eligible"))})
        pc.call("POST", f"/chat-endpoints/{eid}/setup", {
            "action": "reconnect" if args.reconnect else "configure",
            "credentials": {"projectSecret": project["projectSecret"]},
            "photon": photon_config,
        })

    pc.call("PATCH", f"/chat-endpoints/{eid}", {
        "communicationInstructions": COMMUNICATION_INSTRUCTIONS,
        "allowDirectMessages": True,
    })
    endpoint = pc.call("GET", f"/chat-endpoints/{eid}")
    if (endpoint.get("setup") or {}).get("step") not in ("test", "complete"):
        pc.call("POST", f"/chat-endpoints/{eid}/setup", {"action": "verify"})
        endpoint = pc.call("GET", f"/chat-endpoints/{eid}")

    public_url = harness["PAPERCLIP_API_URL"].removesuffix("/api")
    print(json.dumps({
        "ok": True, "agent": args.agent, **summary(endpoint),
        "next": f"Text the Photon line, confirm your identity from the link you get back, then finish setup at "
                f"{public_url}/apps/chat/{eid}/settings",
    }))


if __name__ == "__main__":
    main()
