"""Minimal remote-MCP client over Streamable HTTP with OAuth (dynamic registration + PKCE).

Plain Python, no MCP SDK, so harness agents on Claude Code or Codex (and process workers) can all use
it. `login()` runs the browser sign-in once and saves the session (client + tokens, mode 600) to a file
the harness container reads through /workspace. Every call refreshes the access token when needed.
"""

import base64
import fcntl
import hashlib
import json
import secrets
import sys
import time
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .config import VidgenError

PROTOCOL = "2025-06-18"


class RemoteMCP:
    def __init__(self, name: str, resource: str, authorize: str, token: str, register: str, session: Path,
                 scope: str = "openid profile email offline_access"):
        self.name, self.resource, self.scope = name, resource, scope
        self.authorize_url, self.token_url, self.register_url = authorize, token, register
        self.session = session

    @contextmanager
    def _locked(self):
        self.session.parent.mkdir(parents=True, exist_ok=True)
        with open(self.session.with_suffix(".lock"), "w") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            yield

    def _save(self, data: dict) -> None:
        tmp = self.session.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, indent=1))
        tmp.chmod(0o600)
        tmp.replace(self.session)

    @staticmethod
    def _store(data: dict, tok: dict) -> dict:
        data["access_token"] = tok["access_token"]
        data["refresh_token"] = tok.get("refresh_token") or data.get("refresh_token")
        data["expires_at"] = time.time() + float(tok.get("expires_in", 3600))
        return data

    def login(self, timeout: int = 300, open_browser: bool = True) -> dict:
        got: dict = {}

        class Callback(BaseHTTPRequestHandler):
            def do_GET(self):
                got.update({k: v[0] for k, v in parse_qs(urlparse(self.path).query).items()})
                self.send_response(200)
                self.send_header("Content-Type", "text/html")
                self.end_headers()
                self.wfile.write(b"<h2>Connected to vidgen. You can close this tab.</h2>")

            def log_message(self, *a):
                pass

        server = HTTPServer(("127.0.0.1", 0), Callback)
        server.timeout = 5
        redirect = f"http://localhost:{server.server_port}/callback"
        reg = httpx.post(self.register_url, json={
            "client_name": "vidgen (GTM harness)", "redirect_uris": [redirect],
            "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
            "token_endpoint_auth_method": "none"}, timeout=30)
        if reg.status_code >= 300:
            raise VidgenError(f"{self.name} client registration {reg.status_code}: {reg.text[:300]}")
        client = reg.json()
        verifier = secrets.token_urlsafe(64)
        challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
        state = secrets.token_urlsafe(16)
        url = f"{self.authorize_url}?" + urlencode({
            "response_type": "code", "client_id": client["client_id"], "redirect_uri": redirect,
            "code_challenge": challenge, "code_challenge_method": "S256", "state": state,
            "resource": self.resource, "scope": self.scope})
        print(f"[{self.name}] sign in at:\n{url}", file=sys.stderr, flush=True)
        if open_browser:
            webbrowser.open(url)
        deadline = time.time() + timeout
        while "code" not in got and "error" not in got and time.time() < deadline:
            server.handle_request()
        server.server_close()
        if got.get("state") != state or "code" not in got:
            raise VidgenError(f"{self.name} sign-in did not complete: {got.get('error', 'timed out')}")
        tok = httpx.post(self.token_url, data={
            "grant_type": "authorization_code", "code": got["code"], "redirect_uri": redirect,
            "client_id": client["client_id"], "code_verifier": verifier, "resource": self.resource}, timeout=30)
        if tok.status_code != 200:
            raise VidgenError(f"{self.name} token exchange {tok.status_code}: {tok.text[:300]}")
        with self._locked():
            self._save(self._store({"client_id": client["client_id"]}, tok.json()))
        return {"session_file": str(self.session)}

    def _access_token(self) -> str:
        if not self.session.exists():
            raise VidgenError(f"{self.name} is not signed in for vidgen: run `vidgen {self.name} login` on a machine "
                              "with a browser (the session file is shared with the harness)")
        with self._locked():
            data = json.loads(self.session.read_text())
            if data.get("expires_at", 0) - 120 > time.time():
                return data["access_token"]
            r = httpx.post(self.token_url, data={"grant_type": "refresh_token", "refresh_token": data["refresh_token"],
                                                 "client_id": data["client_id"], "resource": self.resource}, timeout=30)
            if r.status_code != 200:
                raise VidgenError(f"{self.name} token refresh failed ({r.status_code}); run `vidgen {self.name} login`")
            self._save(self._store(data, r.json()))
            return data["access_token"]

    @staticmethod
    def _parse(r: httpx.Response, want_id: int) -> dict:
        if r.headers.get("content-type", "").startswith("text/event-stream"):
            for line in r.text.splitlines():
                if line.startswith("data:"):
                    msg = json.loads(line[5:].strip())
                    if msg.get("id") == want_id:
                        return msg
            raise VidgenError("MCP: no response in event stream")
        return r.json()

    def rpc(self, method: str, params: dict, timeout: float = 120) -> dict:
        headers = {"Authorization": f"Bearer {self._access_token()}", "Accept": "application/json, text/event-stream",
                   "MCP-Protocol-Version": PROTOCOL}
        with httpx.Client(headers=headers, timeout=timeout) as http:
            r = http.post(self.resource, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
                "protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "vidgen", "version": "0.1"}}})
            if r.status_code != 200:
                raise VidgenError(f"{self.name} initialize {r.status_code}: {r.text[:300]}")
            self._parse(r, 1)
            if sid := r.headers.get("mcp-session-id"):
                http.headers["Mcp-Session-Id"] = sid
            http.post(self.resource, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
            msg = self._parse(http.post(self.resource, json={"jsonrpc": "2.0", "id": 2, "method": method,
                                                             "params": params}), 2)
        if "error" in msg:
            raise VidgenError(f"{self.name} {method}: {msg['error'].get('message', msg['error'])}")
        return msg["result"]

    def tools(self) -> list[dict]:
        return self.rpc("tools/list", {}).get("tools", [])

    def call(self, tool: str, arguments: dict, timeout: float = 120) -> dict:
        res = self.rpc("tools/call", {"name": tool, "arguments": arguments}, timeout=timeout)
        text = "\n".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
        if res.get("isError"):
            raise VidgenError(f"{self.name} {tool}: {text[:500]}")
        if isinstance(res.get("structuredContent"), dict):
            return res["structuredContent"]
        try:
            out = json.loads(text)
            return out if isinstance(out, dict) else {"result": out}
        except json.JSONDecodeError:
            return {"text": text}
