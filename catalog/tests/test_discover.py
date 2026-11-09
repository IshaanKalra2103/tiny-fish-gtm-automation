from mscatalog import discover


def _search(results):
    def fake(query, domains=None):
        return results.get(query, [])
    return fake


def test_dedupe_by_domain():
    results = {
        "q1": [{"title": "Foo | AI receptionist", "url": "https://app.foo.com/signup", "snippet": "", "site": "app.foo.com"}],
        "q2": [{"title": "Foo", "url": "https://www.foo.com/", "snippet": "", "site": "www.foo.com"}],
    }
    cands = discover.run(["q1", "q2"], search=_search(results))
    assert [c.domain for c in cands] == ["foo.com"]
    assert len(cands[0].hits) == 2
    assert set(cands[0].urls) == {"https://app.foo.com/signup", "https://www.foo.com/"}


def test_excludes_directories():
    results = {"q": [
        {"title": "x", "url": "https://www.g2.com/products/foo", "snippet": "", "site": "g2.com"},
        {"title": "x", "url": "https://www.reddit.com/r/hvac", "snippet": "", "site": "reddit.com"},
        {"title": "x", "url": "https://theresanaiforthat.com/ai/foo/", "snippet": "", "site": "theresanaiforthat.com"},
        {"title": "x", "url": "https://en.wikipedia.org/wiki/Foo", "snippet": "", "site": "wikipedia.org"},
        {"title": "x", "url": "https://www.forbes.com/advisor/foo", "snippet": "", "site": "forbes.com"},
        {"title": "x", "url": "https://techcrunch.com/2026/foo", "snippet": "", "site": "techcrunch.com"},
        {"title": "Bar", "url": "https://bar.ai/", "snippet": "", "site": "bar.ai"},
    ]}
    cands = discover.run(["q"], search=_search(results))
    assert [c.domain for c in cands] == ["bar.ai"]


def test_registrable_domain_two_part_suffix():
    assert discover.registrable("https://shop.foo.co.uk/x") == "foo.co.uk"


def test_select_round_robin_and_seeds():
    def cand(d, job, n):
        return discover.Candidate(domain=d, name_guess=d, urls=[], hits=[{"need_id": job}] * n)
    cands = [cand("a.com", "reviews", 5), cand("b.com", "reviews", 4), cand("c.com", "quotes", 1)]
    got = discover.select(cands, 3, seeds=[{"domain": "chatling.ai", "name": "Chatling", "need_id": "website-chat"}])
    assert [c.domain for c in got] == ["chatling.ai", "a.com", "c.com"]
