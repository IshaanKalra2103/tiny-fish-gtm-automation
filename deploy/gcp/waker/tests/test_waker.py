"""Proxy and waking logic, with a fake upstream (httpx.MockTransport) and a fake Compute client."""
import asyncio
import json

import httpx
import pytest

from mswaker.app import WAKING_BODY, Waker, create_app

IP = "10.142.0.9"


class FakeCompute:
    """A VM that is TERMINATED until start(); it reports STAGING for `boot_polls` gets, then RUNNING."""

    def __init__(self, status="RUNNING", boot_polls=2, fail_get=False):
        self.st, self.boot_polls, self.fail_get = status, boot_polls, fail_get
        self.gets = self.starts = 0
        self._left = 0

    async def get(self):
        self.gets += 1
        if self.fail_get:
            raise RuntimeError("compute down")
        if self.st == "STAGING":
            self._left -= 1
            if self._left <= 0:
                self.st = "RUNNING"
        return {"status": self.st, "ip": IP}

    async def start(self):
        self.starts += 1
        if self.st == "TERMINATED":
            self.st, self._left = "STAGING", self.boot_polls


class FakeApi:
    """The agent API on the VM. `up` decides whether the port answers; `api_after` delays it after boot."""

    def __init__(self, compute: FakeCompute, api_after=1):
        self.compute, self.api_after = compute, api_after
        self.seen: list[httpx.Request] = []
        self.health_probes = 0

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.compute.st != "RUNNING":
            raise httpx.ConnectError("no route to host", request=request)
        if request.url.path == "/api/health":
            self.health_probes += 1
            if self.health_probes <= self.api_after:
                raise httpx.ConnectError("connection refused", request=request)
            return streamed(200, {"ok": True, "docker": True, "token": True})
        self.seen.append(request)
        return streamed(201, {"path": request.url.path, "query": request.url.query.decode(),
                                         "method": request.method, "body": request.content.decode()},
                        headers=[("x-up", "1"), ("set-cookie", "a=1"), ("set-cookie", "b=2")])


class Chunks(httpx.AsyncByteStream):
    """A body that arrives over the wire (Response(json=...) would be pre-read, unlike a real upstream)."""

    def __init__(self, data: bytes):
        self.data = data

    async def __aiter__(self):
        yield self.data


def streamed(status, body, headers=()):
    return httpx.Response(status, headers=[("content-type", "application/json"), *headers],
                          stream=Chunks(json.dumps(body).encode()))


class Clock:
    def __init__(self):
        self.t = 1000.0

    def __call__(self):
        return self.t

    async def sleep(self, s):
        self.t += s
        await asyncio.sleep(0)


def make(compute, api=None, **kw):
    api = api or FakeApi(compute, api_after=0)
    clock = Clock()
    upstream = httpx.AsyncClient(transport=httpx.MockTransport(api.handler))
    waker = Waker(compute, upstream, host=None, clock=clock, sleep=clock.sleep, **kw)
    app = create_app(waker)
    client = httpx.AsyncClient(transport=httpx.ASGITransport(app=app, client=("203.0.113.7", 5555)),
                               base_url="https://waker.example")
    return client, waker, api, clock


async def test_proxies_method_path_query_body_and_headers():
    compute = FakeCompute("RUNNING")
    client, _, api, _ = make(compute)
    r = await client.post("/api/owners/o_1/turns?x=1&y=2", content=b'{"text":"hi"}',
                          headers={"Origin": "https://mainstreet-ai-five.vercel.app", "X-Relay-Secret": "s3",
                                   "Content-Type": "application/json", "CF-Connecting-IP": "6.6.6.6",
                                   "X-Forwarded-For": "6.6.6.6, 198.51.100.4"})
    assert r.status_code == 201
    assert r.json() == {"path": "/api/owners/o_1/turns", "query": "x=1&y=2", "method": "POST", "body": '{"text":"hi"}'}
    assert r.headers["x-up"] == "1"
    assert r.headers.get_list("set-cookie") == ["a=1", "b=2"]
    sent = api.seen[0]
    assert sent.url.host == IP and sent.url.port == 8787
    assert sent.headers["origin"] == "https://mainstreet-ai-five.vercel.app"
    assert sent.headers["x-relay-secret"] == "s3"
    # The last X-Forwarded-For hop is Cloud Run's; the forged CF-Connecting-IP and first hop are ignored.
    assert sent.headers.get_list("cf-connecting-ip") == ["198.51.100.4"]


async def test_cf_connecting_ip_falls_back_to_socket_peer():
    compute = FakeCompute("RUNNING")
    client, _, api, _ = make(compute)
    await client.get("/api/owners/o_1")
    assert api.seen[0].headers["cf-connecting-ip"] == "203.0.113.7"


@pytest.mark.parametrize("method", ["GET", "PUT", "PATCH", "DELETE", "OPTIONS"])
async def test_every_method_is_proxied(method):
    compute = FakeCompute("RUNNING")
    client, _, api, _ = make(compute)
    r = await client.request(method, "/anything/here")
    assert r.status_code == 201 and api.seen[0].method == method


async def test_health_proxied_when_running():
    compute = FakeCompute("RUNNING")
    client, _, _, _ = make(compute)
    r = await client.get("/api/health")
    assert r.json() == {"ok": True, "docker": True, "token": True}
    assert compute.starts == 0


async def test_health_answers_waking_at_once_and_starts_vm():
    compute = FakeCompute("TERMINATED")
    client, waker, _, _ = make(compute)
    r = await client.get("/api/health")
    assert r.status_code == 200 and r.json() == WAKING_BODY
    assert compute.starts == 1  # the start request went out before the reply (Cloud Run CPU throttling)
    await waker._wake_task  # the kicked-off start finishes in the background
    assert compute.starts == 1 and compute.st == "RUNNING" and waker.up
    r = await client.get("/api/health")
    assert "waking" not in r.json()


async def test_health_never_waits_while_waking():
    compute = FakeCompute("TERMINATED", boot_polls=50)
    client, waker, _, _ = make(compute)
    waker.kick()
    await asyncio.sleep(0)
    gets_before = compute.gets
    r = await asyncio.wait_for(client.get("/api/health"), 1)
    assert r.json() == WAKING_BODY
    assert compute.gets == gets_before  # no extra Compute call or upstream probe while a wake is running
    waker._wake_task.cancel()


async def test_request_to_stopped_vm_starts_it_waits_for_health_then_proxies():
    compute = FakeCompute("TERMINATED", boot_polls=3)
    api = FakeApi(compute, api_after=2)  # the API needs two more polls after the VM is RUNNING
    client, waker, api, clock = make(compute, api)
    t0 = clock()
    r = await client.post("/api/owners", json={"source": "bakery"})
    assert r.status_code == 201 and r.json()["path"] == "/api/owners"
    assert compute.starts == 1
    assert api.health_probes == 3
    assert clock() - t0 < 150


async def test_concurrent_requests_share_one_start():
    compute = FakeCompute("TERMINATED", boot_polls=2)
    client, _, api, _ = make(compute)
    rs = await asyncio.gather(*[client.get(f"/api/owners/o_{i}") for i in range(5)])
    assert [r.status_code for r in rs] == [201] * 5
    assert compute.starts == 1 and len(api.seen) == 5


async def test_wake_gives_up_after_timeout_with_503():
    compute = FakeCompute("TERMINATED", boot_polls=10**6)  # never boots
    client, _, api, clock = make(compute, wake_timeout=150)
    t0 = clock()
    r = await client.get("/api/owners/o_1")
    assert r.status_code == 503 and "starting" in r.json()["detail"]
    assert 140 <= clock() - t0 <= 150
    assert not api.seen


async def test_stopping_vm_is_started_once_it_is_terminated():
    compute = FakeCompute("STOPPING")
    client, waker, _, _ = make(compute)
    task = asyncio.create_task(client.get("/api/owners/o_1"))
    for _ in range(5):
        await asyncio.sleep(0)
    assert compute.starts == 0  # starting a STOPPING VM fails, so the waker waits
    compute.st = "TERMINATED"
    r = await task
    assert r.status_code == 201 and compute.starts == 1


async def test_status_is_cached_for_ten_seconds():
    compute = FakeCompute("RUNNING")
    client, waker, _, clock = make(compute)
    await client.get("/api/owners/o_1")
    n = compute.gets
    for _ in range(5):
        await client.get("/api/owners/o_1")
        clock.t += 1
    assert compute.gets == n  # 5 s later: still cached
    clock.t += 6
    await client.get("/api/owners/o_1")
    assert compute.gets == n + 1


async def test_vm_gone_under_a_cached_running_status_is_woken_and_retried():
    compute = FakeCompute("RUNNING")
    client, waker, api, _ = make(compute)
    await client.get("/api/owners/o_1")
    compute.st = "TERMINATED"  # the idle timer powered it off; the cache still says RUNNING
    r = await client.get("/api/owners/o_2")
    assert r.status_code == 201 and compute.starts == 1
    assert [x.url.path for x in api.seen] == ["/api/owners/o_1", "/api/owners/o_2"]


async def test_compute_outage_still_proxies_to_known_host():
    compute = FakeCompute("RUNNING", fail_get=True)
    client, waker, api, _ = make(compute)
    waker.host = IP
    r = await client.get("/api/owners/o_1")
    assert r.status_code == 201


async def test_response_is_streamed_not_buffered():
    """Drive the ASGI app by hand: the first SSE chunk must reach the client while upstream is still open."""
    compute = FakeCompute("RUNNING")
    first_sent = asyncio.Event()

    class Stream(httpx.AsyncByteStream):
        closed = False

        async def __aiter__(self):
            yield b"data: 1\n\n"
            await asyncio.wait_for(first_sent.wait(), 2)  # deadlocks (and times out) if the proxy buffers
            yield b"data: 2\n\n"

        async def aclose(self):
            Stream.closed = True

    def handler(request):
        if request.url.path == "/api/health":
            return streamed(200, {"ok": True})
        return httpx.Response(200, headers={"content-type": "text/event-stream"}, stream=Stream())

    clock = Clock()
    waker = Waker(compute, httpx.AsyncClient(transport=httpx.MockTransport(handler)), clock=clock, sleep=clock.sleep)
    app = create_app(waker)
    sent: list[dict] = []

    async def receive():
        if not hasattr(receive, "done"):
            receive.done = True
            return {"type": "http.request", "body": b"", "more_body": False}
        await asyncio.sleep(3600)

    async def send(msg):
        sent.append(msg)
        if msg["type"] == "http.response.body" and b"data: 1" in msg.get("body", b""):
            first_sent.set()

    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": "GET", "scheme": "https",
             "path": "/api/turns/t_1/events", "raw_path": b"/api/turns/t_1/events", "query_string": b"",
             "headers": [(b"host", b"waker")], "client": ("1.2.3.4", 1), "server": ("waker", 443)}
    await asyncio.wait_for(app(scope, receive, send), 5)
    start = next(m for m in sent if m["type"] == "http.response.start")
    assert (b"content-type", b"text/event-stream") in start["headers"]
    bodies = [m.get("body", b"") for m in sent if m["type"] == "http.response.body"]
    assert bodies[0] == b"data: 1\n\n" and b"data: 2\n\n" in bodies
    assert Stream.closed


async def test_waking_body_shape():
    assert json.loads(json.dumps(WAKING_BODY)) == {"ok": True, "docker": True, "token": True, "waking": True}


async def test_waking_answers_carry_cors_for_the_site_only():
    compute = FakeCompute("TERMINATED", boot_polls=10**6)
    client, waker, _, _ = make(compute)
    r = await client.get("/api/health", headers={"Origin": "https://mainstreet-ai-five.vercel.app"})
    assert r.json() == WAKING_BODY
    assert r.headers["access-control-allow-origin"] == "https://mainstreet-ai-five.vercel.app"
    r = await client.get("/api/health", headers={"Origin": "https://evil.example"})
    assert "access-control-allow-origin" not in r.headers
    waker._wake_task.cancel()
