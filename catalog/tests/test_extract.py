import json
from pathlib import Path

from mscatalog import extract, simtest, store

FIX = Path(__file__).parent / "fixtures"


def _pages(domain="foo.com"):
    store.save_json(store.pages_dir() / f"{domain}.json", {
        "domain": domain, "pages": [{"url": f"https://{domain}", "title": "Foo", "text": "Foo answers questions."}],
        "hits": [{"query": "AI website chatbot for restaurants", "need_id": "website-chat", "business_type": "restaurant"}]})


def test_extract_validates_claude_json():
    _pages()
    out = FIX.joinpath("claude_extract.json").read_text()
    rec = extract.run("foo.com", runner=lambda prompt, schema: out)
    draft = rec["draft"]
    assert rec["is_tool"] is True
    assert draft["id"] == "foo-chat"
    assert draft["need_ids"] == ["website-chat"]
    # The extractor never turns on agent setup; the human reviewer does.
    assert draft["setup"]["agent_setup"] is False and draft["setup"]["playbook"] is None
    assert json.loads(store.records_dir().joinpath("foo.com.json").read_text())["draft"]["name"] == "Foo Chat"


def test_extract_rejects_bad_claude_json():
    _pages()
    bad = json.dumps({"type": "result", "structured_output": {"is_tool": True, "reason": "x", "tool": {"name": "Foo"}}})
    rec = extract.run("foo.com", runner=lambda prompt, schema: bad)
    assert rec["is_tool"] is False and "invalid" in rec["reason"]


def _vetted(domain="foo.com", free_plan=True, free_trial=False, types=("salon", "restaurant")):
    _pages(domain)
    tool = {
        "id": "foo-chat", "name": "Foo Chat", "vendor": "Foo Labs", "url": f"https://{domain}",
        "need_ids": ["booking"], "business_types": list(types), "what_it_does": "Books appointments.",
        "price": {"free_plan": free_plan, "from_usd_month": 20, "pricing_url": None, "notes": ""},
        "setup": {"minutes": 10, "difficulty": "easy", "agent_setup": False, "playbook": None},
        "integrations": [], "trust": {"score": 60, "badge": "caution", "signals": {}}, "sim_test": None,
        "sources": [], "status": "pending", "reviewed_by": None, "reviewed_at": None}
    store.save_json(store.records_dir() / f"{domain}.json", {
        "domain": domain, "is_tool": True, "draft": {"facts": {"free_trial": free_trial}}, "tool": tool})


def test_simtest_skipped_without_free_plan():
    _vetted(free_plan=False, free_trial=False)
    calls = []
    rec = simtest.run("foo.com", runner=lambda prompt, schema: calls.append(prompt) or "{}")
    assert rec["tool"]["sim_test"] is None
    assert calls == []


def test_simtest_uses_type_persona():
    _vetted(free_plan=False, free_trial=True)
    seen = []

    def fake(prompt, schema):
        seen.append(prompt)
        return json.dumps({"type": "result", "structured_output": {"score": 7, "task": "Set up online booking", "notes": "The calendar sync step may confuse her."}})

    rec = simtest.run("foo.com", runner=fake)
    persona = store.load_needs()["personas"]["salon"]
    assert persona in seen[0]
    st = rec["tool"]["sim_test"]
    assert st["score"] == 7 and st["persona"] == persona and st["label"] == "simulated"
