"""The one LLM adapter. Provider chosen by env so the harness can swap vendors without touching roles.

    GTM_LLM_PROVIDER = openai (default) | anthropic | codex
    GTM_MODEL_SMART / GTM_MODEL_FAST   override the per-provider defaults
    openai:    OPENAI_API_KEY (+ OPENAI_BASE_URL for regional projects)
    anthropic: ANTHROPIC_API_KEY
    codex:     the Codex CLI's ChatGPT login ($CODEX_HOME/auth.json, default ~/.codex), one `codex exec` per call.
               ChatGPT accounts reject gpt-6-sol/astra-class models, hence its own defaults.

Roles only call `parse(...)` with neutral content parts built by `text()` / `image()`.
TTS + word timestamps (video role) use OpenAI when available and fall back to a system voice otherwise.
"""

import base64
import json
import os
import subprocess
import tempfile
import time
from pathlib import Path
from typing import TypeVar

import httpx
from pydantic import BaseModel

from .run import Run

T = TypeVar("T", bound=BaseModel)
PROVIDER = os.environ.get("GTM_LLM_PROVIDER", "openai").lower()
DEFAULTS = {"openai": ("gpt-6.1-sol", "gpt-6-luna"), "anthropic": ("claude-opus-5-5", "claude-sonnet-5-5"),
            "codex": ("gpt-5.6-terra", "gpt-6-luna")}
SMART = os.environ.get("GTM_MODEL_SMART") or DEFAULTS[PROVIDER][0]
FAST = os.environ.get("GTM_MODEL_FAST") or DEFAULTS[PROVIDER][1]
CODEX_TIMEOUT = int(os.environ.get("GTM_CODEX_TIMEOUT", "600"))
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
    if PROVIDER == "codex":
        out, tokens = _codex(model, instructions, content, fmt, "medium" if tier == "smart" else "low")
    else:
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


def codex_home() -> Path:
    """Private CODEX_HOME for worker calls. Only auth.json is shared, as a symlink, so token refreshes reach the
    user's own login; sessions, logs and sqlite state stay out of the user's ~/.codex (a bind mount in the
    harness, where sqlite locking across the VM boundary is not safe). Same pattern as Paperclip's codex_local."""
    src = Path(os.environ.get("CODEX_HOME") or "~/.codex").expanduser()
    home = Path(os.environ.get("GTM_CODEX_HOME") or "~/.cache/gtm-codex").expanduser()
    home.mkdir(parents=True, exist_ok=True)
    link = home / "auth.json"
    if home.resolve() != src.resolve() and not link.is_symlink() and not link.exists():
        try:
            link.symlink_to(src / "auth.json")
        except FileExistsError:  # another worker linked it first
            pass
    return home


def _codex(model, instructions, content, fmt, effort):
    """Structured output via `codex exec --output-schema` on the user's ChatGPT subscription (no API key)."""
    from openai.lib._pydantic import to_strict_json_schema

    with tempfile.TemporaryDirectory(prefix="gtm-codex-") as tmp:
        d = Path(tmp)
        (d / "schema.json").write_text(json.dumps(to_strict_json_schema(fmt)))
        cmd = ["codex", "exec"]
        for i, c in enumerate(c for c in content if c["type"] == "image"):
            p = d / f"image{i}.{c['mime'].split('/')[-1]}"
            p.write_bytes(base64.b64decode(c["data"]))
            cmd += ["-i", str(p)]
        cmd += ["--ephemeral", "--ignore-user-config", "--ignore-rules", "--skip-git-repo-check", "-s", "read-only",
                "-C", tmp, "-m", model, "-c", f'model_reasoning_effort="{effort}"',
                "--output-schema", str(d / "schema.json"), "-o", str(d / "out.json"), "--json", "-"]
        prompt = "\n\n".join([instructions, "Answer from the content below. Do not run commands or use tools.",
                              *(c["text"] for c in content if c["type"] == "text")])
        # An OPENAI_API_KEY in the env would switch the CLI off the ChatGPT login.
        env = {k: v for k, v in os.environ.items() if k not in ("OPENAI_API_KEY", "OPENAI_BASE_URL")}
        env["CODEX_HOME"] = str(codex_home())
        r = subprocess.run(cmd, input=prompt, capture_output=True, text=True, env=env, timeout=CODEX_TIMEOUT)
        events = [json.loads(line) for line in r.stdout.splitlines() if line.startswith("{")]
        out = d / "out.json"
        if r.returncode != 0 or not out.exists() or not out.read_text().strip():
            errs = [(e.get("error") or {}).get("message") or e.get("message") for e in events
                    if e.get("type") in ("turn.failed", "error")]
            raise RuntimeError(f"codex {model} failed: {next(filter(None, reversed(errs)), None) or r.stderr.strip()[-300:] or f'exit {r.returncode}'}")
        usage = next((e.get("usage") or {} for e in reversed(events) if e.get("type") == "turn.completed"), {})
        return fmt.model_validate_json(out.read_text()), usage.get("input_tokens", 0) + usage.get("output_tokens", 0)
