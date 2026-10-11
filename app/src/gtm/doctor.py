"""Readiness checks; report presence and paths, never credential values."""

import importlib.util
import os
import shutil

from . import config


def inspect():
    checks = []
    def add(name, ok, fix, required=True):
        checks.append({"name": name, "ok": bool(ok), "required": required, "fix": "" if ok else fix})
    provider = os.environ.get("GTM_LLM_PROVIDER", "openai")
    add("llm_provider", provider in ("openai", "anthropic"), "Set GTM_LLM_PROVIDER to openai or anthropic")
    key = "ANTHROPIC_API_KEY" if provider == "anthropic" else "OPENAI_API_KEY"
    add("tinyfish_credentials", os.environ.get("TINYFISH_API_KEY"), "Supply TINYFISH_API_KEY to the worker")
    add("llm_credentials", os.environ.get(key), f"Supply {key} to the worker environment")
    for module in ("tinyfish", "openai", "pydantic", "moviepy", "PIL"):
        add(module, importlib.util.find_spec(module) is not None, "Run uv sync --project app --frozen")
    add("node", shutil.which("node"), "Install Node for browser capture")
    parent = config.RUNS_DIR if config.RUNS_DIR.exists() else config.RUNS_DIR.parent
    add("artifact_directory", os.access(parent, os.W_OK), f"Make {parent} writable by the worker")
    add("brightdata_gateway", (config.BRIGHTDATA_DIR / "pyproject.toml").exists(), "Mount brightdata/ alongside app/", False)
    add("system_voice", shutil.which("say") or shutil.which("espeak-ng"), "Install espeak-ng for TTS fallback", False)
    return {"ok": all(c["ok"] for c in checks if c["required"]), "checks": checks,
            "runs_dir": str(config.RUNS_DIR), "memory_file": str(config.MEMORY_FILE), "llm_provider": provider}
