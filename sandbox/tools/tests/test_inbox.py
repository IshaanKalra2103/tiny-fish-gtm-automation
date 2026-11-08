from datetime import datetime, timezone
from types import SimpleNamespace as NS

from mstools.inbox import full_obj


def test_inbox_extracts_codes_and_links():
    m = NS(message_id="m1", from_="Chat-A <hi@chat-a.example>", subject="Your code is 482913", preview="",
           created_at=datetime.now(timezone.utc), to=["x@agentmail.to"],
           extracted_text="Use 482913 to confirm. Or click https://chat-a.example/verify?t=abc", text=None,
           html='<a href="https://chat-a.example/verify?t=abc">Verify</a>')
    out = full_obj(m)
    assert out["codes"] == ["482913"]
    assert out["links"] == ["https://chat-a.example/verify?t=abc"]
