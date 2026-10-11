"""Offline tests: no TinyFish key or network. TinyFish calls are monkeypatched."""

import json

import pytest
from PIL import Image, ImageDraw

from gtm_identity import cli, collect, market, moodboard, schema

IDENTITY = {
    "product": "TinyFish",
    "one_liner": "The web stack for AI agents.",
    "what_it_really_is": "An API that lets AI agents use the real web.",
    "category": "Web infrastructure for AI agents",
    "audience": [{"name": "AI engineers", "pain": "agents get stuck on real sites", "why_they_care": "one API"}],
    "value_props": [{"claim": "Search and Fetch are free", "evidence_url": "https://www.tinyfish.ai/pricing"},
                    {"claim": "Hundreds of sites in parallel", "evidence_url": "https://www.tinyfish.ai/"}],
    "voice": {"adjectives": ["direct", "technical", "confident"], "do": ["show it working"], "dont": ["hype"]},
    "visual": {"palette": ["#FCFCFC", "#111111", "#FF6A00"], "type": ["Host Grotesk"], "imagery": "white, gradients"},
    "keywords": ["web agents", "browser automation", "MCP"],
    "niches": [{"name": "AI browser agents", "why": "x", "search_terms": ["AI browser agents"]},
               {"name": "web scraping for LLMs", "why": "y", "search_terms": ["web scraping for LLM"]}],
}
PMF = {
    "niches": [{"name": "AI browser agents", "demand": 5, "urgency": 4, "competition": 4, "fit": 5,
                "signals": [{"claim": "r/AI_Agents thread on agents stuck at logins", "evidence_url": "https://reddit.com/1"},
                            {"claim": "news coverage this month", "evidence_url": "https://news.example/2"}],
                "pains": ["CAPTCHAs and logins"]}],
    "chosen_niche": "AI browser agents",
    "hypothesis": "For AI engineers whose agents break on real sites, TinyFish runs them on live sites, unlike DIY scrapers.",
    "risks": ["crowded category"],
    "next_tests": ["launch post A/B on the hook"],
}


@pytest.fixture
def campaign(tmp_path, monkeypatch):
    monkeypatch.setenv("GTM_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    folder = tmp_path / "C1" / "identity"
    folder.mkdir(parents=True)
    return folder


def run_cli(monkeypatch, capsys, *argv) -> tuple[int, dict]:
    monkeypatch.setattr("sys.argv", ["identity", *argv])
    code = cli.main()
    return code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def fake_screenshot(path, accent=(255, 106, 0)):
    img = Image.new("RGB", (1440, 900), (252, 252, 252))
    d = ImageDraw.Draw(img)
    d.rectangle((0, 0, 1440, 60), fill=(17, 17, 17))
    d.rectangle((400, 300, 1000, 420), fill=accent)  # a headline-sized accent block
    img.save(path)


def test_schema_accepts_good_and_explains_bad(tmp_path):
    (tmp_path / "identity.json").write_text(json.dumps(IDENTITY))
    assert schema.validate("identity", tmp_path / "identity.json") == []
    bad = {**IDENTITY, "voice": {**IDENTITY["voice"], "adjectives": ["only one"]},
           "visual": {**IDENTITY["visual"], "palette": ["orange", "#111111"]}}
    (tmp_path / "identity.json").write_text(json.dumps(bad))
    problems = schema.validate("identity", tmp_path / "identity.json")
    assert any(p.startswith("voice.adjectives") for p in problems)
    assert any("#RRGGBB" in p for p in problems)


def test_pmf_chosen_niche_must_be_scored(tmp_path):
    (tmp_path / "pmf.json").write_text(json.dumps(PMF))
    assert schema.validate("pmf", tmp_path / "pmf.json") == []
    (tmp_path / "pmf.json").write_text(json.dumps({**PMF, "chosen_niche": "something else"}))
    assert any("chosen_niche" in p for p in schema.validate("pmf", tmp_path / "pmf.json"))


def test_pick_subpages_prefers_one_page_per_hint():
    links = ["https://www.tinyfish.ai/blog/a", "https://www.tinyfish.ai/blog/b", "https://www.tinyfish.ai/pricing",
             "https://twitter.com/tinyfish", "https://docs.tinyfish.ai/", "https://www.tinyfish.ai/customers#x",
             "https://www.tinyfish.ai/careers"]
    picked = collect.pick_subpages("https://www.tinyfish.ai/", links, 4)
    assert picked == ["https://www.tinyfish.ai/pricing", "https://www.tinyfish.ai/customers",
                      "https://docs.tinyfish.ai", "https://www.tinyfish.ai/blog/a"]


def test_palette_keeps_small_accents(tmp_path):
    fake_screenshot(tmp_path / "s.png")
    hexes = [c["hex"] for c in collect.palette([tmp_path / "s.png"])]
    assert hexes[0] == "#FFFFFF" or hexes[0].startswith("#F")  # the page background first
    assert any(h.startswith("#FF6") or h.startswith("#FE6") for h in hexes), hexes  # the orange survives


def test_css_helpers():
    assert collect.css_hex("rgb(255, 106, 0)") == "#FF6A00"
    assert collect.css_hex("rgba(0, 0, 0, 0)") is None
    assert collect.first_font('"Host Grotesk", Inter, sans-serif') == "Host Grotesk"


def test_moodboard_draft_then_final(campaign, monkeypatch, capsys):
    for i in range(3):
        fake_screenshot(campaign / f"shot_{i}.jpg")
    evidence = {"brand_url": "https://www.tinyfish.ai/", "meta": {"title": "TinyFish", "description": "Web agents"},
                "pages": [{"url": "https://www.tinyfish.ai/", "title": "TinyFish", "text": "..."}],
                "fonts": ["Host Grotesk"], "palette": [{"hex": "#FCFCFC", "share": 0.8}],
                "screenshots": [f"shot_{i}.jpg" for i in range(3)], "images": []}
    (campaign / "evidence.json").write_text(json.dumps(evidence))

    code, out = run_cli(monkeypatch, capsys, "moodboard", "--campaign", "C1")
    assert code == 0 and out["final"] is False and Image.open(out["moodboard"]).size == (moodboard.W, moodboard.H)

    (campaign / "identity.json").write_text(json.dumps(IDENTITY))
    code, out = run_cli(monkeypatch, capsys, "moodboard", "--campaign", "C1")
    assert code == 0 and out["final"] is True and out["moodboard"].endswith("moodboard.png")

    (campaign / "identity.json").write_text(json.dumps({**IDENTITY, "niches": []}))
    code, out = run_cli(monkeypatch, capsys, "moodboard", "--campaign", "C1")
    assert code == 1 and "invalid" in out["error"]


def test_age_parsing():
    assert market.age_days("3 weeks ago") == 21
    assert market.age_days("5 hours ago") == pytest.approx(5 / 24)
    assert market.age_days("Sep 29, 2026") is not None
    assert market.age_days(None) is None and market.age_days("soon") is None


def test_market_scan_uses_identity_niches(campaign, monkeypatch, capsys):
    calls = []

    def fake_search(query, **kw):
        calls.append((query, kw))
        site = (kw.get("include_domains") or "news.example").split(",")[0]
        return [{"title": f"{query} #{i}", "url": f"https://{site}/{len(calls)}/{i}", "snippet": "",
                 "site": site, "date": "3 days ago" if i == 0 else None} for i in range(2)]

    monkeypatch.setattr(market.tf, "search", fake_search)
    monkeypatch.setattr(market.tf, "fetch", lambda urls, **kw: ([{"url": u, "title": "t", "text": "pain " * 50,
                                                                   "links": [], "image_links": []} for u in urls], []))
    (campaign / "identity.json").write_text(json.dumps(IDENTITY))

    code, out = run_cli(monkeypatch, capsys, "market", "--campaign", "C1", "--read", "2")
    assert code == 0
    assert set(out["niches"]) == {"AI browser agents", "web scraping for LLMs"}
    assert len(calls) == 10  # 5 searches per niche
    community = [kw for q, kw in calls if kw.get("include_domains") == "reddit.com,news.ycombinator.com"]
    assert community and all(kw["recency_minutes"] for kw in community)
    report = json.loads((campaign / "market.json").read_text())
    n0 = report["niches"][0]
    assert n0["signals"]["fresh_results"] == 5 and n0["signals"]["dated_results"] == 5
    assert len(n0["threads"]) == 2 and n0["buckets"]["news"][0]["age_days"] == 3
    assert (campaign / n0["social_urls_file"]).read_text().startswith("https://tiktok.com/")


def test_market_needs_niches(campaign, monkeypatch, capsys):
    code, out = run_cli(monkeypatch, capsys, "market", "--campaign", "C1")
    assert code == 1 and "--niche" in out["error"]


def test_schema_command_prints_json_schema(monkeypatch, capsys):
    code = None
    monkeypatch.setattr("sys.argv", ["identity", "schema", "--kind", "pmf"])
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    code = cli.main()
    printed = json.loads(capsys.readouterr().out)
    assert code == 0 and "chosen_niche" in printed["properties"]
