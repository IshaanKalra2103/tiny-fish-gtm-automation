import json
import os
import subprocess
import sys
from pathlib import Path

FIXTURE = Path(__file__).parent / "fixtures" / "catalog.json"


def cli(env, module, *args, stdin=None):
    e = {**os.environ, "MS_WORK": str(env["work"]), "MS_CATALOG": str(FIXTURE),
         "MS_GLOBAL_BUDGET": str(env["budget"] / "global.json"), "MS_OWNER_ID": "o_test"}
    p = subprocess.run([sys.executable, "-m", f"mstools.{module}", *args], capture_output=True, text=True, env=e, input=stdin)
    out = json.loads(p.stdout.strip().splitlines()[-1])
    return p.returncode, out, p.stdout


def write(env, name, data):
    f = env["tmp"] / name
    f.write_text(json.dumps(data))
    return str(f)


def test_ws_save_rejects_invalid_needs(env):
    f = write(env, "n.json", {"items": [{"need_id": "reviews", "title": "t", "why": "w", "est_hours_saved_week": 1}]})
    code, out, _ = cli(env, "ws", "save", "needs", f)
    assert code == 1 and out["ok"] is False and "items" in out["error"]


def test_ws_save_setup_mode_600_and_redacted(env):
    f = write(env, "s.json", {"tool_id": "chat-a", "status": "done", "username": "u", "password": "hunter2-secret"})
    code, out, raw = cli(env, "ws", "save", "setup", f)
    path = env["work"] / "setup_chat-a.json"
    assert code == 0 and Path(out["path"]) == path
    assert os.stat(path).st_mode & 0o777 == 0o600
    assert "***" in raw and "hunter2-secret" not in raw
    assert json.loads(path.read_text())["password"] == "hunter2-secret"


def test_ws_get_returns_saved_profile(env):
    f = write(env, "p.json", {"name": "Bean", "business_type": "coffee_shop", "city": "Frederick", "state": "MD", "size": "4 staff", "summary": "Cafe"})
    cli(env, "ws", "save", "profile", f)
    code, out, _ = cli(env, "ws", "get", "profile")
    assert code == 0 and out["data"]["city"] == "Frederick"


def ids(out):
    return [t["id"] for t in out["tools"]]


def test_match_excludes_pending(env):
    code, out, _ = cli(env, "catalog", "match", "--type", "hvac", "--need", "missed-calls")
    assert code == 0 and ids(out) == ["recep-a"]


def test_match_orders_by_works_with_then_trust(env):
    _, out, _ = cli(env, "catalog", "match", "--type", "coffee_shop", "--need", "website-chat", "--works-with", "square,website")
    assert ids(out) == ["chat-c", "chat-b", "chat-a"]
    assert out["tools"][2]["can_setup"] is True and out["tools"][0]["can_setup"] is False


def test_match_other_type_returns_tools(env):
    code, out, _ = cli(env, "catalog", "match", "--type", "other", "--need", "website-chat")
    assert code == 0 and len(out["tools"]) >= 2


def test_needs_for_other_type_are_generic(env):
    _, out, _ = cli(env, "catalog", "needs", "--type", "other")
    assert [n["id"] for n in out["needs"]] == ["missed-calls", "reviews", "social-posts", "booking", "website-chat", "books"]


def test_approval_request_creates_pending(env):
    code, out, _ = cli(env, "approval", "request", "--tool", "chat-a", "--summary", "Create a free Chat-A account")
    assert code == 0 and out["status"] == "pending" and "End your turn" in out["message"]
    saved = json.loads((env["work"] / "approvals" / f"{out['approval_id']}.json").read_text())
    assert saved["status"] == "pending" and saved["tool_id"] == "chat-a"
    code, st, _ = cli(env, "approval", "status", out["approval_id"])
    assert st["approval"]["status"] == "pending"
