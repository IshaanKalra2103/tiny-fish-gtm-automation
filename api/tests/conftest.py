import json

import httpx
import pytest

from msapi.app import create_app
from msapi.runner import FakeRunner
from msapi.settings import Settings


def script(reply="Here is what I found.", save_kind="profile"):
    return [
        {"type": "system", "subtype": "init"},
        {"type": "assistant", "message": {"content": [{"type": "text", "text": "Reading your website now."}]}},
        {"type": "assistant", "message": {"content": [{"type": "tool_use", "id": "t1", "name": "Bash",
                                                        "input": {"command": f"ws save {save_kind} /work/tmp/x.json"}}]}},
        {"type": "user", "message": {"content": [{"type": "tool_result", "tool_use_id": "t1", "content": '{"ok": true}'}]}},
        {"type": "result", "subtype": "success", "is_error": False, "result": reply},
    ]


@pytest.fixture
def settings(tmp_path):
    return Settings(root=tmp_path, workspaces=tmp_path / "workspaces", budget=tmp_path / "budget",
                    web_url="https://web.example", web_origins=["https://web.example"], max_concurrent=2)


@pytest.fixture
def make_client(settings):
    def _make(runner=None, **kw):
        runner = runner or FakeRunner(script())
        app = create_app(runner=runner, settings=settings, **kw)
        return app, httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://t")
    return _make


async def sse_events(client, turn_id):
    r = await client.get(f"/api/turns/{turn_id}/events")
    out = []
    for line in r.text.splitlines():
        if line.startswith("data:"):
            out.append(json.loads(line[5:].strip()))
    return out
