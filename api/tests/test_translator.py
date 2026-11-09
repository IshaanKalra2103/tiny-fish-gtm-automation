from msapi.turns import Translator


def _assistant_text(text):
    return {"type": "assistant", "message": {"content": [{"type": "text", "text": text}]}}


def test_agent_narration_is_not_shown_as_status():
    # The agent's in-between text is for itself ("save was blocked, I'll use Write"); owners see tool labels only.
    out = Translator()(_assistant_text("The profile save was blocked, so I'll use the Write tool instead."))
    assert out == []


def test_tool_labels_still_become_status():
    ev = {"type": "assistant", "message": {"content": [
        {"type": "tool_use", "id": "t1", "name": "Bash", "input": {"command": "tf fetch https://x.example"}}]}}
    assert Translator()(ev) == [{"type": "status", "text": "Reading pages"}]


def test_done_reply_has_no_markdown():
    ev = {"type": "result", "subtype": "success", "is_error": False,
          "result": "## Try this first\nI'd try a **website chat helper**. My pick is __Chat-A__.\n- free plan"}
    assert Translator()(ev) == [{"type": "done",
                                 "reply": "Try this first\nI'd try a website chat helper. My pick is Chat-A.\n- free plan"}]
