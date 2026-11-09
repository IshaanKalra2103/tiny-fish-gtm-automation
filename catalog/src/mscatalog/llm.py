"""Headless Claude Code on the host: no tools, no MCP servers, no session saved, run from an empty folder."""
import json
import subprocess
import tempfile
from pathlib import Path

MODEL = "claude-sonnet-5-5"
_SCRATCH = Path(tempfile.gettempdir()) / "mscatalog-claude-cwd"


def inline_refs(schema: dict) -> dict:
    """Pydantic puts nested models under $defs; give the CLI one self-contained schema."""
    defs = schema.pop("$defs", {})

    def walk(node):
        if isinstance(node, dict):
            if "$ref" in node:
                return walk(dict(defs[node["$ref"].split("/")[-1]]))
            return {k: walk(v) for k, v in node.items() if k != "title"}
        if isinstance(node, list):
            return [walk(v) for v in node]
        return node

    return walk(schema)


def claude_cli(prompt: str, schema: dict, timeout: int = 240) -> str:
    _SCRATCH.mkdir(parents=True, exist_ok=True)
    args = ["claude", "-p", "--model", MODEL, "--output-format", "json", "--json-schema", json.dumps(schema),
            "--tools", "", "--strict-mcp-config", "--no-session-persistence"]
    r = subprocess.run(args, input=prompt, capture_output=True, text=True, timeout=timeout, cwd=_SCRATCH)
    return r.stdout


def structured(stdout: str) -> dict:
    """The CLI's JSON envelope carries the schema-shaped answer in structured_output."""
    env = json.loads(stdout)
    out = env.get("structured_output")
    if out is None and isinstance(env.get("result"), str) and env["result"].strip().startswith("{"):
        out = json.loads(env["result"])
    if not isinstance(out, dict):
        raise ValueError(f"no structured output (subtype={env.get('subtype')})")
    return out
