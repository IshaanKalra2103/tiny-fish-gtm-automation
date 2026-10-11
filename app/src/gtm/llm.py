"""The one LLM adapter. Provider chosen by env so the harness can swap vendors without touching roles.

    GTM_LLM_PROVIDER = openai (default) | anthropic
    GTM_MODEL_SMART / GTM_MODEL_FAST   override the per-provider defaults
    openai:    OPENAI_API_KEY (+ OPENAI_BASE_URL for regional projects)
    anthropic: ANTHROPIC_API_KEY

Roles only call `parse(...)` with neutral content parts built by `text()` / `image()`.
TTS + word timestamps (video role) use OpenAI when available and fall back to a system voice otherwise.
"""

import base64
import os
import time
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel

from .run import Run

T = TypeVar("T", bound=BaseModel)
PROVIDER = os.environ.get("GTM_LLM_PROVIDER", "openai").lower()
DEFAULTS = {"openai": ("gpt-6.1-sol", "gpt-6-luna"), "anthropic": ("claude-opus-5-5", "claude-sonnet-5-5")}
SMART = os.environ.get("GTM_MODEL_SMART") or DEFAULTS[PROVIDER][0]
FAST = os.environ.get("GTM_MODEL_FAST") or DEFAULTS[PROVIDER][1]
_openai = None


def openai_client():
    global _openai
    if _openai is None:
        from openai import OpenAI

        _openai = OpenAI()
    return _openai


def text(s: str) -> dict:
    return {"type": "text", "text": s}


def image(path_or_bytes: Path | bytes, mime: str = "image/jpeg") -> dict:
    data = path_or_bytes if isinstance(path_or_bytes, bytes) else Path(path_or_bytes).read_bytes()
    return {"type": "image", "mime": mime, "data": base64.b64encode(data).decode()}


def parse(run: Run, role: str, tier: str, instructions: str, content: list[dict], fmt: type[T]) -> T:
    """tier: 'smart' or 'fast'."""
    model = SMART if tier == "smart" else FAST
    t0 = time.time()
    out, tokens = (_anthropic if PROVIDER == "anthropic" else _openai_parse)(model, instructions, content, fmt)
    run.charge("llm", 0.0, tokens=tokens)
    run.log(role, f"{PROVIDER}:{model} -> {fmt.__name__}", primitive="llm", tokens=tokens, seconds=round(time.time() - t0, 1))
    return out


def _openai_parse(model, instructions, content, fmt):
    parts = [{"type": "input_text", "text": c["text"]} if c["type"] == "text"
             else {"type": "input_image", "image_url": f"data:{c['mime']};base64,{c['data']}"} for c in content]
    r = openai_client().responses.parse(model=model, instructions=instructions,
                                        input=[{"role": "user", "content": parts}], text_format=fmt)
    if r.output_parsed is None:
        raise RuntimeError(f"{model} returned no parsed {fmt.__name__}")
    return r.output_parsed, (r.usage.total_tokens if r.usage else 0)


def _anthropic(model, instructions, content, fmt):
    """Structured output via a forced tool call (no SDK needed)."""
    parts = [c if c["type"] == "text" else
             {"type": "image", "source": {"type": "base64", "media_type": c["mime"], "data": c["data"]}} for c in content]
    r = httpx.post("https://api.anthropic.com/v1/messages", timeout=300, headers={
        "x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01", "content-type": "application/json"},
        json={"model": model, "max_tokens": 8000, "system": instructions,
              "tools": [{"name": "emit", "description": f"Return the {fmt.__name__}", "input_schema": fmt.model_json_schema()}],
              "tool_choice": {"type": "tool", "name": "emit"}, "messages": [{"role": "user", "content": parts}]})
    r.raise_for_status()
    body = r.json()
    block = next(b for b in body["content"] if b["type"] == "tool_use")
    usage = body.get("usage", {})
    return fmt.model_validate(block["input"]), usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
