"""MainStreet AI API (spec §7): owners, turns over SSE, approvals, one-time passwords, media, iMessage."""
import json
import logging
import os
import secrets
import subprocess
import time
from datetime import date
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .imessage import IMessage, RateLimited
from .runner import DockerRunner, FakeRunner, Runner, token_looks_valid
from .settings import Settings
from .turns import LimitReached, TurnManager
from .workspaces import Gone, NotFound, Workspaces


class OwnerIn(BaseModel):
    source: str = Field(min_length=1, max_length=500)


class TurnIn(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    channel: Literal["web", "imessage"] = "web"


class DecisionIn(BaseModel):
    decision: Literal["approve", "reject"]


class IMessageIn(BaseModel):
    from_hash: str = Field(pattern=r"^[0-9a-f]{64}$")
    text: str = Field(min_length=1, max_length=2000)


def docker_ready(image: str) -> bool:
    try:
        return subprocess.run(["docker", "image", "inspect", image], capture_output=True, timeout=5).returncode == 0
    except (OSError, subprocess.TimeoutExpired):
        return False


def create_app(runner: Runner | None = None, settings: Settings | None = None,
               check_docker: Callable[[], bool] | None = None,
               check_token: Callable[[], bool] | None = None) -> FastAPI:
    s = settings or Settings()
    ws = Workspaces(s.workspaces)
    turns = TurnManager(runner or DockerRunner(s), ws, s)
    app = FastAPI(title="MainStreet AI API")
    app.state.settings, app.state.ws, app.state.turns = s, ws, turns
    app.state.imessage = IMessage(ws, turns, s)
    app.add_middleware(CORSMiddleware, allow_origins=s.web_origins, allow_methods=["GET", "POST"],
                       allow_headers=["Content-Type"])
    check_docker = check_docker or (lambda: docker_ready(s.image))
    check_token = check_token or token_looks_valid
    health_cache: dict = {}
    owners_today: dict[str, int] = {}

    @app.exception_handler(NotFound)
    async def _nf(_, __):
        return JSONResponse({"detail": "Not found"}, status_code=404)

    @app.exception_handler(Gone)
    async def _gone(_, __):
        return JSONResponse({"detail": "Already shown once"}, status_code=410)

    @app.exception_handler(LimitReached)
    async def _limit(_, e):
        return JSONResponse({"detail": str(e)}, status_code=429)

    @app.get("/api/health")
    def health():
        if health_cache.get("at", 0) < time.monotonic() - 20:
            d, t = bool(check_docker()), bool(check_token())
            health_cache.update(at=time.monotonic(), body={"ok": d and t, "docker": d, "token": t})
        return health_cache["body"]

    @app.post("/api/owners")
    async def create_owner(body: OwnerIn):
        today = date.today().isoformat()
        if owners_today.get(today, 0) >= s.owners_per_day:
            raise HTTPException(429, "We're at today's limit for new businesses. Try the examples instead.")
        owners_today[today] = owners_today.get(today, 0) + 1
        return {"owner_id": ws.create_owner(body.source.strip())}

    @app.post("/api/owners/{owner_id}/turns")
    async def start_turn(owner_id: str, body: TurnIn):
        return {"turn_id": turns.start(owner_id, body.text.strip(), body.channel)}

    @app.get("/api/turns/{turn_id}/events")
    async def turn_events(turn_id: str):
        turns.get(turn_id)  # 404 before the stream starts

        async def gen():
            async for ev in turns.events(turn_id):
                yield ": ping\n\n" if ev is None else f"data: {json.dumps(ev)}\n\n"

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

    @app.get("/api/owners/{owner_id}")
    async def bundle(owner_id: str):
        return {**ws.read_bundle(owner_id), "active_turn": turns.active_turn(owner_id)}

    @app.post("/api/owners/{owner_id}/approvals/{approval_id}")
    async def decide(owner_id: str, approval_id: str, body: DecisionIn):
        # No await between reading and writing the approval, so two clicks cannot both pass.
        try:
            ap = ws.decide(owner_id, approval_id, body.decision)
        except ValueError as e:
            raise HTTPException(409, f"Already {e}")
        word = "approved" if body.decision == "approve" else "rejected"
        shown = f"{'Approved' if word == 'approved' else 'Declined'}: {ap['summary']}"
        tid = turns.start(owner_id, f"Owner {word} approval {approval_id}", "web", log_text=shown)
        return {"turn_id": tid, "approval": ap}

    @app.get("/api/owners/{owner_id}/password/{tool_id}")
    async def password(owner_id: str, tool_id: str):
        return JSONResponse({"password": ws.reveal_password(owner_id, tool_id)}, headers={"Cache-Control": "no-store"})

    @app.get("/media/{owner_id}/{name}")
    async def media(owner_id: str, name: str):
        return FileResponse(ws.media_path(owner_id, name), media_type="video/mp4")

    @app.post("/api/imessage")
    async def imessage(body: IMessageIn, request: Request):
        if s.relay_secret and not secrets.compare_digest(request.headers.get("x-relay-secret", ""), s.relay_secret):
            raise HTTPException(401, "Unknown relay")
        try:
            return await app.state.imessage.handle(body.from_hash, body.text.strip())
        except RateLimited as e:
            raise HTTPException(429, str(e))

    return app


def main() -> None:
    import uvicorn

    logging.basicConfig(level=logging.INFO)
    runner = None
    if os.environ.get("MS_RUNNER") == "fake":
        runner = FakeRunner([{"type": "system", "subtype": "init"},
                             {"type": "result", "subtype": "success", "is_error": False,
                              "result": "This is the offline test agent. The real one runs in Docker."}], delay=0.5)
    uvicorn.run(create_app(runner=runner), host="127.0.0.1", port=int(os.environ.get("MS_API_PORT", "8787")))
