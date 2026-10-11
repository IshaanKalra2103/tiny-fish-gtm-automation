#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Attach an existing AgentMail inbox to a harness agent via Paperclip's native AgentMail channel.

Paperclip (>= v2026.916) receives the inbox's mail over WebSocket (no public URL needed), turns
each email thread into a task for the assigned agent, and sends only on explicit agent actions.
It vaults the org key and mints an inbox-scoped runtime key; agents never see either. Whichever
runtime the agent uses (Claude Code, Codex, ...) does the reasoning; this script only wires the
channel. Idempotent: the endpoint ID is derived from the company and inbox.

    uv run agentmail/connect_paperclip.py                  # youngmirror648@ -> orchestrator
    uv run agentmail/connect_paperclip.py --agent qa --inbox x@agentmail.to
    uv run agentmail/connect_paperclip.py --status         # show email endpoints, change nothing

Reads harness/state/integration.env (written by harness/bootstrap.py) and agentmail/.env
(AGENTMAIL_API_KEY). Prints one JSON line; never prints secrets. The inbox it attaches stops
being a throwaway: its mail becomes Paperclip tasks, so don't use it for sign-ups.
"""

import argparse
import json
import sys
import urllib.error
import urllib.request
import uuid
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
INTEGRATION_ENV = ROOT / "harness" / "state" / "integration.env"
AGENTMAIL_ENV = ROOT / "agentmail" / ".env"
DEFAULT_INBOX = "youngmirror648@agentmail.to"


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
        "inbox": endpoint.get("address") or endpoint.get("botExternalId"),
        "status": endpoint.get("status"),
        "assignedAgentId": endpoint.get("assignedAgentId"),
        "receiveMode": endpoint.get("receiveMode"),
        "lastError": endpoint.get("lastError"),
    }


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--agent", default="orchestrator", help="org.yaml agent key (default: orchestrator)")
    parser.add_argument("--inbox", default=DEFAULT_INBOX, help=f"existing AgentMail inbox (default: {DEFAULT_INBOX})")
    parser.add_argument("--status", action="store_true", help="only report email endpoints")
    args = parser.parse_args()

    harness = read_env(INTEGRATION_ENV)
    pc = Paperclip(harness["PAPERCLIP_API_URL"], harness["PAPERCLIP_BOARD_API_KEY"])
    company_id = harness["PAPERCLIP_COMPANY_ID"]

    endpoints = pc.call("GET", f"/companies/{company_id}/email/inboxes") or []
    if args.status:
        print(json.dumps({"ok": True, "endpoints": [summary(e) for e in endpoints]}))
        return

    agent_id = harness.get(f"PAPERCLIP_AGENT_{args.agent.upper()}")
    if not agent_id:
        fail(f"no PAPERCLIP_AGENT_{args.agent.upper()} in integration.env; rerun harness bootstrap")
    api_key = read_env(AGENTMAIL_ENV).get("AGENTMAIL_API_KEY")
    if not api_key:
        fail("no AGENTMAIL_API_KEY in agentmail/.env")

    endpoint = pc.call("POST", f"/companies/{company_id}/email/inboxes", {
        "assignedAgentId": agent_id,
        "apiKey": api_key,
        "inboxId": args.inbox,
        "receiveMode": "websocket",
        "idempotencyKey": str(uuid.uuid5(uuid.NAMESPACE_URL, f"paperclip-agentmail:{company_id}:{args.inbox}")),
    })
    public_url = harness["PAPERCLIP_API_URL"].removesuffix("/api")
    print(json.dumps({
        "ok": True, "agent": args.agent, **summary(endpoint),
        "settings": f"{public_url}/apps/chat/{endpoint.get('id')}/settings",
    }))


if __name__ == "__main__":
    main()
