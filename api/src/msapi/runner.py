"""One agent turn = one `claude -p` inside the owner's sandbox container, streamed as stream-json events."""
import asyncio
import json
import os
import re
import time
from collections import defaultdict
from typing import AsyncIterator, Protocol

from .settings import Settings

ALLOWED_TOOLS = "Bash(ws:*),Bash(catalog:*),Bash(tf:*),Bash(inbox:*),Bash(preview:*),Bash(approval:*),Read,Write,Edit,Skill"
DISALLOWED_TOOLS = "WebFetch,WebSearch"
PASS_ENV = ("TINYFISH_API_KEY", "OPENROUTER_API_KEY", "AGENTMAIL_API_KEY")


def clean_token(raw: str | None) -> str:
    """Keychain copies of the token picked up stray spaces and prefixes; keep only the sk-ant-oat... part."""
    t = re.sub(r"\s+", "", raw or "")
    i = t.find("sk-ant-oat")
    return t[i:] if i >= 0 else t


def token_looks_valid(raw: str | None = None) -> bool:
    t = clean_token(raw if raw is not None else os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))
    return t.startswith("sk-ant-oat") and len(t) > 80


class Runner(Protocol):
    def run(self, owner_id: str, prompt: str, session_id: str, resume: bool) -> AsyncIterator[dict]: ...


class DockerRunner:
    def __init__(self, settings: Settings):
        self.s = settings

    def env(self) -> dict:
        return {**os.environ, "CLAUDE_CODE_OAUTH_TOKEN": clean_token(os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"))}

    def name(self, owner_id: str) -> str:
        return f"ms-{owner_id}"

    def command(self, owner_id: str, prompt: str, session_id: str, resume: bool) -> list[str]:
        work = self.s.workspaces / owner_id
        # Secrets go by name only (-e NAME), so values never show up in `ps`.
        env = ["-e", "CLAUDE_CODE_OAUTH_TOKEN", "-e", "CLAUDE_CONFIG_DIR=/work/.claude-config",
               "-e", f"MS_OWNER_ID={owner_id}", *[x for k in PASS_ENV for x in ("-e", k)]]
        return ["docker", "run", "--rm", "--name", self.name(owner_id), "--label", "mainstreet=1",
                "--memory", "1g", "--cpus", "1.5", "--pids-limit", "256",
                "-v", f"{work}:/work", "-v", f"{self.s.workspaces / '_decisions' / owner_id}:/decisions:ro",
                "-v", f"{self.s.budget}:/budget", *env, self.s.image,
                "claude", "-p", prompt, "--resume" if resume else "--session-id", session_id,
                "--model", self.s.model, "--output-format", "stream-json", "--verbose",
                "--settings", "/sandbox/settings.json", "--add-dir", "/work",
                "--allowedTools", ALLOWED_TOOLS, "--disallowedTools", DISALLOWED_TOOLS]

    def session_exists(self, owner_id: str, session_id: str) -> bool:
        return any((self.s.workspaces / owner_id / ".claude-config" / "projects").glob(f"*/{session_id}.jsonl"))

    async def _rm(self, owner_id: str) -> None:
        p = await asyncio.create_subprocess_exec("docker", "rm", "-f", self.name(owner_id),
                                                 stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.DEVNULL)
        await p.wait()

    async def run(self, owner_id: str, prompt: str, session_id: str, resume: bool) -> AsyncIterator[dict]:
        self.s.budget.mkdir(parents=True, exist_ok=True)
        (self.s.workspaces / "_decisions" / owner_id).mkdir(parents=True, exist_ok=True)
        # What is on disk wins over our flag: a turn that died early may or may not have created the session.
        resume = self.session_exists(owner_id, session_id)
        await self._rm(owner_id)  # the per-owner lock means any container with this name is a leftover
        proc = await asyncio.create_subprocess_exec(
            *self.command(owner_id, prompt, session_id, resume), env=self.env(),
            stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE, limit=16 * 1024 * 1024)
        err = asyncio.create_task(proc.stderr.read())
        deadline = time.monotonic() + self.s.turn_timeout
        try:
            while True:
                left = deadline - time.monotonic()
                if left <= 0:
                    raise TimeoutError
                line = await asyncio.wait_for(proc.stdout.readline(), left)
                if not line:
                    break
                try:
                    yield json.loads(line)
                except json.JSONDecodeError:
                    continue
            code = await proc.wait()
            if code:
                tail = (await err).decode(errors="replace")[-1500:]
                yield {"type": "runner_error", "message": f"exit {code}: {tail}"}
        except TimeoutError:
            yield {"type": "runner_error", "message": "turn timed out"}
        finally:
            if proc.returncode is None:
                await self._rm(owner_id)
                proc.kill()
            err.cancel()


class FakeRunner:
    """Plays back canned stream-json events. Used by tests and by `MS_RUNNER=fake` for web work without Docker."""

    def __init__(self, events: list[dict], delay: float = 0.0):
        self.events, self.delay = events, delay
        self.calls: list[dict] = []
        self.active = self.max_active = 0
        self.active_per_owner: dict[str, int] = defaultdict(int)
        self.max_active_per_owner: dict[str, int] = defaultdict(int)

    async def run(self, owner_id: str, prompt: str, session_id: str, resume: bool) -> AsyncIterator[dict]:
        self.calls.append({"owner_id": owner_id, "prompt": prompt, "session_id": session_id, "resume": resume})
        self.active += 1
        self.active_per_owner[owner_id] += 1
        self.max_active = max(self.max_active, self.active)
        self.max_active_per_owner[owner_id] = max(self.max_active_per_owner[owner_id], self.active_per_owner[owner_id])
        try:
            for ev in self.events:
                await asyncio.sleep(self.delay)
                yield ev
        finally:
            self.active -= 1
            self.active_per_owner[owner_id] -= 1
