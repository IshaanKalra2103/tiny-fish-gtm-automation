"""Discover: run the query grid through TinyFish Search and turn hits into vendor candidates, one per domain."""
import re
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, field
from urllib.parse import urlparse

DIRECTORY = "theresanaiforthat.com"

EXCLUDED = {
    # review sites, directories, social, video, encyclopedias
    "g2.com", "capterra.com", "reddit.com", "youtube.com", "medium.com", "forbes.com", "linkedin.com",
    DIRECTORY, "producthunt.com", "wikipedia.org", "getapp.com", "softwareadvice.com", "trustpilot.com",
    "trustradius.com", "quora.com", "facebook.com", "instagram.com", "x.com", "twitter.com", "tiktok.com",
    "pinterest.com", "github.com", "apple.com", "google.com", "yelp.com", "amazon.com", "substack.com",
    "futurepedia.io", "toolify.ai", "aitoolsdirectory.com", "saasworthy.com", "sourceforge.net", "crunchbase.com",
    # news and magazines
    "techcrunch.com", "theverge.com", "wired.com", "cnbc.com", "cnn.com", "nytimes.com", "wsj.com",
    "bloomberg.com", "reuters.com", "businessinsider.com", "zdnet.com", "cnet.com", "pcmag.com", "techradar.com",
    "tomsguide.com", "entrepreneur.com", "inc.com", "fastcompany.com", "venturebeat.com", "usatoday.com",
    "washingtonpost.com", "theguardian.com", "bbc.com", "bbc.co.uk", "fortune.com", "nerdwallet.com",
    "investopedia.com", "uschamber.com", "sba.gov", "restaurantbusinessonline.com", "nrn.com", "qsrmagazine.com",
    "achrnews.com", "prnewswire.com", "businesswire.com", "globenewswire.com", "axios.com", "theinformation.com",
    "zapier.com", "hubspot.com",
}

TWO_PART = {"co.uk", "co.nz", "co.in", "com.au", "com.br", "co.za", "co.jp", "com.mx", "com.sg", "co.il", "org.uk"}


def registrable(url_or_host: str) -> str:
    host = urlparse(url_or_host).hostname if "//" in url_or_host else url_or_host
    host = (host or "").lower().strip(".")
    parts = host.split(".")
    if len(parts) >= 3 and ".".join(parts[-2:]) in TWO_PART:
        return ".".join(parts[-3:])
    return ".".join(parts[-2:])


def excluded(domain: str) -> bool:
    return domain in EXCLUDED or domain.endswith((".gov", ".edu")) or not re.match(r"^[a-z0-9-]+(\.[a-z0-9-]+)+$", domain)


@dataclass
class Candidate:
    domain: str
    name_guess: str
    urls: list[str] = field(default_factory=list)
    hits: list[dict] = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)


def _name_from_title(title: str, domain: str) -> str:
    t = re.split(r"\s+[|\-–—:]\s+", title or "")[0].strip()
    stem = domain.split(".")[0]
    return t if t and len(t) <= 30 and stem[:4].lower() in t.lower().replace(" ", "") else stem.capitalize()


def _directory_target(links: list[str]) -> str | None:
    """A There's An AI For That tool page links out to the tool with a ref=taaft tag."""
    for link in links:
        if "taaft" in link.lower() and DIRECTORY not in link:
            return link
    return None


def run(queries: list[str], search=None, meta: dict | None = None, fetch_links=None, workers: int = 4,
        sleep: bool = True) -> list["Candidate"]:
    if search is None:
        from mstools.tinyfish import search
    meta = meta or {}

    failed: list[str] = []

    def one(q):
        for attempt in range(4):  # Search rate-limits bursts; back off and retry
            try:
                return q, search(q)
            except Exception:
                time.sleep(1.5 * (attempt + 1) if sleep else 0)
        failed.append(q)
        return q, []

    with ThreadPoolExecutor(workers) as ex:
        results = list(ex.map(one, queries))

    by_domain: dict[str, Candidate] = {}
    directory_hits: list[tuple[str, dict]] = []
    for q, hits in results:
        for h in hits:
            url = h.get("url") or ""
            domain = registrable(url)
            if domain == DIRECTORY and "/ai/" in url:
                directory_hits.append((q, h))
            if not domain or excluded(domain):
                continue
            _add(by_domain, domain, q, h, url, meta)

    if fetch_links and directory_hits:
        pages = fetch_links([h["url"] for _, h in directory_hits])
        for q, h in directory_hits:
            target = _directory_target(pages.get(h["url"], []))
            if target:
                domain = registrable(target)
                if domain and not excluded(domain):
                    _add(by_domain, domain, q, {**h, "via": "directory"}, target.split("?")[0], meta)

    if failed:
        print(f"discover: {len(failed)} queries failed after retries: {failed[:5]}", flush=True)
    return sorted(by_domain.values(), key=lambda c: -len(c.hits))


def _add(by_domain, domain, q, h, url, meta):
    c = by_domain.get(domain)
    if c is None:
        c = by_domain[domain] = Candidate(domain=domain, name_guess=_name_from_title(h.get("title", ""), domain))
    if url not in c.urls:
        c.urls.append(url)
    m = meta.get(q, {})
    c.hits.append({"query": q, "need_id": m.get("need_id"), "business_type": m.get("business_type"),
                   "url": url, "title": h.get("title"), "snippet": (h.get("snippet") or "")[:300]})


def select(cands: list[Candidate], limit: int, seeds: list[dict] | None = None) -> list[Candidate]:
    """Seeds first, then round-robin over jobs (by hit count) so every job gets candidates before any gets many."""
    chosen: dict[str, Candidate] = {}
    by_domain = {c.domain: c for c in cands}
    for s in seeds or []:
        c = by_domain.get(s["domain"]) or Candidate(domain=s["domain"], name_guess=s["name"],
                                                     urls=[f"https://{s['domain']}/"],
                                                     hits=[{"query": "seed", "need_id": s.get("need_id"), "business_type": None,
                                                            "url": f"https://{s['domain']}/", "title": s["name"], "snippet": ""}])
        chosen[c.domain] = c
    queues: dict[str, list[Candidate]] = {}
    for c in cands:
        jobs = [h["need_id"] for h in c.hits if h.get("need_id")]
        main = max(set(jobs), key=jobs.count) if jobs else "none"
        queues.setdefault(main, []).append(c)
    while len(chosen) < limit and any(queues.values()):
        for q in list(queues.values()):
            while q and q[0].domain in chosen:
                q.pop(0)
            if q and len(chosen) < limit:
                c = q.pop(0)
                chosen[c.domain] = c
    return list(chosen.values())


def merge(*lists: list[Candidate]) -> list[Candidate]:
    """Union of several discovery runs, one candidate per domain, hits deduplicated by (query, url)."""
    out: dict[str, Candidate] = {}
    for cands in lists:
        for c in cands:
            m = out.setdefault(c.domain, Candidate(domain=c.domain, name_guess=c.name_guess))
            m.urls += [u for u in c.urls if u not in m.urls]
            seen = {(h.get("query"), h.get("url")) for h in m.hits}
            m.hits += [h for h in c.hits if (h.get("query"), h.get("url")) not in seen]
    return sorted(out.values(), key=lambda c: -len(c.hits))
