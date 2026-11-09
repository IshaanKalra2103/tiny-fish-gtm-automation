from datetime import date

from mscatalog import vet


def test_longevity_from_rdap_date():
    today = date(2026, 11, 8)
    s = vet.longevity("foo.com", "Foo", rdap=lambda d: date(2023, 3, 1), search=lambda q, domains=None: [], today=today)
    assert s.points == 15
    s = vet.longevity("foo.com", "Foo", rdap=lambda d: date(2026, 2, 1), search=lambda q, domains=None: [], today=today)
    assert s.points == 0


def test_viability_zero_on_shutdown_news():
    hits = [{"title": "Foo is shutting down its AI receptionist", "url": "https://news.example/foo",
             "snippet": "Foo announced it is shutting down on December 1.", "site": "news.example", "date": "Sep 2, 2026"}]
    s = vet.viability("Foo", search=lambda q, domains=None: hits, today=date(2026, 11, 8))
    assert s.points == 0
    assert s.evidence_url == "https://news.example/foo"
    s = vet.viability("Foo", search=lambda q, domains=None: [], today=date(2026, 11, 8))
    assert s.points == 10


def test_review_snippet_parse():
    assert vet.parse_review_snippet("4.6 out of 5 (123 reviews)") == (4.6, 123)
    assert vet.parse_review_snippet("Rated 4.8/5 stars from 1,204 reviews") == (4.8, 1204)
    assert vet.parse_review_snippet("No ratings here") is None


def test_reviews_ignore_competitor_pages_and_read_app_store():
    hits = [
        {"title": "Top 10 Foo Alternatives", "url": "https://www.g2.com/products/foo/competitors/alternatives",
         "snippet": "Birdeye, rated 4.7 out of 5 from 4142 reviews"},
        {"title": "Foo - App Store", "url": "https://apps.apple.com/us/app/foo/id1", "snippet": "Great app."},
    ]
    s = vet.reviews("Foo", search=lambda q, domains=None: hits,
                    fetch_text=lambda url: "Ratings & Reviews\n* 4.7\n\n out of 5\n\n 3.5K Ratings")
    assert s.points == 15 and "3500" in s.value and s.evidence_url.startswith("https://apps.apple.com")


def test_review_formats_and_name_match():
    assert vet.parse_review_snippet("By Chatling 4.7/5(79) Read Chatling Reviews") == (4.7, 79)
    assert vet.parse_review_snippet("4.5 Based on 44 reviews.") == (4.5, 44)
    hits = [{"title": "Papaya Global Software", "url": "https://www.capterra.com/p/1/Papaya-Platform/", "snippet": "4.5 Based on 44 reviews."}]
    assert vet.reviews("Apaya", search=lambda q, domains=None: hits, fetch_text=None).points == 0
    hits = [{"title": "Chatling Products | Read 79 Reviews on G2", "url": "https://www.g2.com/sellers/chatling",
             "snippet": "Chatling has been rated 4.7 stars by 79 verified reviews on G2."}]
    assert vet.reviews("Chatling", search=lambda q, domains=None: hits, fetch_text=None).points == 15


def test_review_skips_sponsored_rating():
    text = "Chatling Features See all 79 Chatling reviews. AI Verified. Gemini. Sponsored. Gemini. 4.4/5(617) ..."
    assert vet.parse_review_snippet(text, near=vet._name_re("Chatling")) is None
    assert vet.parse_review_snippet("By Chatling 4.7/5(79) Read Chatling Reviews", near=vet._name_re("Chatling")) == (4.7, 79)
