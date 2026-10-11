"""Tiny stdlib-only client for Paperclip `process`-adapter agents.

Paperclip runs `uv run gtm agent <role>` (cwd /workspace/app) inside the harness
container and injects:

    PAPERCLIP_API_URL     server base URL, no /api suffix
    PAPERCLIP_API_KEY     short-lived run token (Bearer)
    PAPERCLIP_RUN_ID      heartbeat run id (send as X-Paperclip-Run-Id on mutations)
    PAPERCLIP_AGENT_ID    this agent's id
    PAPERCLIP_COMPANY_ID  company id

It does NOT inject the task/issue id for process agents, so `current_issue()`
reads it from the run context (falling back to the agent's inbox). Stdout is
never posted anywhere; an agent must comment on its issue or Paperclip re-wakes
it with `missing_issue_comment`.

Typical agent body:

    from paperclip_agent import PaperclipRun
    pc = PaperclipRun.from_env()
    issue = pc.current_issue()
    if issue is None:
        return  # nothing assigned
    pc.checkout(issue["id"])
    campaign = pc.campaign_id(issue)        # e.g. "GTM-1"; use runs/<campaign>/
    ... do the work ...
    pc.done(issue["id"], "Wrote runs/GTM-1/evidence.json (42 sources)")
"""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from typing import Any


class PaperclipError(RuntimeError):
    pass


class PaperclipRun:
    def __init__(self, api_url: str, api_key: str, run_id: str | None = None,
                 agent_id: str | None = None, company_id: str | None = None):
        self.base = api_url.rstrip("/")
        if not self.base.endswith("/api"):
            self.base += "/api"
        self.api_key = api_key
        self.run_id = run_id
        self.agent_id = agent_id
        self.company_id = company_id

    @classmethod
    def from_env(cls) -> "PaperclipRun":
        try:
            return cls(
                api_url=os.environ["PAPERCLIP_API_URL"],
                api_key=os.environ["PAPERCLIP_API_KEY"],
                run_id=os.environ.get("PAPERCLIP_RUN_ID"),
                agent_id=os.environ.get("PAPERCLIP_AGENT_ID"),
                company_id=os.environ.get("PAPERCLIP_COMPANY_ID"),
            )
        except KeyError as e:
            raise PaperclipError(f"not running under Paperclip: {e} unset") from e

    # ── HTTP ────────────────────────────────────────────────────────────
    def request(self, method: str, path: str, body: Any = None) -> Any:
        headers = {"Authorization": f"Bearer {self.api_key}", "Accept": "application/json"}
        if self.run_id:
            headers["X-Paperclip-Run-Id"] = self.run_id
        data = None
        if body is not None:
            data = json.dumps(body).encode()
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(self.base + path, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise PaperclipError(f"{method} {path} -> {e.code}: {e.read().decode(errors='replace')[:500]}") from e
        return json.loads(raw) if raw else None

    # ── Work discovery ──────────────────────────────────────────────────
    def run(self) -> dict:
        return self.request("GET", f"/heartbeat-runs/{self.run_id}")

    def wake_context(self) -> dict:
        """Why this run was woken: issueId/taskId, wakeReason, approvalId, ..."""
        if not self.run_id:
            return {}
        try:
            return self.run().get("contextSnapshot") or {}
        except PaperclipError:
            return {}

    def inbox(self) -> list[dict]:
        return self.request("GET", "/agents/me/inbox-lite")

    def issue(self, issue_id: str) -> dict:
        return self.request("GET", f"/issues/{issue_id}")

    def current_issue(self) -> dict | None:
        ctx = self.wake_context()
        issue_id = ctx.get("issueId") or ctx.get("taskId")
        if issue_id:
            return self.issue(issue_id)
        ready = [i for i in self.inbox() if i.get("dependencyReady", True)]
        return self.issue(ready[0]["id"]) if ready else None

    def campaign_issue(self, issue: dict) -> dict:
        """Walk up parentId to the top-level campaign issue."""
        seen = set()
        while issue.get("parentId") and issue["id"] not in seen:
            seen.add(issue["id"])
            issue = self.issue(issue["parentId"])
        return issue

    def campaign_id(self, issue: dict) -> str:
        """Stable id for runs/<campaign_id>/ (the root issue's identifier, e.g. GTM-1)."""
        root = self.campaign_issue(issue)
        return root.get("identifier") or root["id"]

    # ── Mutations ───────────────────────────────────────────────────────
    def checkout(self, issue_id: str) -> dict:
        return self.request("POST", f"/issues/{issue_id}/checkout", {
            "agentId": self.agent_id,
            "expectedStatuses": ["todo", "backlog", "blocked", "in_review", "in_progress"],
        })

    def comment(self, issue_id: str, body: str) -> dict:
        return self.request("POST", f"/issues/{issue_id}/comments", {"body": body})

    def set_status(self, issue_id: str, status: str, comment: str | None = None) -> dict:
        payload: dict[str, Any] = {"status": status}
        if comment:
            payload["comment"] = comment
        return self.request("PATCH", f"/issues/{issue_id}", payload)

    def done(self, issue_id: str, summary: str) -> dict:
        return self.set_status(issue_id, "done", summary)

    def blocked(self, issue_id: str, reason: str) -> dict:
        return self.set_status(issue_id, "blocked", reason)

    def create_subissue(self, parent_id: str, title: str, description: str = "",
                        assignee_agent_id: str | None = None, priority: str = "medium") -> dict:
        body: dict[str, Any] = {"title": title, "description": description, "priority": priority}
        if assignee_agent_id:
            body["assigneeAgentId"] = assignee_agent_id
        return self.request("POST", f"/issues/{parent_id}/children", body)

    def request_approval(self, issue_id: str, title: str, summary: str,
                         recommended_action: str = "Approve to publish", artifact_hash: str | None = None) -> dict:
        """Human gate (board approval). The board approves in the UI or over iMessage;
        on approve Paperclip re-wakes this agent with wakeReason=approval_approved."""
        return self.request("POST", f"/companies/{self.company_id}/approvals", {
            "type": "request_board_approval",
            "requestedByAgentId": self.agent_id,
            "issueIds": [issue_id],
            "payload": {"title": title, "summary": summary, "recommendedAction": recommended_action,
                        "artifactHash": artifact_hash},
        })

    def agents(self) -> list[dict]:
        return self.request("GET", f"/companies/{self.company_id}/agents")

    def agent_id_by_name(self, name: str) -> str | None:
        return next((a["id"] for a in self.agents() if a.get("name") == name), None)


if __name__ == "__main__":
    # Smoke test inside a Paperclip run: print the wake context and inbox.
    pc = PaperclipRun.from_env()
    print(json.dumps({"wake": pc.wake_context(), "inbox": pc.inbox()}, indent=2, default=str))
