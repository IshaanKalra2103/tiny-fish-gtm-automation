"""Compatibility import; the worker client lives in the app package."""
import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "app" / "src"))
from gtm.paperclip_agent import PaperclipError, PaperclipRun  # noqa: F401,E402
