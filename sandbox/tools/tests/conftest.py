import pytest


@pytest.fixture
def env(tmp_path, monkeypatch):
    work = tmp_path / "work"
    work.mkdir()
    budget = tmp_path / "budget"
    budget.mkdir()
    decisions = tmp_path / "decisions"
    decisions.mkdir()
    monkeypatch.setenv("MS_DECISIONS", str(decisions))
    monkeypatch.setenv("MS_WORK", str(work))
    monkeypatch.setenv("MS_GLOBAL_BUDGET", str(budget / "global.json"))
    monkeypatch.setenv("MS_OWNER_ID", "o_test")
    return {"work": work, "budget": budget, "decisions": decisions, "tmp": tmp_path}
