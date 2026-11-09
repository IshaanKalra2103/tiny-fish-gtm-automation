"""ms-waker: the public API URL. Streams every request to the agent VM on :8787 and starts the VM when it is stopped.

- The VM's status comes from the Compute API and is cached for STATUS_TTL seconds.
- A stopped VM is started, and the request is held until GET :8787/api/health answers (at most WAKE_TIMEOUT s).
- GET /api/health never waits: while the VM wakes it answers {"ok": true, ..., "waking": true} at once.
- CF-Connecting-IP is always set from the last X-Forwarded-For entry (the hop Cloud Run appended), because
  the API rate-limits per client on it. Whatever the client sent in CF-Connecting-IP is dropped.
- Response bodies are streamed chunk by chunk (SSE and long polls), never buffered.
"""
from __future__ import annotations

import asyncio
import contextlib
import logging
import os
import time
from typing import Awaitable, Callable, Protocol

import httpx
from starlette.applications import Starlette
from starlette.background import BackgroundTask
from starlette.requests import Request
from starlette.responses import JSONResponse, Response, StreamingResponse
from starlette.routing import Route

log = logging.getLogger("mswaker")

HEALTH_PATH = "/api/health"
WAKING_BODY = {"ok": True, "docker": True, "token": True, "waking": True}
# Hop-by-hop headers (RFC 9110 7.6.1) plus the ones httpx/uvicorn must set themselves.
HOP = {"connection", "keep-alive", "proxy-authenticate", "proxy-authorization", "proxy-connection", "te",
       "trailer", "trailers", "transfer-encoding", "upgrade", "host", "content-length"}
STOPPED = {"TERMINATED", "STOPPED"}
DEFAULT_ORIGINS = {"https://mainstreet-ai-five.vercel.app", "http://localhost:3000"}


class Compute(Protocol):
    async def get(self) -> dict: ...  # {"status": "RUNNING", "ip": "10.142.0.2"}
    async def start(self) -> None: ...


class GceCompute:
    """Compute Engine REST calls with the Cloud Run service account's token from the metadata server."""

    META = "http://metadata.google.internal/computeMetadata/v1/instance/service-accounts/default/token"

    def __init__(self, project: str, zone: str, instance: str, http: httpx.AsyncClient | None = None):
        self.url = f"https://compute.googleapis.com/compute/v1/projects/{project}/zones/{zone}/instances/{instance}"
        self.http = http or httpx.AsyncClient(timeout=httpx.Timeout(10.0))
        self._token, self._token_until = "", 0.0

    async def _auth(self) -> dict:
        if time.monotonic() > self._token_until:
            r = await self.http.get(self.META, headers={"Metadata-Flavor": "Google"})
            r.raise_for_status()
            body = r.json()
            self._token = body["access_token"]
            self._token_until = time.monotonic() + max(int(body.get("expires_in", 300)) - 60, 30)
        return {"Authorization": f"Bearer {self._token}"}

    async def get(self) -> dict:
        r = await self.http.get(self.url, headers=await self._auth())
        r.raise_for_status()
        body = r.json()
        nics = body.get("networkInterfaces") or [{}]
        return {"status": body.get("status", "UNKNOWN"), "ip": nics[0].get("networkIP")}

    async def start(self) -> None:
        r = await self.http.post(f"{self.url}/start", headers=await self._auth())
        if r.status_code >= 400:
            # A start racing another start (or a VM still STOPPING) is not fatal: the wake loop retries.
            log.warning("compute start answered %s: %s", r.status_code, r.text[:300])


class Waker:
    def __init__(self, compute: Compute, upstream: httpx.AsyncClient, *, port: int = 8787,
                 host: str | None = None, status_ttl: float = 10.0, wake_timeout: float = 150.0,
                 poll: float = 2.0, health_timeout: float = 3.0, restart_every: float = 20.0,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], Awaitable[None]] = asyncio.sleep):
        self.compute, self.upstream, self.port, self.host = compute, upstream, port, host
        self.status_ttl, self.wake_timeout, self.poll = status_ttl, wake_timeout, poll
        self.health_timeout, self.restart_every = health_timeout, restart_every
        self.clock, self.sleep = clock, sleep
        self._status: str | None = None
        self._status_at = float("-inf")
        self._status_lock = asyncio.Lock()
        self._wake_task: asyncio.Task | None = None
        self.start_sent = asyncio.Event()  # set once the current wake has asked Compute to start the VM
        self.up = False  # the last health probe or proxied request reached the API

    # -- VM status -------------------------------------------------------------------------------

    async def status(self, force: bool = False) -> str:
        async with self._status_lock:
            if force or self.clock() - self._status_at >= self.status_ttl:
                try:
                    info = await self.compute.get()
                    self._status = info.get("status") or "UNKNOWN"
                    self.host = info.get("ip") or self.host
                except Exception as e:  # noqa: BLE001 - a Compute API hiccup must not take the proxy down
                    log.warning("compute get failed: %s", e)
                    self._status = "UNKNOWN"
                self._status_at = self.clock()
            return self._status or "UNKNOWN"

    def forget_status(self) -> None:
        self._status_at = float("-inf")

    # -- waking ----------------------------------------------------------------------------------

    async def health_ok(self) -> bool:
        if not self.host:
            return False
        try:
            r = await self.upstream.get(f"http://{self.host}:{self.port}{HEALTH_PATH}", timeout=self.health_timeout)
            return r.status_code == 200
        except httpx.HTTPError:
            return False

    def kick(self) -> asyncio.Task:
        """Start (or join) the one wake attempt shared by every waiting request."""
        if self._wake_task is None or self._wake_task.done():
            self.start_sent = asyncio.Event()
            self._wake_task = asyncio.create_task(self._wake())
        return self._wake_task

    async def _wake(self) -> bool:
        t0 = self.clock()
        deadline = t0 + self.wake_timeout
        last_start = float("-inf")
        started = False
        while True:
            st = await self.status(force=True)
            if st in ("RUNNING", "UNKNOWN") and await self.health_ok():
                self.up = True
                if started:
                    log.info("VM awake: API answered %.1f s after the wake began", self.clock() - t0)
                return True
            if st in STOPPED and self.clock() - last_start >= self.restart_every:
                log.info("VM is %s; starting it", st)
                try:
                    await self.compute.start()
                except Exception as e:  # noqa: BLE001
                    log.warning("compute start failed: %s", e)
                last_start, started = self.clock(), True
                self.start_sent.set()
                self.forget_status()
            if self.clock() + self.poll > deadline:
                log.warning("VM did not answer within %.0f s (last status %s)", self.wake_timeout, st)
                return False
            await self.sleep(self.poll)

    async def ensure_up(self) -> bool:
        if self.up and await self.status() == "RUNNING":
            return True
        self.up = False
        return await asyncio.shield(self.kick())

    def mark_down(self) -> None:
        self.up = False
        self.forget_status()

    # -- proxying --------------------------------------------------------------------------------

    def target(self, request: Request) -> str:
        q = request.url.query
        return f"http://{self.host}:{self.port}{request.url.path}" + (f"?{q}" if q else "")

    async def send(self, request: Request, body: bytes, timeout: httpx.Timeout | None = None) -> httpx.Response:
        req = self.upstream.build_request(request.method, self.target(request), headers=forward_headers(request),
                                          content=body, timeout=timeout or self.upstream.timeout)
        return await self.upstream.send(req, stream=True)


def client_ip(request: Request) -> str:
    """The last X-Forwarded-For hop is the one Cloud Run's front end appended; earlier ones can be forged."""
    hops = [h.strip() for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]
    if hops:
        return hops[-1]
    return request.client.host if request.client else "unknown"


def forward_headers(request: Request) -> list[tuple[str, str]]:
    out = [(k, v) for k, v in request.headers.items() if k.lower() not in HOP and k.lower() != "cf-connecting-ip"]
    out.append(("cf-connecting-ip", client_ip(request)))
    return out


def stream_back(resp: httpx.Response) -> StreamingResponse:
    out = StreamingResponse(resp.aiter_raw(), status_code=resp.status_code, background=BackgroundTask(resp.aclose))
    out.raw_headers = [(k.encode("latin-1"), v.encode("latin-1")) for k, v in resp.headers.multi_items()
                       if k.lower() not in HOP - {"content-length"}]
    return out


def cors(request: Request, origins: set[str]) -> dict:
    """CORS for the waker's own answers (waking health, 503). Proxied answers carry the API's own CORS headers."""
    origin = request.headers.get("origin")
    return {"Access-Control-Allow-Origin": origin, "Vary": "Origin"} if origin and origin in origins else {}


def unavailable(request: Request, origins: set[str]) -> JSONResponse:
    return JSONResponse({"detail": "The MainStreet agent is starting up. Try again in a minute."},
                        status_code=503, headers={"Retry-After": "30", **cors(request, origins)})


def create_app(waker: Waker, origins: set[str] | None = None) -> Starlette:
    origins = origins if origins is not None else DEFAULT_ORIGINS

    async def handle(request: Request) -> Response:
        body = await request.body()
        if request.method == "POST" and request.url.path == "/api/owners":
            # Owner creation is rate-limited per client on this value, so log which address it was keyed on.
            log.info("owner create: CF-Connecting-IP=%s (X-Forwarded-For has %d hop(s))", client_ip(request),
                     len([h for h in request.headers.get("x-forwarded-for", "").split(",") if h.strip()]))
        if request.method == "GET" and request.url.path == HEALTH_PATH:
            return await health(request, body)
        for attempt in (1, 2):
            if not await waker.ensure_up():
                return unavailable(request, origins)
            try:
                resp = await waker.send(request, body)
            except (httpx.ConnectError, httpx.ConnectTimeout) as e:
                # The request never reached the API (the VM went down under us), so one retry is safe.
                log.info("upstream connect failed (%s); waking again", type(e).__name__)
                waker.mark_down()
                continue
            waker.up = True
            return stream_back(resp)
        return unavailable(request, origins)

    async def health(request: Request, body: bytes) -> Response:
        waking = waker._wake_task is not None and not waker._wake_task.done()
        st = "WAKING" if waking else await waker.status()
        if st in ("RUNNING", "UNKNOWN") and waker.host:
            try:
                resp = await waker.send(request, body, timeout=httpx.Timeout(waker.health_timeout))
                waker.up = True
                return stream_back(resp)
            except httpx.HTTPError:
                waker.mark_down()
        waker.kick()
        if st in STOPPED:
            # Cloud Run throttles CPU once a response is sent, so let the start call go out first (about 1 s).
            with contextlib.suppress(asyncio.TimeoutError):
                await asyncio.wait_for(waker.start_sent.wait(), 2.5)
        return JSONResponse(WAKING_BODY, headers={"Cache-Control": "no-store", **cors(request, origins)})

    methods = ["GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"]
    routes = [Route("/{path:path}", handle, methods=methods)]

    @contextlib.asynccontextmanager
    async def lifespan(_app):
        yield
        await waker.upstream.aclose()

    return Starlette(routes=routes, lifespan=lifespan)


def from_env() -> Starlette:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s %(message)s")
    e = os.environ
    upstream = httpx.AsyncClient(timeout=httpx.Timeout(connect=5.0, read=None, write=30.0, pool=10.0),
                                 limits=httpx.Limits(max_connections=200, max_keepalive_connections=20))
    compute = GceCompute(e["MS_PROJECT"], e["MS_ZONE"], e.get("MS_INSTANCE", "ms-agent"))
    waker = Waker(compute, upstream, port=int(e.get("MS_UPSTREAM_PORT", "8787")), host=e.get("MS_UPSTREAM_HOST") or None,
                  status_ttl=float(e.get("MS_STATUS_TTL", "10")), wake_timeout=float(e.get("MS_WAKE_TIMEOUT", "150")))
    origins = {o.strip() for o in e.get("MS_WEB_ORIGINS", ",".join(DEFAULT_ORIGINS)).split(",") if o.strip()}
    return create_app(waker, origins)
