"""Thin wrappers over the TinyFish primitives (SDK 0.11). Spend is charged by the caller (tf.py).

Search -> discover URLs we don't have yet (free)
Fetch  -> read known URLs as clean markdown (free)
Agent  -> goal-driven multi-step work on interactive pages ($0.016/step), queued and polled
"""
import time

from tinyfish import BrowserProfile, ProxyConfig, TinyFish

from .cli import log

RETRY_WAITS = (2.0, 5.0)  # seconds before the 2nd and 3rd attempt

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
        res = None
        for attempt, wait in enumerate(RETRY_WAITS + (None,)):
            try:
                res = client().fetch.get_contents(urls=chunk)
                break
            except Exception as e:  # rate limits and blips while other runs share the key
                log(f"fetch attempt {attempt + 1} failed: {type(e).__name__}: {str(e)[:120]}")
                if wait is None:
                    break
                time.sleep(wait)
        if res is None:
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
    # max_steps only sizes our own budget reservation (tf.py): TinyFish refuses agent_config.max_steps
    # ("not enabled for custom max steps") for accounts outside its beta.
    r = client().agent.queue(url=url, goal=goal, output_schema=schema, browser_profile=BrowserProfile.STEALTH,
                             proxy_config=ProxyConfig(enabled=True, country_code="US"))
    if not r.run_id:
        raise RuntimeError(getattr(r.error, "message", None) or "TinyFish did not start the run")
    return r.run_id


def get_run(run_id: str) -> dict:
    r = client().runs.get(run_id)
    err = getattr(r, "error", None)
    return {"run_id": r.run_id, "status": str(getattr(r.status, "value", r.status)), "result": r.result,
            "error": getattr(err, "message", None) if err else None, "streaming_url": getattr(r, "streaming_url", None)}
