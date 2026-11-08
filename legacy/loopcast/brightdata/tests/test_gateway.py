"""Offline tests against a fake Bright Data API (httpx.MockTransport). No key or network needed.

Fixture records use the field names from docs.brightdata.com/scrapers/{domain}.json.
"""

import json

import httpx
import pytest

from bd_gateway import gateway as gw_mod
from bd_gateway import BrightDataError, BrightDataGateway

TIKTOK_POSTS = [
    {"url": "https://www.tiktok.com/@alice/video/1", "description": "3 agents that save me 2h #AI #agents ask @bob",
     "play_count": 200000, "digg_count": 15000, "comment_count": 300, "num_share_count": 700, "share_count": "700",
     "collect_count": 900, "video_duration": 21, "original_sound": "original sound - alice", "hashtags": ["AI", "agents"],
     "profile_followers": 50000, "profile_username": "alice", "profile_id": "p1", "create_time": "2026-10-08T12:00:00Z"},
    {"url": "https://www.tiktok.com/@carl/video/2", "description": "browser agents are overhyped",
     "play_count": 10000, "digg_count": 300, "comment_count": 80, "share_count": "1.2K", "video_duration": 34,
     "original_sound": "Espresso", "hashtags": ["ai"], "profile_username": "carl"},
    {"error": "Page not found", "error_code": "dead_page", "input": {"url": "https://www.tiktok.com/@x/video/3"}},
]
TIKTOK_COMMENTS = [
    {"post_url": "https://www.tiktok.com/@alice/video/1", "comment_text": "show it actually working first",
     "num_likes": 400, "num_replies": 12, "commenter_user_name": "dana", "commenter_url": "https://tiktok.com/@dana"},
    {"post_url": "https://www.tiktok.com/@alice/video/1", "comment_text": "@erin which tool is this", "num_likes": 900},
    {"post_url": "https://www.tiktok.com/@alice/video/1", "comment_text": "", "num_likes": 1},
]
REELS = [
    {"url": "https://www.instagram.com/reel/abc/", "description": "Stop clicking. Let the agent do it",
     "views": 81000, "likes": 4000, "num_comments": 120, "length": "0:15", "audio_url": "https://www.instagram.com/reels/audio/42/",
     "hashtags": ["#automation"], "followers": 12000, "user_posted": "frank", "date_posted": "2026-10-07"},
]
REEL_COMMENTS = [
    {"post_url": "https://www.instagram.com/reel/abc/", "comment": "is this free? mail me g@h.io", "likes_number": 33,
     "replies_number": 1, "comment_user": "gina_77"},
]
REDDIT_POSTS = [
    {"url": "https://reddit.com/r/AI_Agents/p1", "title": "Agents keep hitting CAPTCHAs", "description": "ask u/someguy",
     "num_upvotes": 120, "num_comments": 40, "user_posted": "harry"},
]

# Commenters, @mentions and creator account fields must never come out. Creator handles inside TikTok post
# URLs (and "original sound - <name>") do, by design: you need the URL to watch the video.
IDENTIFIERS = ("bob", "dana", "erin", "frank", "gina_77", "g@h.io", "someguy", "harry",
               "profile_username", "profile_id", "user_posted", "commenter", "comment_user")


def make(handler, **kw) -> BrightDataGateway:
    return BrightDataGateway("test-key", transport=httpx.MockTransport(handler), poll_every=0, log=lambda m: None, **kw)


def routes(table: dict, calls: list | None = None):
    def handler(req: httpx.Request):
        assert req.headers["authorization"] == "Bearer test-key"
        if calls is not None:
            calls.append(req)
        return httpx.Response(200, json=table[req.url.params["dataset_id"]])
    return handler


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(gw_mod.time, "sleep", lambda s: None)


def test_tiktok_keyword_sample_for_analysis():
    calls = []
    table = {"gd_lu702nij2f790tmv9h": TIKTOK_POSTS, "gd_lkf2st302ap89utw5k": TIKTOK_COMMENTS}
    sample = make(routes(table, calls)).sample("tiktok", keyword="AI agents", posts=10, comment_on_top=1)

    discover, comments = calls
    assert discover.url.params["discover_by"] == "keyword" and discover.url.params["type"] == "discover_new"
    assert json.loads(discover.content) == {"input": [{"search_keyword": "AI agents", "num_of_posts": 10}],
                                            "limit_per_input": 10}
    assert json.loads(comments.content) == [{"url": "https://www.tiktok.com/@alice/video/1", "num_of_comments": 20}]

    top = sample["posts"][0]
    assert top["views"] == 200000 and top["shares"] == 700 and top["saves"] == 900 and top["duration_s"] == 21.0
    assert top["engagement_rate"] == round((15000 + 300 + 700) / 200000, 4)
    assert top["hashtags"] == ["#ai", "#agents"] and top["creator_followers"] == 50000
    assert top["text"] == "3 agents that save me 2h #AI #agents ask @user"
    assert sample["posts"][1]["shares"] == 1200  # "1.2K" from the text field
    assert sample["comments"][0]["text"] == "@user which tool is this"  # sorted by likes, empty one dropped
    stats = sample["stats"]
    assert stats["posts"] == 2 and stats["comments"] == 2 and stats["errors"] == 1
    assert stats["top_hashtags"][0] == ("#ai", 2) and stats["median_duration_s"] == 27.5
    assert not any(name in json.dumps(sample) for name in IDENTIFIERS)
    without_urls = [{k: v for k, v in p.items() if k not in ("url", "sound")} for p in sample["posts"]]
    assert "alice" not in json.dumps(without_urls) and "carl" not in json.dumps(without_urls)


def test_tiktok_hashtag_adds_hash():
    calls = []
    make(routes({"gd_lu702nij2f790tmv9h": [], "gd_lkf2st302ap89utw5k": []}, calls)).posts("tiktok", hashtag="aitools")
    assert json.loads(calls[0].content)["input"] == [{"search_keyword": "#aitools", "num_of_posts": 10}]


def test_instagram_reels_from_tinyfish_urls():
    calls = []
    table = {"gd_lyclm20il4r5helnj": REELS, "gd_ltppn085pokosxh13": REEL_COMMENTS}
    mixed = ["https://news.ycombinator.com/item?id=1", "https://www.instagram.com/reel/abc/",
             "https://www.reddit.com/r/x/comments/2"]
    sample = make(routes(table, calls)).sample("instagram", urls=mixed)

    assert json.loads(calls[0].content) == [{"url": "https://www.instagram.com/reel/abc/"}]  # other sites skipped
    assert "discover_by" not in calls[0].url.params
    reel = sample["posts"][0]
    assert reel["duration_s"] == 15.0 and reel["views"] == 81000
    assert reel["sound"] == "https://www.instagram.com/reels/audio/42/" and reel["hashtags"] == ["#automation"]
    assert sample["comments"][0]["text"] == "is this free? mail me [email]"
    assert "24 hours" in sample["note"]
    assert not any(name in json.dumps(sample) for name in IDENTIFIERS)


def test_instagram_keyword_points_to_tinyfish():
    with pytest.raises(BrightDataError, match="TinyFish Search"):
        make(routes({})).posts("instagram", keyword="ai agents")


def test_instagram_profile_discovery():
    calls = []
    make(routes({"gd_lyclm20il4r5helnj": REELS}, calls)).posts("instagram", from_url="https://www.instagram.com/brand/")
    assert calls[0].url.params["discover_by"] == "url"
    assert json.loads(calls[0].content)["input"] == [{"url": "https://www.instagram.com/brand/", "num_of_posts": 10}]


def test_urls_on_wrong_site():
    with pytest.raises(BrightDataError, match="none of the 1 URLs"):
        make(routes({})).posts("tiktok", urls=["https://www.instagram.com/reel/abc/"])


def test_reddit_still_works():
    sample = make(routes({"gd_lvz8ah06191smkebj4": REDDIT_POSTS, "gd_lvzdpsdlw09j6t702": []})).sample(
        "reddit", keyword="AI agents")
    assert sample["posts"][0]["text"] == "Agents keep hitting CAPTCHAs\nask @user"
    assert "engagement_rate" not in sample["posts"][0]  # no views on Reddit
    assert not any(name in json.dumps(sample) for name in IDENTIFIERS)


def test_sync_scrape_falls_back_to_snapshot_on_202():
    seen = []

    def handler(req: httpx.Request):
        seen.append(req.url.path)
        if req.url.path.endswith("/scrape"):
            return httpx.Response(202, json={"snapshot_id": "sd_1"}, headers={"retry-after": "10"})
        if "/progress/" in req.url.path:
            return httpx.Response(200, json={"status": "running" if seen.count(req.url.path) < 2 else "ready"})
        return httpx.Response(200, text="\n".join(json.dumps(p) for p in TIKTOK_POSTS[:2]))  # NDJSON

    rows = make(handler).scrape("gd_x", [{"url": "u"}])
    assert len(rows) == 2
    assert seen == ["/datasets/v3/scrape", "/datasets/v3/progress/sd_1", "/datasets/v3/progress/sd_1",
                    "/datasets/v3/snapshot/sd_1"]


def test_429_backs_off_then_gives_up(monkeypatch):
    slept = []
    monkeypatch.setattr(gw_mod.time, "sleep", slept.append)
    with pytest.raises(BrightDataError, match="429"):
        make(lambda req: httpx.Response(429)).scrape("gd_x", [{"url": "u"}])
    assert slept == [2, 4, 8, 16, 32]


def test_failed_snapshot_raises():
    def handler(req):
        if req.url.path.endswith("/scrape"):
            return httpx.Response(202, json={"snapshot_id": "sd_2"})
        return httpx.Response(200, json={"status": "failed"})

    with pytest.raises(BrightDataError, match="failed"):
        make(handler).scrape("gd_x", [{"url": "u"}])


def test_missing_key(monkeypatch):
    monkeypatch.delenv("BRIGHTDATA_API_KEY", raising=False)
    with pytest.raises(BrightDataError, match="BRIGHTDATA_API_KEY"):
        BrightDataGateway()


def test_cli_writes_shared_memory_file(monkeypatch, tmp_path, capsys):
    from bd_gateway import cli

    urls = tmp_path / "search_urls.txt"
    urls.write_text("https://news.ycombinator.com/item?id=1\nhttps://www.instagram.com/reel/abc/\n")
    table = {"gd_lyclm20il4r5helnj": REELS, "gd_ltppn085pokosxh13": REEL_COMMENTS}
    monkeypatch.setattr(cli, "BrightDataGateway", lambda: make(routes(table)))
    monkeypatch.setattr(cli, "load_dotenv", lambda *a, **k: None)
    monkeypatch.setenv("GTM_RUNS_DIR", str(tmp_path))
    monkeypatch.setattr("sys.argv", ["bd-gateway", "sample", "--campaign", "c1", "--platform", "instagram",
                                     "--urls-file", str(urls)])

    assert cli.main() == 0
    summary = json.loads(capsys.readouterr().out)
    assert summary["ok"] and summary["posts"] == 1 and summary["comments"] == 1 and summary["median_views"] == 81000
    written = json.loads((tmp_path / "c1" / "social_instagram.json").read_text())
    assert written["platform"] == "instagram" and "SYNTHETIC" in written["note"]
