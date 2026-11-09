"""Model-supplied ids must never steer a write outside the owner's file names (security finding A)."""
import json

import pytest

from mstools import ws
from test_cli_tools import cli, write
from test_preview import no_http, run_cli
from test_tf import FakeClient, call as tf_call

LEDGER = {"usd": {"video_global": 19.9, "tinyfish_owner": 1.2}, "counts": {"previews": 2}}


def seed(path):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(LEDGER))
    return path.read_text()


def test_ws_save_preview_cannot_overwrite_global_budget(env):
    target = env["budget"] / "global.json"
    before = seed(target)
    f = write(env, "p.json", {"tool_id": "x/../../budget/global", "prompt": "p", "status": "completed"})
    code, out, _ = cli(env, "ws", "save", "preview", f)
    assert code == 1 and out["ok"] is False and "tool_id" in out["error"]
    assert target.read_text() == before


@pytest.mark.parametrize("tool_id,target", [("x/../budget", "budget.json"), ("x/../runs/run_1", "runs/run_1.json")])
def test_ws_save_setup_cannot_reset_owner_ledgers(env, tool_id, target):
    path = env["work"] / target
    before = seed(path)
    f = write(env, "s.json", {"tool_id": tool_id, "status": "planned"})
    code, out, _ = cli(env, "ws", "save", "setup", f)
    assert code == 1 and out["ok"] is False and "tool_id" in out["error"]
    assert path.read_text() == before


def test_preview_make_tool_flag_cannot_overwrite_global_budget(env, monkeypatch, capsys):
    target = env["budget"] / "global.json"
    before = seed(target)  # at the cap, so make() goes straight to saving a "capped" record
    code, out = run_cli(monkeypatch, capsys, no_http, "--tool", "x/../../budget/global", "--prompt", "p")
    assert code == 1 and out["ok"] is False and "tool id" in out["error"]
    assert target.read_text() == before


def test_reads_reject_traversal_ids(env):
    seed(env["budget"] / "global.json")
    (env["work"] / "approvals").mkdir()  # exists after the first `approval request`
    (env["work"] / "preview_x").mkdir()  # left behind by an earlier traversal write
    code, out, _ = cli(env, "ws", "get", "preview", "--id", "x/../../budget/global")
    assert code == 1 and out["ok"] is False and "usd" not in out.get("data", {})
    code, out, _ = cli(env, "approval", "status", "../../budget/global")
    assert code == 1 and out["ok"] is False and "approval" not in out


def test_tf_agent_wait_run_id_cannot_reset_owner_budget(env, monkeypatch, capsys):
    target = env["work"] / "budget.json"
    before = seed(target)
    code, out = tf_call(monkeypatch, capsys, FakeClient(), "agent-wait", "../budget")
    assert code == 1 and out["ok"] is False and "run id" in out["error"]
    assert target.read_text() == before


def test_path_for_refuses_paths_outside_work(env):
    with pytest.raises(ws.ToolError):
        ws.path_for("preview", {"tool_id": "../../etc/x"}, env["work"])
    # second wall: a valid id whose file is a link out of the workspace
    seed(env["budget"] / "global.json")
    (env["work"] / "preview_chat-a.json").symlink_to(env["budget"] / "global.json")
    with pytest.raises(ws.ToolError):
        ws.path_for("preview", {"tool_id": "chat-a"}, env["work"])
