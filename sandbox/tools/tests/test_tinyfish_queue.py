from types import SimpleNamespace

from mstools import tinyfish


def test_queue_agent_sends_no_custom_max_steps(monkeypatch):
    """TinyFish rejects agent_config.max_steps for accounts outside its beta, so never send it."""
    seen = {}

    def queue(**kw):
        seen.update(kw)
        return SimpleNamespace(run_id="run_1", error=None)

    monkeypatch.setattr(tinyfish, "client", lambda: SimpleNamespace(agent=SimpleNamespace(queue=queue)))
    assert tinyfish.queue_agent("https://example.com", "goal", None, 45) == "run_1"
    assert "agent_config" not in seen
