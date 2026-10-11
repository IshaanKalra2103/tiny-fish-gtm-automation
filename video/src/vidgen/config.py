"""Paths, secrets and defaults shared by every vidgen module."""

import glob
import os
import shutil
import subprocess
from pathlib import Path

from dotenv import load_dotenv

PACKAGE_ROOT = Path(__file__).resolve().parents[2]  # video/
PROJECT_ROOT = PACKAGE_ROOT.parent  # /workspace inside the harness container
FONTS = Path(__file__).resolve().parent / "fonts"

load_dotenv(PACKAGE_ROOT / ".env")

# Downloaded footage, images and TTS live here (gitignored). Shared with the
# harness container through the /workspace mount, so nothing is fetched twice.
ASSETS = Path(os.environ.get("VIDGEN_ASSETS", PACKAGE_ROOT / "assets"))
CACHE = ASSETS / "cache"

W, H, FPS = 1080, 1920, 30


class VidgenError(RuntimeError):
    pass


def runs_dir() -> Path:
    return Path(os.environ.get("GTM_RUNS_DIR", PROJECT_ROOT / "runs"))


def secret(name: str) -> str | None:
    """Env var (or video/.env) first, then the macOS Keychain item whose service is `name`.

    The harness container has no Keychain, so there the value comes from harness/.env.
    """
    if value := os.environ.get(name, "").strip():
        return value
    if shutil.which("security"):
        r = subprocess.run(["security", "find-generic-password", "-s", name, "-w"],
                           capture_output=True, text=True)
        if r.returncode == 0 and r.stdout.strip():
            return r.stdout.strip()
    return None


def tool(name: str) -> str:
    path = shutil.which(name)
    if not path and name == "ffmpeg":
        # The harness container has no system ffmpeg; reuse the static build imageio-ffmpeg ships in a venv.
        env = os.environ.get("VIDGEN_FFMPEG") or os.environ.get("IMAGEIO_FFMPEG_EXE")
        found = [env] if env else sorted(glob.glob("/paperclip/venvs/*/lib/python*/site-packages/"
                                                   "imageio_ffmpeg/binaries/ffmpeg-*"))
        path = next((p for p in found if p and os.access(p, os.X_OK)), None)
    if not path:
        raise VidgenError(f"{name} not found on PATH (macOS: brew install {name}; Debian: apt-get install {name})")
    return path


def run(cmd: list[str], what: str) -> subprocess.CompletedProcess:
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        tail = "\n".join(r.stderr.strip().splitlines()[-12:])
        raise VidgenError(f"{what} failed:\n{tail}")
    return r


def probe_duration(path: Path) -> float:
    r = run([tool("ffprobe"), "-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", str(path)],
            f"ffprobe {path.name}")
    return float(r.stdout.strip())
