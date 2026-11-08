import pytest
from pydantic import ValidationError

from mstools.schemas import Compare, CompareOption, NeedItem, Needs, SimTest, Tool


def need(i="missed-calls"):
    return NeedItem(need_id=i, title="Answer missed calls", why="You are on jobs", est_hours_saved_week=3)


def test_needs_requires_3_to_5_items():
    with pytest.raises(ValidationError):
        Needs(items=[need(), need()])
    with pytest.raises(ValidationError):
        Needs(items=[need()] * 6)
    assert len(Needs(items=[need()] * 3).items) == 3


def test_compare_requires_2_to_3_options():
    opt = CompareOption(tool_id="a", fit_sentence="Fits", works_with=["square"])
    with pytest.raises(ValidationError):
        Compare(need_id="reviews", options=[opt], recommended_tool_id="a")
    with pytest.raises(ValidationError):
        Compare(need_id="reviews", options=[opt] * 4, recommended_tool_id="a")
    assert Compare(need_id="reviews", options=[opt, opt], recommended_tool_id="a")


def tool_data(**over):
    d = {
        "id": "acme-chat", "name": "Acme Chat", "vendor": "Acme Inc", "url": "https://acme.example",
        "need_ids": ["website-chat"], "business_types": ["coffee_shop"],
        "what_it_does": "Answers questions on your website.",
        "price": {"free_plan": True, "from_usd_month": None, "pricing_url": "https://acme.example/pricing", "notes": ""},
        "setup": {"minutes": 15, "difficulty": "easy", "agent_setup": False, "playbook": None},
        "integrations": ["website"],
        "trust": {"score": 80, "badge": "verified", "signals": {}},
        "sim_test": None, "sources": [], "status": "approved", "reviewed_by": "x", "reviewed_at": "2026-11-08",
    }
    d.update(over)
    return d


def test_tool_rejects_unknown_need():
    Tool(**tool_data())
    with pytest.raises(ValidationError):
        Tool(**tool_data(need_ids=["pizza"]))


def test_sim_test_label_is_simulated():
    s = SimTest(score=7, persona="Denise, diner owner", task="Set up chat", notes="Easy")
    assert s.label == "simulated"
    with pytest.raises(ValidationError):
        SimTest(score=7, persona="p", task="t", notes="n", label="real")
