import json
import sys
from types import SimpleNamespace as NS

import pytest

from mstools import budget, config, tf, tinyfish


class FakeClient:
    def __init__(self, run_status="COMPLETED", result=None, fetch_ok=(), fetch_bad=()):
        self.queued = []
        self.search = NS(query=lambda query, **kw: NS(results=[NS(title="T", url="https://a.example", snippet="s", site_name="a.example", date=None)]))
        self.fetch = NS(get_contents=lambda urls, **kw: NS(
            results=[NS(url=u, title="Page", text="hello " * 10) for u in urls if u in fetch_ok],
            errors=[NS(url=u, error="404") for u in urls if u in fetch_bad]))
        self.agent = NS(queue=self._queue)
        self.runs = NS(get=lambda run_id: NS(run_id=run_id, status=run_status, result=result, error=None,
                                             streaming_url="https://stream.example/x"))

    def _queue(self, **kw):
        self.queued.append(kw)
        return NS(run_id="run_1", error=None)


def call(monkeypatch, capsys, fake, *argv):
    monkeypatch.setattr(tinyfish, "client", lambda: fake)
    monkeypatch.setattr(sys, "argv", ["tf", *argv])
    with pytest.raises(SystemExit) as e:
        tf.main()
    return e.value.code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_fetch_reports_failed_urls_without_raising(env, monkeypatch, capsys):
    fake = FakeClient(fetch_ok={"https://ok.example"}, fetch_bad={"https://dead.example"})
    code, out = call(monkeypatch, capsys, fake, "fetch", "https://ok.example", "https://dead.example")
    assert code == 0 and out["ok"] is True
    assert out["failed"] == ["https://dead.example"] and out["docs"][0]["url"] == "https://ok.example"


def test_fetch_whole_call_error_lists_all_failed(env, monkeypatch, capsys):
    fake = FakeClient()
    fake.fetch = NS(get_contents=lambda urls, **kw: (_ for _ in ()).throw(RuntimeError("boom")))
    code, out = call(monkeypatch, capsys, fake, "fetch", "https://maps.google.com/x")
    assert code == 0 and out["failed"] == ["https://maps.google.com/x"] and out["docs"] == []


def test_search_returns_hits(env, monkeypatch, capsys):
    code, out = call(monkeypatch, capsys, FakeClient(), "search", "AI receptionist for HVAC")
    assert code == 0 and out["hits"][0]["url"] == "https://a.example"


def approve(env, aid="ap_1", tool="chat-a", status="approved"):
    """The API records decisions in the read-only /decisions mount; the agent's own approvals/ copy is not trusted."""
    d = env["work"] / "approvals"
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{aid}.json").write_text(json.dumps({"id": aid, "tool_id": tool, "summary": "s", "status": "pending",
                                                "created_at": "2026-11-08T00:00:00Z"}))
    if status != "pending":
        (env["decisions"] / f"{aid}.json").write_text(json.dumps({"id": aid, "tool_id": tool, "status": status}))


def test_agent_start_ignores_self_approved_file(env, monkeypatch, capsys):
    approve(env, status="pending")
    (env["work"] / "approvals" / "ap_1.json").write_text(json.dumps({"id": "ap_1", "tool_id": "chat-a", "summary": "s",
                                                                      "status": "approved", "created_at": "x"}))
    fake = FakeClient()
    code, out = call(monkeypatch, capsys, fake, *START)
    assert code == 1 and "not approved" in out["error"] and fake.queued == []


START = ("agent-start", "--url", "https://v.example", "--goal", "sign up", "--tool", "chat-a", "--approval", "ap_1")


def test_agent_start_refuses_pending_approval(env, monkeypatch, capsys):
    approve(env, status="pending")
    fake = FakeClient()
    code, out = call(monkeypatch, capsys, fake, *START)
    assert code == 1 and "not approved" in out["error"] and fake.queued == []


def test_agent_start_refuses_missing_approval(env, monkeypatch, capsys):
    fake = FakeClient()
    code, out = call(monkeypatch, capsys, fake, *START)
    assert code == 1 and "approval request" in out["error"] and fake.queued == []


def test_agent_start_refuses_approval_for_other_tool(env, monkeypatch, capsys):
    approve(env, tool="chat-b")
    fake = FakeClient()
    code, out = call(monkeypatch, capsys, fake, *START)
    assert code == 1 and "chat-b" in out["error"] and fake.queued == []


def test_agent_start_allows_two_runs_per_approval_then_refuses(env, monkeypatch, capsys):
    """Sign-up, then a second run to verify the email and configure; a third needs a new yes."""
    approve(env)
    fake = FakeClient()
    small = (*START, "--max-steps", "20")
    assert call(monkeypatch, capsys, fake, *small)[0] == 0
    fake.agent = NS(queue=lambda **kw: (fake.queued.append(kw), NS(run_id="run_2", error=None))[1])
    assert call(monkeypatch, capsys, fake, *small)[0] == 0
    fake.agent = NS(queue=lambda **kw: (fake.queued.append(kw), NS(run_id="run_3", error=None))[1])
    code, out = call(monkeypatch, capsys, fake, *small)
    assert code == 1 and "already used" in out["error"] and len(fake.queued) == 2


def test_agent_start_refuses_when_budget_below_one_setup(env, monkeypatch, capsys):
    approve(env)
    budget.charge(config.owner_budget(), "tinyfish_owner", 0.80, 1.50)
    fake = FakeClient()
    code, out = call(monkeypatch, capsys, fake, *START)
    assert code == 1 and "Not enough budget" in out["error"] and fake.queued == []


def test_agent_start_reserves_max_steps(env, monkeypatch, capsys):
    approve(env)
    fake = FakeClient()
    code, out = call(monkeypatch, capsys, fake, *START)
    assert code == 0 and out["run_id"] == "run_1"
    assert fake.queued[0]["agent_config"].max_steps == 45
    assert budget.spent(config.owner_budget(), "tinyfish_owner") == pytest.approx(0.72)


def test_agent_wait_completed_blocked_is_needs_owner(env, monkeypatch, capsys):
    monkeypatch.setenv("MS_POLL_SECONDS", "0")
    fake = FakeClient(result={"blocked": True, "reason": "CAPTCHA"})
    code, out = call(monkeypatch, capsys, fake, "agent-wait", "run_1")
    assert code == 0 and out["outcome"] == "needs_owner" and out["streaming_url"].startswith("https://")
    saved = json.loads((env["work"] / "runs" / "run_1.json").read_text())
    assert saved["streaming_url"] == "https://stream.example/x"


def test_agent_wait_completed_with_result_is_done(env, monkeypatch, capsys):
    monkeypatch.setenv("MS_POLL_SECONDS", "0")
    code, out = call(monkeypatch, capsys, FakeClient(result={"account_created": True}), "agent-wait", "run_1")
    assert out["outcome"] == "done" and out["result"]["account_created"] is True
