"""Reference images (people, products) generated with the Codex CLI's image generation.

Uses whatever Codex login the process has (host ~/.codex, or CODEX_HOME in the harness).
About 45s per image. Codex saves images under $CODEX_HOME/generated_images/; we copy the new one out.
"""

import os
import shutil
import subprocess
import time
from pathlib import Path

from .config import VidgenError, tool


def generate(prompt: str, out: Path, timeout: int = 300, images: list[str] | None = None) -> Path:
    """`images`: local files Codex sees as input (e.g. the real product packshot to hold)."""
    home = Path(os.environ.get("CODEX_HOME", Path.home() / ".codex"))
    start = time.time()
    r = subprocess.run(
        [tool("codex"), "exec", "--skip-git-repo-check", "-s", "read-only",
         f"Generate one photorealistic vertical 9:16 image: {prompt}. "
         "Generate the image only; don't write any files or code.",
         *[a for img in (images or []) for a in ("-i", img)]],  # after the prompt: -i takes several files
        capture_output=True, text=True, timeout=timeout, stdin=subprocess.DEVNULL)
    new = [p for p in (home / "generated_images").glob("*/*") if p.is_file() and p.stat().st_mtime >= start - 1]
    if r.returncode != 0 or not new:
        tail = "\n".join((r.stderr or r.stdout).strip().splitlines()[-6:])
        raise VidgenError(f"codex image generation failed (exit {r.returncode}): {tail}")
    out.parent.mkdir(parents=True, exist_ok=True)
    src = max(new, key=lambda p: p.stat().st_mtime)
    shutil.copyfile(src, out.with_suffix(src.suffix))
    return out.with_suffix(src.suffix)
