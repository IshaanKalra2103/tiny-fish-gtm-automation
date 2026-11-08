"""Vizard Agent (AI video editor) over its remote MCP endpoint, from plain Python.

No MCP client is needed, so harness agents on Claude Code or Codex can both use it.
`vidgen vizard login` runs the OAuth sign-in once, on a machine with a browser. The
session (client registration plus access and refresh tokens) is saved to
video/.vizard/session.json (gitignored, mode 600). The harness container reads it
through the /workspace mount, and every call refreshes the access token when needed.
"""

import base64
import fcntl
import hashlib
import json
import os
import secrets
import sys
import time
import webbrowser
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse

import httpx

from .config import PACKAGE_ROOT, VidgenError

BASE = "https://mcp.agent.vizard.ai"
RESOURCE = f"{BASE}/mcp"
SESSION = Path(os.environ.get("VIZARD_SESSION_FILE", PACKAGE_ROOT / ".vizard" / "session.json"))
PROTOCOL = "2025-06-18"


@contextmanager
def _locked():
    SESSION.parent.mkdir(parents=True, exist_ok=True)
    with open(SESSION.with_suffix(".lock"), "w") as lock:
        fcntl.flock(lock, fcntl.LOCK_EX)
        yield


def _save(session: dict) -> None:
    tmp = SESSION.with_suffix(".tmp")
    tmp.write_text(json.dumps(session, indent=1))
    tmp.chmod(0o600)
    tmp.replace(SESSION)


def _store_tokens(session: dict, tok: dict) -> dict:
    session["access_token"] = tok["access_token"]
    session["refresh_token"] = tok.get("refresh_token") or session.get("refresh_token")
    session["expires_at"] = time.time() + float(tok.get("expires_in", 3600))
    return session


def login(timeout: int = 300, open_browser: bool = True) -> dict:
    """OAuth (dynamic client registration + PKCE) with a one-shot localhost callback."""
    got: dict = {}

    class Callback(BaseHTTPRequestHandler):
        def do_GET(self):
            q = parse_qs(urlparse(self.path).query)
            got.update({k: v[0] for k, v in q.items()})
            self.send_response(200)
            self.send_header("Content-Type", "text/html")
            self.end_headers()
            self.wfile.write(b"<h2>Vizard is connected to vidgen. You can close this tab.</h2>")

        def log_message(self, *a):
            pass

    server = HTTPServer(("127.0.0.1", 0), Callback)
    server.timeout = 5
    redirect = f"http://localhost:{server.server_port}/callback"
    reg = httpx.post(f"{BASE}/register", json={
        "client_name": "vidgen (GTM harness)", "redirect_uris": [redirect],
        "grant_types": ["authorization_code", "refresh_token"], "response_types": ["code"],
        "token_endpoint_auth_method": "client_secret_post"}, timeout=30)
    if reg.status_code >= 300:
        raise VidgenError(f"Vizard client registration {reg.status_code}: {reg.text[:300]}")
    client = reg.json()
    verifier = secrets.token_urlsafe(64)
    challenge = base64.urlsafe_b64encode(hashlib.sha256(verifier.encode()).digest()).rstrip(b"=").decode()
    state = secrets.token_urlsafe(16)
    url = f"{BASE}/authorize?" + urlencode({
        "response_type": "code", "client_id": client["client_id"], "redirect_uri": redirect,
        "code_challenge": challenge, "code_challenge_method": "S256", "state": state, "resource": RESOURCE})
    print(f"[vizard] sign in at:\n{url}", file=sys.stderr)
    if open_browser:
        webbrowser.open(url)
    deadline = time.time() + timeout
    while "code" not in got and "error" not in got and time.time() < deadline:
        server.handle_request()
    server.server_close()
    if got.get("state") != state or "code" not in got:
        raise VidgenError(f"Vizard sign-in did not complete: {got.get('error', 'timed out')}")
    tok = httpx.post(f"{BASE}/token", data={
        "grant_type": "authorization_code", "code": got["code"], "redirect_uri": redirect,
        "client_id": client["client_id"], "client_secret": client.get("client_secret", ""),
        "code_verifier": verifier, "resource": RESOURCE}, timeout=30)
    if tok.status_code != 200:
        raise VidgenError(f"Vizard token exchange {tok.status_code}: {tok.text[:300]}")
    session = _store_tokens({"client_id": client["client_id"], "client_secret": client.get("client_secret", "")},
                            tok.json())
    with _locked():
        _save(session)
    return {"session_file": str(SESSION)}


def _access_token() -> str:
    if not SESSION.exists():
        raise VidgenError("Vizard is not signed in for vidgen: run `uv run --project video vidgen vizard login` "
                          "on a machine with a browser (the session file is shared with the harness)")
    with _locked():
        session = json.loads(SESSION.read_text())
        if session.get("expires_at", 0) - 120 > time.time():
            return session["access_token"]
        r = httpx.post(f"{BASE}/token", data={
            "grant_type": "refresh_token", "refresh_token": session["refresh_token"],
            "client_id": session["client_id"], "client_secret": session["client_secret"],
            "resource": RESOURCE}, timeout=30)
        if r.status_code != 200:
            raise VidgenError(f"Vizard token refresh failed ({r.status_code}); run `vidgen vizard login` again")
        _save(_store_tokens(session, r.json()))
        return session["access_token"]


def _parse(r: httpx.Response, want_id: int) -> dict:
    if r.headers.get("content-type", "").startswith("text/event-stream"):
        for line in r.text.splitlines():
            if line.startswith("data:"):
                msg = json.loads(line[5:].strip())
                if msg.get("id") == want_id:
                    return msg
        raise VidgenError("Vizard: no response in event stream")
    return r.json()


def call(tool: str, arguments: dict, timeout: float = 120) -> dict:
    """Run one Vizard MCP tool and return its result as a dict."""
    headers = {"Authorization": f"Bearer {_access_token()}", "Accept": "application/json, text/event-stream",
               "MCP-Protocol-Version": PROTOCOL}
    with httpx.Client(headers=headers, timeout=timeout) as http:
        r = http.post(RESOURCE, json={"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {
            "protocolVersion": PROTOCOL, "capabilities": {}, "clientInfo": {"name": "vidgen", "version": "0.1"}}})
        if r.status_code != 200:
            raise VidgenError(f"Vizard initialize {r.status_code}: {r.text[:300]}")
        _parse(r, 1)
        if sid := r.headers.get("mcp-session-id"):
            http.headers["Mcp-Session-Id"] = sid
        http.post(RESOURCE, json={"jsonrpc": "2.0", "method": "notifications/initialized"})
        r = http.post(RESOURCE, json={"jsonrpc": "2.0", "id": 2, "method": "tools/call",
                                      "params": {"name": tool, "arguments": arguments}})
        msg = _parse(r, 2)
    if "error" in msg:
        raise VidgenError(f"Vizard {tool}: {msg['error'].get('message', msg['error'])}")
    res = msg["result"]
    text = "\n".join(c.get("text", "") for c in res.get("content", []) if c.get("type") == "text")
    if res.get("isError"):
        raise VidgenError(f"Vizard {tool}: {text[:500]}")
    if isinstance(res.get("structuredContent"), dict):
        return res["structuredContent"]
    try:
        out = json.loads(text)
        return out if isinstance(out, dict) else {"result": out}
    except json.JSONDecodeError:
        return {"text": text}


def upload(path: Path) -> str:
    """Upload a local file; returns the material_url to pass as a material."""
    link = call("get_upload_link", {"file_name": path.name})
    with open(path, "rb") as f:
        r = httpx.put(link["upload_url"], content=f, timeout=600)
    if r.status_code >= 300:
        raise VidgenError(f"Vizard upload {r.status_code}: {r.text[:200]}")
    return link["material_url"]


def materials(items: list[str]) -> list[str]:
    out = []
    for m in items:
        p = Path(m).expanduser()
        out.append(upload(p) if not m.startswith(("http://", "https://")) and p.exists() else m)
    return out


MIN_SECONDS, MAX_SECONDS = 20, 25
DONE, FAILED = {"delivered"}, {"failed", "error", "cancelled"}


def make(prompt: str, refs: list[str], out: Path, seconds: int = 22, aspect: str = "9:16",
         tier: str | None = None, wait: int = 900) -> dict:
    """Reference images + prompt -> one finished short with voiceover, sound and captions.

    Vizard does the visuals, sound and edit. Blocks until delivery, a question or `wait` runs out;
    the latter two return the project id so the caller can `send` an answer or poll `status`.
    """
    seconds = max(MIN_SECONDS, min(MAX_SECONDS, seconds))
    brief = (
        f"{prompt.strip()}\n\n"
        f"Deliver ONE finished {aspect} short video of {seconds} seconds (hard limit: {MIN_SECONDS}-{MAX_SECONDS}s), "
        "with voiceover, music/sound and burned-in captions. "
        + ("The attached images are the visual references: match their product, look and characters. " if refs else "")
        + "Don't ask follow-up questions; make reasonable choices and deliver."
    )
    body = {"brief": brief, "aspect_ratio": aspect, "target_duration_seconds": seconds}
    if refs:
        body["materials"] = materials(refs)
    if tier:
        body["tier"] = tier
    project = call("create_video_project", body)
    pid = project["project_id"]
    print(f"[vizard] project {pid} started", file=sys.stderr)

    deadline = time.time() + wait
    while True:
        left = int(deadline - time.time())
        st = call("get_project_status", {"project_id": pid, "wait_seconds": max(0, min(left, 300))},
                  timeout=min(left, 300) + 120)
        state = st.get("state", "")
        if state in DONE:
            break
        if state in FAILED:
            raise VidgenError(f"Vizard project {pid} {state}: {st.get('editor_message', '')[:300]}")
        if st.get("question") or st.get("questions") or "input" in state or "question" in state:
            return {"ok": False, "state": state, "project_id": pid, "project_url": st.get("project_url"),
                    "question": st.get("question") or st.get("questions") or st.get("editor_message"),
                    "next": f"vidgen vizard send {pid} --message '...'  then  vidgen vizard status {pid} --wait 600"}
        if left <= 0:
            return {"ok": False, "state": state or "working", "project_id": pid, "project_url": st.get("project_url"),
                    "error": f"not delivered within {wait}s",
                    "next": f"vidgen vizard status {pid} --wait 600 --download --campaign <id>"}
        print(f"[vizard] {pid}: {state or 'working'} ({left}s left)", file=sys.stderr)

    saved = download(st, out.parent, f"vizard_{pid}")
    if not saved:
        raise VidgenError(f"Vizard project {pid} delivered no video file: {st.get('project_url')}")
    Path(saved[0]).replace(out)
    return {"ok": True, "path": str(out), "project_id": pid, "project_url": st.get("project_url"),
            "target_seconds": seconds, "refs": len(refs), "extra_files": saved[1:]}


def download(status: dict, folder: Path, prefix: str) -> list[str]:
    """Save every video file linked from a delivered project's status."""
    urls: list[str] = []

    def walk(x):
        if isinstance(x, str) and x.startswith("http"):
            urls.append(x)
        elif isinstance(x, dict):
            for v in x.values():
                walk(v)
        elif isinstance(x, list):
            for v in x:
                walk(v)

    walk({k: status.get(k) for k in ("links", "deliverables")})
    saved = []
    folder.mkdir(parents=True, exist_ok=True)
    with httpx.Client(follow_redirects=True, timeout=600) as http:
        for url in dict.fromkeys(urls):
            with http.stream("GET", url) as r:
                if r.status_code != 200 or not r.headers.get("content-type", "").startswith("video/"):
                    continue
                path = folder / f"{prefix}_{len(saved) + 1}.mp4"
                with open(path, "wb") as f:
                    for chunk in r.iter_bytes():
                        f.write(chunk)
                saved.append(str(path))
    return saved
