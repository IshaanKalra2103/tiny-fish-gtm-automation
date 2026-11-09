"""Pure parts of scripts/prerun_demos.py: bundle transform, validation, idempotent skip, index.ts."""
import copy
import importlib.util
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _load(name: str):
    spec = importlib.util.spec_from_file_location(name, ROOT / "scripts" / f"{name}.py")
    mod = importlib.util.module_from_spec(spec)
    sys.modules[name] = mod
    spec.loader.exec_module(mod)
    return mod


pd = _load("prerun_demos")
OID = "o_0123456789"


def api_bundle() -> dict:
    """What GET /api/owners/{id} returns after a good run (shape from api/src/msapi/workspaces.py)."""
    needs = [
        {"need_id": "missed-calls", "title": "AI phone receptionist", "why": "w", "est_hours_saved_week": 3},
        {"need_id": "reviews", "title": "Review replies", "why": "w", "est_hours_saved_week": 1},
        {"need_id": "booking", "title": "Online booking", "why": "w", "est_hours_saved_week": 2},
        {"need_id": "social-posts", "title": "Social posts", "why": "w", "est_hours_saved_week": 1},
    ]
    compares = {
        n["need_id"]: {"need_id": n["need_id"], "recommended_tool_id": f"{n['need_id']}-a",
                       "options": [{"tool_id": f"{n['need_id']}-a", "fit_sentence": "f", "works_with": []},
                                   {"tool_id": f"{n['need_id']}-b", "fit_sentence": "f", "works_with": []}]}
        for n in needs[:3]
    }
    return {
        "owner_id": OID,
        "source": "https://mainstreet-demo-sites.vercel.app/hvac/",
        "profile": {"name": "Two Vans", "business_type": "hvac", "city": "Hagerstown", "state": "MD",
                    "size": "s", "uses": [], "pains": [], "summary": "s"},
        "needs": {"items": needs},
        "compares": compares,
        "previews": {
            "recep-a": {"tool_id": "recep-a", "prompt": "p", "status": "completed",
                        "video_file": "preview_recep-a.mp4", "cost_usd": 0.4,
                        "video_url": f"/media/{OID}/preview_recep-a.mp4"},
            "recep-b": {"tool_id": "recep-b", "prompt": "p", "status": "failed",
                        "video_file": None, "cost_usd": 0.0, "video_url": None},
        },
        "setups": {
            "recep-a": {"tool_id": "recep-a", "status": "done", "username": "u@x.example",
                        "password": "hunter2", "configured": [], "next_steps": [], "has_password": True,
                        "extra": {"nested": [{"password": "deep", "ok": 1}]}},
        },
        "approvals": [],
        "messages": [
            {"role": "owner", "text": "Here is my business", "channel": "web", "at": "t"},
            {"role": "agent", "text": f"Your page: https://mainstreet-ai-five.vercel.app/b/{OID}", "channel": "web", "at": "t"},
        ],
        "active_turn": None,
    }


def demo(slug: str = "hvac"):
    return pd.to_demo_bundle(api_bundle(), slug)


# transform

def test_owner_id_rewritten_everywhere():
    b, _ = demo()
    assert b["owner_id"] == "demo-hvac"
    assert OID not in json.dumps(b)
    assert "/b/demo-hvac" in b["messages"][1]["text"]


def test_video_url_rewritten_and_media_map():
    b, downloads = demo()
    assert b["previews"]["recep-a"]["video_url"] == "/demo-media/hvac/recep-a.mp4"
    assert b["previews"]["recep-a"]["video_file"] == "recep-a.mp4"
    assert b["media"] == {"recep-a": "/demo-media/hvac/recep-a.mp4"}
    assert downloads == {"recep-a": f"/media/{OID}/preview_recep-a.mp4"}


def test_previews_without_video_are_dropped():
    b, downloads = demo()
    assert "recep-b" not in b["previews"]
    assert "recep-b" not in b["media"] and "recep-b" not in downloads


def test_passwords_stripped_recursively():
    b, _ = demo()
    text = json.dumps(b)
    assert '"password"' not in text and "hunter2" not in text and "deep" not in text
    s = b["setups"]["recep-a"]
    assert s["has_password"] is False
    assert s["username"] == "u@x.example"
    assert "active_turn" not in b


def test_strip_secrets_other_keys():
    out = pd.strip_secrets({"a": {"Password": "x", "api_key": "k", "client_secret": "c", "keep": 1}, "l": [{"pwd": "p"}]})
    assert out == {"a": {"keep": 1}, "l": [{}]}


def test_transform_does_not_mutate_input():
    src = api_bundle()
    before = copy.deepcopy(src)
    pd.to_demo_bundle(src, "hvac")
    assert src == before


def test_drop_media_removes_failed_download():
    b, _ = demo()
    b2 = pd.drop_media(b, {"recep-a"})
    assert b2["media"] == {} and "recep-a" not in b2["previews"]


# validation

def test_validate_good_bundle():
    b, _ = demo()
    assert pd.validate(b, "hvac") == []


def test_validate_reports_each_miss():
    src = api_bundle()
    src["profile"] = None
    src["needs"]["items"] = src["needs"]["items"][:2]
    src["compares"].pop("reviews")
    src["previews"] = {}
    b, _ = pd.to_demo_bundle(src, "hvac")
    misses = pd.validate(b, "hvac")
    text = " | ".join(misses)
    assert "profile" in text
    assert "needs" in text
    assert "reviews" in text
    assert "preview" in text


def test_validate_wrong_business_type():
    src = api_bundle()
    src["profile"]["business_type"] = "salon"
    b, _ = pd.to_demo_bundle(src, "hvac")
    assert any("type" in m for m in pd.validate(b, "hvac"))


def test_validate_too_many_needs_and_missing_compare_for_top3_only():
    src = api_bundle()
    src["needs"]["items"] = src["needs"]["items"] * 2  # 8 needs
    b, _ = pd.to_demo_bundle(src, "hvac")
    assert any("needs" in m for m in pd.validate(b, "hvac"))
    # a missing compare for need #4 is fine
    src = api_bundle()
    b, _ = pd.to_demo_bundle(src, "hvac")
    assert "social-posts" not in b["compares"] and pd.validate(b, "hvac") == []


def test_validate_catches_password_and_live_owner_id():
    b, _ = demo()
    b["setups"]["recep-a"]["password"] = "x"
    b["messages"].append({"role": "agent", "text": "o_abcdef0123", "channel": "web", "at": "t"})
    misses = " | ".join(pd.validate(b, "hvac"))
    assert "password" in misses and "owner id" in misses


# idempotent skip

def test_should_skip(tmp_path):
    assert pd.should_skip(tmp_path, "hvac", force=False) is False
    b, _ = demo()
    (tmp_path / "hvac.json").write_text(json.dumps(b))
    assert pd.should_skip(tmp_path, "hvac", force=False) is True
    assert pd.should_skip(tmp_path, "hvac", force=True) is False


def test_hand_made_placeholder_is_not_skipped(tmp_path):
    # The hand-made coffee.json has no media map: a real run replaces it.
    placeholder = json.loads((ROOT / "web/data/demo/coffee.json").read_text())
    assert "media" not in placeholder
    (tmp_path / "coffee.json").write_text(json.dumps(placeholder))
    assert pd.should_skip(tmp_path, "coffee", force=False) is False


# helpers

def test_top_needs_keeps_agent_order():
    assert [n["need_id"] for n in pd.top_needs(api_bundle())] == ["missed-calls", "reviews", "booking"]
    assert pd.top_needs({"needs": None}) == []


def test_parse_urls_reads_demo_sites_file():
    urls = pd.parse_urls((ROOT / "demo-sites/URLS.md").read_text())
    assert list(urls) == ["diner", "coffee", "hvac", "landscaping", "salon"]
    assert urls["hvac"] == "https://mainstreet-demo-sites.vercel.app/hvac/"


def test_sse_terminal_event():
    lines = [": ping", "", 'data: {"type": "status", "text": "x"}', "", 'data: {"type": "done", "reply": "hi"}', ""]
    evs = list(pd.sse_events(lines))
    assert evs == [{"type": "status", "text": "x"}, {"type": "done", "reply": "hi"}]


# index.ts

def test_render_index_lists_present_bundles(tmp_path):
    for slug in ("hvac", "coffee"):
        b, _ = demo(slug)
        (tmp_path / f"{slug}.json").write_text(json.dumps(b))
    (tmp_path / "incomplete").mkdir()
    (tmp_path / "incomplete" / "salon.json").write_text("{}")
    ts = pd.render_index(tmp_path)
    assert 'import coffee from "./coffee.json";' in ts
    assert 'import hvac from "./hvac.json";' in ts
    assert "salon from" not in ts
    assert "export const demoBundles: Record<string, OwnerBundle>" in ts
    assert "export const DEMO_BUSINESSES" in ts
    for name in ("Route 40 Diner", "Bean & Brick Coffee", "Main Street Shears"):
        assert name in ts
    # coffee keeps its place before hvac (order of DEMO_BUSINESSES)
    assert ts.index("import coffee") < ts.index("import hvac")


def test_render_index_adds_unknown_slug_card(tmp_path):
    b, _ = demo("bakery")
    b["profile"].update(name="Sweet Rise Bakery", city="Laurel", state="MD", business_type="other")
    (tmp_path / "bakery.json").write_text(json.dumps(b))
    ts = pd.render_index(tmp_path)
    assert 'import bakery from "./bakery.json";' in ts
    assert '"Sweet Rise Bakery"' in ts and '"Laurel, MD"' in ts


# contact sheets

def test_contact_sheet_sample_times():
    cs = _load("contact_sheets")
    ts = cs.sample_times(12.0, 6)
    assert len(ts) == 6 and ts[0] == pytest.approx(1.0) and ts[-1] == pytest.approx(11.0)


def test_unknown_tools_against_web_catalog(tmp_path):
    b, _ = demo()
    cat = tmp_path / "catalog.json"
    cat.write_text(json.dumps({"tools": [{"id": "missed-calls-a"}, {"id": "missed-calls-b"}, {"id": "recep-a"}]}))
    ids = pd.catalog_ids(cat)
    assert pd.unknown_tools(b, ids) == ["booking-a", "booking-b", "reviews-a", "reviews-b"]
    assert pd.catalog_ids(tmp_path / "missing.json") is None
    assert pd.unknown_tools(b, None) == []
