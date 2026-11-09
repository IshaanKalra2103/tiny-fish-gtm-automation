from mstools.schemas import Signal
from mstools.trust import score_signals

from mscatalog import review, store


def _rec(domain, rid, points):
    sig = {k: Signal(points=p, max=m, value="x") for (k, m), p in zip(
        [("identity", 25), ("longevity", 15), ("data_handling", 20), ("pricing", 15), ("reviews", 15), ("viability", 10)], points)}
    tool = {"id": rid, "name": rid, "vendor": "v", "url": f"https://{domain}", "need_ids": ["website-chat"],
            "business_types": ["other"], "what_it_does": "x", "price": {"free_plan": True, "from_usd_month": None, "pricing_url": None, "notes": ""},
            "setup": {"minutes": 5, "difficulty": "easy", "agent_setup": False, "playbook": None}, "trust": score_signals(sig, False).model_dump()}
    store.save_json(store.records_dir() / f"{domain}.json", {"domain": domain, "is_tool": True, "tool": tool})


def test_review_flags_approve_reject_agent_setup():
    _rec("a.com", "a", [25, 15, 20, 15, 15, 10])
    _rec("b.com", "b", [10, 0, 10, 5, 0, 10])
    assert store.load_json(store.records_dir() / "a.com.json")["tool"]["trust"]["badge"] == "caution"
    review.apply(["a"], ["b"], ["a"], "Tester")
    a = store.load_json(store.records_dir() / "a.com.json")["tool"]
    b = store.load_json(store.records_dir() / "b.com.json")["tool"]
    assert a["status"] == "approved" and a["reviewed_by"] == "Tester" and a["reviewed_at"]
    assert a["trust"]["badge"] == "verified"
    assert a["setup"]["agent_setup"] is True and a["setup"]["playbook"] == "setup-a"
    assert b["status"] == "rejected" and b["trust"]["badge"] == "unknown"
