#!/usr/bin/env -S uv run --script
# /// script
# requires-python = ">=3.11"
# dependencies = []
# ///
"""Device vault for the GTM harness: keeps every token / session file in the macOS Keychain.

The harness needs a handful of gitignored secret files (API keys, Paperclip board key, Photon project
secret, fal/Vizard OAuth sessions, ...). `capture` copies each one into the login Keychain;
`restore` writes them back, so a fresh checkout (or a wiped file) works out of the box on this Mac.
Values never touch stdout; output is one JSON line of names and states.

    uv run harness/vault.py list                 # which files exist, which are in the vault
    uv run harness/vault.py capture              # file -> Keychain (overwrites vault entries)
    uv run harness/vault.py restore [--force]    # Keychain -> file (only missing files unless --force)
    uv run harness/vault.py add <path>           # vault another secret file (e.g. exported cookies JSON)

Not here on purpose: Codex and Claude logins. Codex keeps ~/.codex/auth.json (mounted into the
container), and the Claude subscription token lives in Paperclip's own secret store on the data volume.
"""

import base64
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SERVICE = "gtm-harness"
MANIFEST = ROOT / "harness" / "vault.json"  # extra paths added with `add` (names only, no secrets)
DEFAULT = [
    "harness/.env",
    "harness/state/admin.json",
    "harness/state/board.json",
    "harness/state/integration.env",
    "harness/state/paperclip.json",
    "photon/.env",
    "video/.fal/session.json",
    "video/.vizard/session.json",
    "agentmail/.env",
    "brightdata/.env",
]


def paths() -> list[str]:
    extra = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
    return list(dict.fromkeys(DEFAULT + extra))


def keychain_get(name: str) -> bytes | None:
    r = subprocess.run(["security", "find-generic-password", "-s", SERVICE, "-a", name, "-w"],
                       capture_output=True, text=True)
    return base64.b64decode(r.stdout.strip()) if r.returncode == 0 and r.stdout.strip() else None


def keychain_put(name: str, data: bytes) -> None:
    r = subprocess.run(["security", "add-generic-password", "-U", "-s", SERVICE, "-a", name,
                        "-l", f"{SERVICE}: {name}", "-w", base64.b64encode(data).decode()],
                       capture_output=True, text=True)
    if r.returncode != 0:
        raise RuntimeError(f"keychain write failed for {name}: {r.stderr.strip()[:200]}")


def main() -> None:
    cmd = sys.argv[1] if len(sys.argv) > 1 else "list"
    out: dict = {"ok": True, "cmd": cmd}
    if cmd == "add":
        rel = str(Path(sys.argv[2]).resolve().relative_to(ROOT))
        extra = json.loads(MANIFEST.read_text()) if MANIFEST.exists() else []
        MANIFEST.write_text(json.dumps(sorted(set(extra + [rel])), indent=1) + "\n")
        keychain_put(rel, (ROOT / rel).read_bytes())
        out["added"] = rel
    elif cmd == "list":
        out["items"] = {p: {"file": (ROOT / p).exists(), "vault": keychain_get(p) is not None} for p in paths()}
    elif cmd == "capture":
        out["captured"], out["skipped_missing"] = [], []
        for p in paths():
            f = ROOT / p
            if f.exists():
                keychain_put(p, f.read_bytes())
                out["captured"].append(p)
            else:
                out["skipped_missing"].append(p)
    elif cmd == "restore":
        force = "--force" in sys.argv
        out["restored"], out["kept"], out["not_in_vault"] = [], [], []
        for p in paths():
            f = ROOT / p
            if f.exists() and not force:
                out["kept"].append(p)
                continue
            data = keychain_get(p)
            if data is None:
                out["not_in_vault"].append(p)
                continue
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_bytes(data)
            f.chmod(0o600)
            out["restored"].append(p)
    else:
        out = {"ok": False, "error": f"unknown command {cmd!r}; use list|capture|restore|add"}
    print(json.dumps(out))
    sys.exit(0 if out["ok"] else 1)


if __name__ == "__main__":
    main()
