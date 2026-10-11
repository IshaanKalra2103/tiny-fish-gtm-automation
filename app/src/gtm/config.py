"""Paths, models, budgets and the default campaign brief."""

import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
load_dotenv(APP_DIR / ".env")
if os.environ.get("GTM_ENV_FILE"):  # optional extra env file for keys kept outside the repo
    load_dotenv(os.environ["GTM_ENV_FILE"])

# Shared with brightdata/ and the Paperclip harness when running inside the monorepo.
RUNS_DIR = Path(os.environ.get("GTM_RUNS_DIR") or (ROOT / "runs" if (ROOT / "brightdata").is_dir() else APP_DIR / "runs"))
BRIGHTDATA_DIR = Path(os.environ.get("GTM_BRIGHTDATA_DIR")
                      or next((d for d in (APP_DIR / "brightdata", ROOT / "brightdata") if d.is_dir()), ROOT / "brightdata"))
MEMORY_FILE = RUNS_DIR / "learnings.json"

TTS_MODEL = os.environ.get("GTM_TTS_MODEL", "gpt-4o-mini-tts")

TINYFISH_BUDGET_USD = float(os.environ.get("GTM_TINYFISH_BUDGET_USD", "1.50"))
AGENT_USD_PER_STEP = 0.016
BROWSER_USD_PER_MIN = 0.002

MAX_VERSIONS = 3  # v1 + up to two QA-driven revisions
MAX_VIDEO_SECONDS = 30

DEFAULT_BRIEF = {
    "brand": "TinyFish",
    "brand_url": "https://www.tinyfish.ai/",
    "niche": "AI browser agents",
    "audience": "developers building AI agents that need the live web",
    "goal": "drive developer signups for TinyFish",
}
