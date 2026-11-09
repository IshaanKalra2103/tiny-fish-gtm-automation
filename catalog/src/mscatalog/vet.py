"""Vet: the six trust signals (plan Task 10 table, spec 6.3), each with its evidence URL, then mstools.trust scores them."""
import re
from datetime import date, datetime, timedelta

from mstools.schemas import Signal, Tool
from mstools.trust import WEIGHTS, score_signals

from . import store
from .discover import registrable

REVIEW_SITES = ["g2.com", "capterra.com", "apps.apple.com"]
NOT_NEWS = {"facebook.com", "linkedin.com", "x.com", "twitter.com", "reddit.com", "youtube.com", "instagram.com",
            "tiktok.com", "quora.com", "medium.com", "crunchbase.com", "tracxn.com", "pitchbook.com", "cbinsights.com",
            "zoominfo.com", "apple.com", "shopify.com", "g2.com", "capterra.com", "producthunt.com", "trustpilot.com",
            "theresanaiforthat.com", "wikipedia.org", "glassdoor.com", "indeed.com"}
PRESS_WORDS = re.compile(r"\b(raises?|raised|funding|seed|series [a-d]|launch(es|ed)?|announces?|partners? with|backed|investment)\b", re.I)
PRODUCT_WORDS = re.compile(r"\b(ai|app|apps|software|platform|startup|saas|tool|product|customers|users|chatbot|receptionist)\b", re.I)


def _search(q, domains=None):
    from mstools.tinyfish import search
    return search(q, domains)


def rdap_created(domain: str, attempts: int = 3) -> date | None:
    """Registration date from RDAP. rdap.org throttles bursts, so retry anything but a clean 404."""
    import time

    import httpx
    for attempt in range(attempts):
        try:
            r = httpx.get(f"https://rdap.org/domain/{domain}", follow_redirects=True, timeout=15)
            if r.status_code == 404:
                return None
            if r.status_code == 200:
                for ev in r.json().get("events", []):
                    if ev.get("eventAction") == "registration" and ev.get("eventDate"):
                        return datetime.fromisoformat(ev["eventDate"].replace("Z", "+00:00")).date()
                return None
        except Exception:
            pass
        time.sleep(2 * (attempt + 1))
    return None


def parse_date(s: str | None, today: date) -> date | None:
    if not s:
        return None
    s = s.strip()
    m = re.match(r"(\d+)\s+(minute|hour|day|week|month|year)s?\s+ago", s, re.I)
    if m:
        n, unit = int(m.group(1)), m.group(2).lower()
        days = {"minute": 0, "hour": 0, "day": 1, "week": 7, "month": 30, "year": 365}[unit] * n
        return today - timedelta(days=days)
    m = re.search(r"([A-Z][a-z]{2,8})\.? (\d{1,2}), (\d{4})", s)
    if m:
        for fmt in ("%b %d %Y", "%B %d %Y"):
            try:
                return datetime.strptime(f"{m.group(1)[:3] if fmt == '%b %d %Y' else m.group(1)} {m.group(2)} {m.group(3)}", fmt).date()
            except ValueError:
                continue
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", s)
    return date(*map(int, m.groups())) if m else None


def identity(facts: dict, evidence: dict) -> Signal:
    company, people, address = facts.get("company"), facts.get("people") or [], facts.get("address")
    url = evidence.get("identity_url")
    if company and people and address:
        return Signal(points=25, max=25, value=f"{company}; people: {', '.join(people[:3])}; address: {address}", evidence_url=url)
    if company:
        missing = [w for w, v in (("named people", people), ("address", address)) if not v]
        return Signal(points=10, max=25, value=f"{company}; no {' or '.join(missing)} found", evidence_url=url)
    return Signal(points=0, max=25, value="no company name found on the site", evidence_url=url)


def longevity(domain: str, name: str, rdap=rdap_created, search=_search, today: date | None = None) -> Signal:
    today = today or date.today()
    created = rdap(domain)
    rdap_url = f"https://rdap.org/domain/{domain}"
    if created and (today - created).days >= 730:
        return Signal(points=15, max=15, value=f"domain registered {created.isoformat()}", evidence_url=rdap_url)
    try:
        hits = search(f'"{name}" funding OR raises OR launches OR press')
    except Exception:
        hits = []
    pat = _name_re(name)
    for h in hits:
        site = registrable(h.get("url", ""))
        text = f"{h.get('title', '')} {h.get('snippet', '')}"
        if site != domain and site not in NOT_NEWS and pat.search(h.get("title", "").lower()) and PRESS_WORDS.search(text):
            when = f"domain registered {created.isoformat()}; " if created else ""
            return Signal(points=5, max=15, value=f"{when}press: {h.get('title', '')[:90]}", evidence_url=h.get("url"))
    value = f"domain registered {created.isoformat()}, under 2 years" if created else "no registration date and no press found"
    return Signal(points=0, max=15, value=value, evidence_url=rdap_url if created else None)


def data_handling(facts: dict, evidence: dict) -> Signal:
    url = evidence.get("privacy_url")
    extra = "; SOC 2 or similar stated" if facts.get("soc2") else ""
    if url and facts.get("privacy_states_training_use"):
        stmt = facts.get("training_statement") or "states whether customer data trains models"
        return Signal(points=20, max=20, value=f"privacy policy: {stmt[:140]}{extra}", evidence_url=url)
    if url:
        return Signal(points=10, max=20, value=f"privacy policy, silent on model training{extra}", evidence_url=url)
    return Signal(points=0, max=20, value="no privacy policy found", evidence_url=None)


def pricing(price: dict, facts: dict, evidence: dict) -> Signal:
    url = price.get("pricing_url") or evidence.get("pricing_url")
    if facts.get("prices_public") or price.get("from_usd_month") is not None:
        usd = price.get("from_usd_month")
        v = ("free plan; " if price.get("free_plan") else "") + (f"from ${usd:g}/month" if usd is not None else "prices listed")
        return Signal(points=15, max=15, value=v, evidence_url=url)
    if facts.get("contact_sales_only"):
        return Signal(points=5, max=15, value='"contact us" pricing only', evidence_url=url)
    if price.get("free_plan"):
        return Signal(points=15, max=15, value="free plan, no paid prices shown", evidence_url=url)
    return Signal(points=0, max=15, value="no pricing found", evidence_url=url)


_COUNT = r"(\d[\d,.]*\s*[KkMm]?)"
_RATING = [
    r"(\d(?:\.\d)?)\s*(?:\*\s*)?(?:out of|/)\s*5(?:\.0)?\s*(?:stars?)?[^\d]{0,30}?\(?\s*" + _COUNT + r"\+?\s*(?:verified\s+)?(?:reviews?|ratings?)",
    r"(?:rated|rating:?)\s*(\d(?:\.\d)?)[^\d]{0,40}?" + _COUNT + r"\+?\s*(?:verified\s+)?(?:reviews?|ratings?)",
    _COUNT + r"\s*(?:reviews?|ratings?)[^\d]{0,30}?(\d\.\d)\s*(?:out of|/)\s*5",
    r"(\d(?:\.\d)?)\s*/\s*5\s*\(\s*" + _COUNT + r"\s*\)",
    r"(\d\.\d)\s*based on\s*" + _COUNT + r"\s*(?:reviews?|ratings?)",
]


def _count(s: str) -> int:
    s = s.replace(",", "").strip()
    mult = 1000 if s[-1:] in "Kk" else 1_000_000 if s[-1:] in "Mm" else 1
    return int(float(s.rstrip("KkMm ")) * mult)


def parse_review_snippet(text: str, near: re.Pattern | None = None) -> tuple[float, int] | None:
    """(rating, count) from review-site text. With `near`, the product name must appear just before the numbers,
    so a sponsored or competitor rating on the same page is skipped."""
    t = text or ""
    found = []
    for i, pat in enumerate(_RATING):
        for m in re.finditer(pat, t, re.I):
            if near is not None and not near.search(t[max(0, m.start() - 30):m.start() + 1].lower()):
                continue
            a, b = m.group(1), m.group(2)
            try:
                rating, count = (float(b), _count(a)) if i == 2 else (float(a), _count(b))
            except ValueError:
                continue
            if 0 < rating <= 5 and count > 0:
                found.append((m.start(), rating, count))
    if not found:
        return None
    _, rating, count = min(found)  # the first rating in the text is the page's own
    return rating, count


def product_review_url(url: str) -> bool:
    """A page about this product's own rating, not a competitors, category or compare page."""
    u = url.lower()
    if any(w in u for w in ("/competitors", "/alternatives", "/categories", "/compare", "/search")):
        return False
    return "g2.com/products/" in u or "g2.com/sellers/" in u or "capterra.com/p/" in u or "capterra.com/reviews/" in u or "apps.apple.com/" in u and "/app/" in u


def _fetch_text(url: str) -> str:
    from .read import fetch_with_links
    got = fetch_with_links([url], max_chars=30_000)
    return next(iter(got.values()), {}).get("text", "")


def _name_re(name: str) -> re.Pattern:
    words = re.findall(r"[a-z0-9]+", name.lower())
    key = words[0] if words and len(words[0]) >= 4 else " ".join(words[:2]) if words else name.lower()
    return re.compile(rf"\b{re.escape(key).replace(chr(92) + ' ', '[ ._-]?')}\b")


def reviews(name: str, search=_search, fetch_text=_fetch_text) -> Signal:
    hits = []
    for q, domains in ((f"{name} reviews", REVIEW_SITES), (f'"{name}" reviews rating', None)):
        try:
            hits += search(q, domains)
        except Exception:
            pass
    pat = _name_re(name)
    mine = [h for h in hits if product_review_url(h.get("url", ""))
            and pat.search(f"{h.get('title', '')} {h.get('url', '').replace('-', ' ')}".lower())]
    best = None
    for h in mine:
        parsed = parse_review_snippet(f"{h.get('title', '')} {h.get('snippet', '')}", near=pat)
        if parsed and (best is None or parsed[1] > best[0][1]):
            best = (parsed, h)
    if best is None and fetch_text:  # snippets rarely carry the numbers; the App Store page does
        for h in [h for h in mine if "apps.apple.com" in h["url"] and "see-all" not in h["url"]][:1]:
            try:
                parsed = parse_review_snippet(fetch_text(h["url"]))
            except Exception:
                parsed = None
            if parsed:
                best = (parsed, h)
    if best:
        (rating, count), h = best
        site = registrable(h["url"])
        if count >= 20 and rating >= 4.0:
            return Signal(points=15, max=15, value=f"{rating} from {count} reviews on {site}", evidence_url=h["url"])
        return Signal(points=7, max=15, value=f"{rating} from {count} reviews on {site}", evidence_url=h["url"])
    if mine:
        return Signal(points=0, max=15, value=f"listed on {registrable(mine[0]['url'])}, no rating or count readable", evidence_url=mine[0]["url"])
    return Signal(points=0, max=15, value="no G2, Capterra or App Store listing found", evidence_url=None)


def _shutdown_about(name: str, text: str) -> bool:
    n = re.escape(name.lower())
    t = text.lower()
    near = r"(?:\W+\w+){0,4}?\W+"
    pats = [rf"\b{n}\b{near}(?:is |will |to )?(?:shut(?:s|ting)? down|shutting down|discontinu\w*|sunset\w*|winds? down|wound down|clos(?:es|ing) (?:its doors|down)|(?:has been|was|is being|to be|gets|got) acquired\b)",
            rf"\b(?:acquires|acquired|acquisition of|buys|bought|sunsets|discontinues|shuts down|shutting down)\W+(?:\w+\W+){{0,3}}?{n}\b"]
    return any(re.search(p, t) for p in pats)


def viability(name: str, search=_search, today: date | None = None) -> Signal:
    today = today or date.today()
    try:
        hits = search(f'"{name}" (shut down OR shutting down OR discontinued OR acquired)')
    except Exception:
        hits = []
    for h in hits:
        text = f"{h.get('title', '')} {h.get('snippet', '')}"
        when = parse_date(h.get("date"), today)
        site = registrable(h.get("url", ""))
        if (when and (today - when).days <= 365 and site not in NOT_NEWS and PRODUCT_WORDS.search(text)
                and _shutdown_about(name, text)):
            return Signal(points=0, max=10, value=f"news {when.isoformat()}: {h.get('title', '')[:100]}", evidence_url=h.get("url"))
    return Signal(points=10, max=10, value="no shutdown or acquisition news in the last 12 months", evidence_url=None)


def signals_for(draft: dict, domain: str, search=_search, rdap=rdap_created) -> dict[str, Signal]:
    facts, ev = draft.get("facts") or {}, draft.get("evidence") or {}
    return {
        "identity": identity(facts, ev),
        "longevity": longevity(domain, draft["name"], rdap=rdap, search=search),
        "data_handling": data_handling(facts, ev),
        "pricing": pricing(draft["price"], facts, ev),
        "reviews": reviews(draft["name"], search=search),
        "viability": viability(draft["name"], search=search),
    }


def run(domain: str, search=_search, rdap=rdap_created) -> dict:
    path = store.records_dir() / f"{domain}.json"
    rec = store.load_json(path)
    draft = rec.get("draft")
    if not rec.get("is_tool") or not draft:
        return rec
    old = rec.get("tool") or {}
    status = old.get("status", "pending")
    taken = {r["tool"]["id"] for r in store.records() if r.get("tool") and r["domain"] != domain}
    if draft["id"] in taken:  # two vendor domains with the same product name
        draft = {**draft, "id": f"{draft['id']}-{domain.split('.')[0]}"}
    trust = score_signals(signals_for(draft, domain, search=search, rdap=rdap), human_approved=status == "approved")
    tool = Tool.model_validate({k: draft[k] for k in Tool.model_fields if k in draft} | {
        "trust": trust.model_dump(), "status": status, "reviewed_by": old.get("reviewed_by"),
        "reviewed_at": old.get("reviewed_at"), "sim_test": old.get("sim_test")})
    if old.get("setup"):  # keep the reviewer's agent-setup toggle
        tool.setup = tool.setup.model_copy(update={k: old["setup"][k] for k in ("agent_setup", "playbook")})
    rec["tool"] = tool.model_dump()
    store.save_json(path, rec)
    return rec


assert set(WEIGHTS) == {"identity", "longevity", "data_handling", "pricing", "reviews", "viability"}
