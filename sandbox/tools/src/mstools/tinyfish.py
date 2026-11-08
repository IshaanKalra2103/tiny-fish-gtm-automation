"""Thin wrappers over the TinyFish primitives (SDK 0.11). Spend is charged by the caller (tf.py).

Search -> discover URLs we don't have yet (free)
Fetch  -> read known URLs as clean markdown (free)
Agent  -> goal-driven multi-step work on interactive pages ($0.016/step), queued and polled
"""
from tinyfish import AgentConfig, BrowserProfile, ProxyConfig, TinyFish

_client: TinyFish | None = None


def client() -> TinyFish:
    global _client
    if _client is None:
        _client = TinyFish()
    return _client


def search(query: str, domains: list[str] | None = None) -> list[dict]:
    kw = {"include_domains": ",".join(domains)} if domains else {}
    res = client().search.query(query=query, location="US", **kw)
    return [{"title": r.title, "url": r.url, "snippet": r.snippet, "site": r.site_name,
             "date": getattr(r, "date", None)} for r in res.results]


def fetch(urls: list[str], max_chars: int = 20_000) -> tuple[list[dict], list[str]]:
    """Never raises: URLs that could not be read come back in the failed list."""
    docs: list[dict] = []
    failed: list[str] = []
    for i in range(0, len(urls), 10):
        chunk = urls[i:i + 10]
        try:
            res = client().fetch.get_contents(urls=chunk)
        except Exception:
            failed += chunk
            continue
        for r in res.results:
            text = (r.text or "")[:max_chars]
            if text.strip():
                docs.append({"url": r.url, "title": r.title, "text": text})
            else:
                failed.append(r.url)
        failed += [e.url for e in (res.errors or [])]
    return docs, failed


def queue_agent(url: str, goal: str, schema: dict | None, max_steps: int) -> str:
    r = client().agent.queue(url=url, goal=goal, output_schema=schema, browser_profile=BrowserProfile.STEALTH,
                             proxy_config=ProxyConfig(enabled=True, country_code="US"),
                             agent_config=AgentConfig(max_steps=max_steps))
    if not r.run_id:
        raise RuntimeError(getattr(r.error, "message", None) or "TinyFish did not start the run")
    return r.run_id


def get_run(run_id: str) -> dict:
    r = client().runs.get(run_id)
    err = getattr(r, "error", None)
    return {"run_id": r.run_id, "status": str(getattr(r.status, "value", r.status)), "result": r.result,
            "error": getattr(err, "message", None) if err else None, "streaming_url": getattr(r, "streaming_url", None)}
