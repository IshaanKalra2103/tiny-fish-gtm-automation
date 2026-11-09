"""MainStreet AI API (spec §7): owners, turns (polled, or SSE locally), approvals, one-time passwords, media, iMessage."""
import asyncio
import json
import logging
import os
import secrets
import subprocess
import time
from datetime import date
from typing import Callable, Literal

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse, StreamingResponse
from pydantic import BaseModel, Field

from .imessage import IMessage, RateLimited
from .runner import DockerRunner, FakeRunner, Runner, token_looks_valid
from .settings import Settings
from .turns import LimitReached, TurnManager
from .workspaces import Gone, NotFound, Workspaces

log = logging.getLogger("msapi.app")


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
    owners_today: dict = {"day": "", "all": 0, "ip": {}}

    @app.exception_handler(NotFound)
    async def _nf(_, __):
        return JSONResponse({"detail": "Not found"}, status_code=404)

    @app.exception_handler(Gone)
    async def _gone(_, __):
        return JSONResponse({"detail": "Already shown once"}, status_code=410)

    @app.exception_handler(LimitReached)
    async def _limit(_, e):
        return JSONResponse({"detail": str(e)}, status_code=429)

    def _check_health() -> dict:
        try:
            d, t = bool(check_docker()), bool(check_token())
        except Exception:
            log.exception("health check failed")
            d = t = False
        return {"ok": d and t, "docker": d, "token": t}

    async def _refresh_health() -> dict:
        try:
            body = await asyncio.to_thread(_check_health)  # docker image inspect can take seconds on colima
            health_cache.update(at=time.monotonic(), body=body)
            return body
        finally:
            health_cache.pop("task", None)

    @app.get("/api/health")
    async def health():
        # Stale-while-revalidate: one refresh at a time, and callers get the cached body while it runs.
        if health_cache.get("at", 0) < time.monotonic() - s.health_ttl and "task" not in health_cache:
            health_cache["task"] = asyncio.create_task(_refresh_health())
        if "body" in health_cache:
            return health_cache["body"]
        return await asyncio.shield(health_cache["task"])

    @app.post("/api/owners")
    async def create_owner(body: OwnerIn, request: Request):
        # Behind the Cloudflare tunnel (and the GCP proxy, which sets it) the real client is in CF-Connecting-IP;
        # the socket peer is the proxy. X-Forwarded-For is client-controlled, so it is not used.
        ip = request.headers.get("cf-connecting-ip") or (request.client.host if request.client else "unknown")
        today = date.today().isoformat()
        if owners_today["day"] != today:
            owners_today.update(day=today, all=0, ip={})
        if owners_today["ip"].get(ip, 0) >= s.owners_per_ip_day:
            raise HTTPException(429, "You've started a lot of businesses today. Open one from earlier, or try the examples.")
        if owners_today["all"] >= s.owners_per_day:
            raise HTTPException(429, "We're at today's limit for new businesses. Try the examples instead.")
        owners_today["all"] += 1
        owners_today["ip"][ip] = owners_today["ip"].get(ip, 0) + 1
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

    @app.get("/api/turns/{turn_id}/poll")
    async def turn_poll(turn_id: str, after: int = Query(0, ge=0)):
        # The Cloudflare quick tunnel buffers SSE until the stream ends, so the web polls this instead.
        turn = turns.get(turn_id)
        return JSONResponse({"events": turn.events[after:], "next": len(turn.events), "done": turn.done},
                            headers={"Cache-Control": "no-store"})

    @app.get("/api/owners/{owner_id}")
    async def bundle(owner_id: str):
        return {**ws.read_bundle(owner_id), "active_turn": turns.active_turn(owner_id)}

    @app.post("/api/owners/{owner_id}/approvals/{approval_id}")
    async def decide(owner_id: str, approval_id: str, body: DecisionIn):
        # No await between reading and writing the approval, so two clicks cannot both pass.
        # Turn limits are checked before the decision is written: a refused turn leaves it pending to retry.
        try:
            ws.pending_approval(owner_id, approval_id)
            turns.check(owner_id)
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
    runner, checks = None, {}
    if os.environ.get("MS_RUNNER") == "fake":
        checks = {"check_docker": lambda: True, "check_token": lambda: True}
        runner = FakeRunner([{"type": "system", "subtype": "init"},
                             {"type": "result", "subtype": "success", "is_error": False,
                              "result": "This is the offline test agent. The real one runs in Docker."}], delay=0.5)
    uvicorn.run(create_app(runner=runner, **checks), host=os.environ.get("MS_API_HOST", "127.0.0.1"),
                port=int(os.environ.get("MS_API_PORT", "8787")))
