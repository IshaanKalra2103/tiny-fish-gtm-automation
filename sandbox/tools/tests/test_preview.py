import json
import sys

import httpx
import pytest

from mstools import budget, config, preview, ws


def run_cli(monkeypatch, capsys, handler, *argv):
    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setenv("MS_VIDEO_POLL_SECONDS", "0")
    monkeypatch.setattr(preview, "http_client", lambda: httpx.Client(transport=httpx.MockTransport(handler)))
    monkeypatch.setattr(sys, "argv", ["preview", "make", *argv])
    with pytest.raises(SystemExit) as e:
        preview.main()
    return e.value.code, json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def no_http(request):
    raise AssertionError(f"unexpected HTTP call {request.url}")


def happy(seen, final_status="completed"):
    def handler(request: httpx.Request):
        if request.method == "POST":
            seen["body"] = json.loads(request.content)
            seen["auth"] = request.headers.get("authorization")
            return httpx.Response(202, json={"id": "v1", "status": "pending", "polling_url": "https://openrouter.ai/api/v1/videos/v1"})
        if request.url.path.endswith("/videos/v1"):
            if final_status != "completed":
                return httpx.Response(200, json={"id": "v1", "status": final_status, "error": "content filter"})
            return httpx.Response(200, json={"id": "v1", "status": "completed", "unsigned_urls": ["https://cdn.example/v1.mp4"], "usage": {"cost": 0.34}})
        if request.url.host == "cdn.example":
            return httpx.Response(200, content=b"\x00\x00\x00\x18ftypmp42fake")
        return httpx.Response(404)
    return handler


ARGS = ("--tool", "chat-a", "--prompt", "A barista smiles at a tablet")


def test_preview_cached_returns_without_http(env, monkeypatch, capsys):
    (env["work"] / "preview_chat-a.mp4").write_bytes(b"x")
    ws.save("preview", {"tool_id": "chat-a", "prompt": "p", "status": "completed", "video_file": "preview_chat-a.mp4", "cost_usd": 0.3})
    code, out = run_cli(monkeypatch, capsys, no_http, *ARGS)
    assert code == 0 and out["cached"] is True and out["preview"]["status"] == "completed"


def test_preview_refuses_over_global_cap(env, monkeypatch, capsys):
    budget.charge(config.global_budget(), "video_global", 19.90, 20.0)
    code, out = run_cli(monkeypatch, capsys, no_http, *ARGS)
    assert code == 0 and out["preview"]["status"] == "capped"


def test_preview_refuses_third_live_for_owner(env, monkeypatch, capsys):
    budget.bump_count(config.owner_budget(), "previews", 2)
    budget.bump_count(config.owner_budget(), "previews", 2)
    code, out = run_cli(monkeypatch, capsys, no_http, *ARGS)
    assert out["preview"]["status"] == "capped"


def test_preview_seconds_clamped_to_8(env, monkeypatch, capsys):
    seen = {}
    code, out = run_cli(monkeypatch, capsys, happy(seen), *ARGS, "--seconds", "12")
    assert code == 0 and seen["body"]["duration"] == 8
    assert seen["body"]["resolution"] == "720p" and seen["body"]["aspect_ratio"] == "16:9" and seen["body"]["generate_audio"] is False
    assert seen["auth"] == "Bearer test-key"
    assert out["preview"]["status"] == "completed" and out["preview"]["cost_usd"] == pytest.approx(0.34)
    assert (env["work"] / "preview_chat-a.mp4").read_bytes().startswith(b"\x00\x00\x00\x18ftyp")
    assert budget.spent(config.global_budget(), "video_global") == pytest.approx(0.34)


def test_preview_failed_job_records_failed(env, monkeypatch, capsys):
    code, out = run_cli(monkeypatch, capsys, happy({}, final_status="failed"), *ARGS)
    assert out["preview"]["status"] == "failed"
    assert ws.load("preview", "chat-a")["status"] == "failed"


def test_preview_seconds_snap_to_model_durations(env, monkeypatch, capsys):
    seen = {}
    run_cli(monkeypatch, capsys, happy(seen), *ARGS, "--seconds", "5")
    assert seen["body"]["duration"] == 4
    assert seen["body"]["model"] == "google/veo-3.1-lite"
