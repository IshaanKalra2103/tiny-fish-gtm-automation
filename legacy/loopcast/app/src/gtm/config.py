"""Paths, models, budgets and the default campaign brief."""

import os
from pathlib import Path

from dotenv import load_dotenv

APP_DIR = Path(__file__).resolve().parents[2]
ROOT = APP_DIR.parent
load_dotenv(APP_DIR / ".env")
if os.environ.get("GTM_ENV_FILE"):  # optional extra env file for keys kept outside the repo
    load_dotenv(os.environ["GTM_ENV_FILE"])
# In the harness the key arrives as GTM_OPENAI_*: a container-wide OPENAI_API_KEY makes codex_local agents
# (the Orchestrator) drop their ChatGPT login and fail with 401. Only this worker process sees OPENAI_*.
for _k in ("OPENAI_API_KEY", "OPENAI_BASE_URL"):
    if os.environ.get(f"GTM_{_k}") and not os.environ.get(_k):
        os.environ[_k] = os.environ[f"GTM_{_k}"]

# Shared with brightdata/ and the Paperclip harness when running inside the monorepo.
RUNS_DIR = Path(os.environ.get("GTM_RUNS_DIR") or (ROOT / "runs" if (ROOT / "brightdata").is_dir() else APP_DIR / "runs"))
BRIGHTDATA_DIR = Path(os.environ.get("GTM_BRIGHTDATA_DIR")
                      or next((d for d in (APP_DIR / "brightdata", ROOT / "brightdata") if d.is_dir()), ROOT / "brightdata"))
MEMORY_FILE = RUNS_DIR / "learnings.json"

TTS_MODEL = os.environ.get("GTM_TTS_MODEL", "gpt-4o-mini-tts")

TINYFISH_BUDGET_USD = float(os.environ.get("GTM_TINYFISH_BUDGET_USD", "1.50"))
# minimal (default, demo-friendly): Search + Fetch + Browser + a small Bright Data sample, about 1-2 min.
# full: also runs the TinyFish Agent on YouTube Shorts filters (slow: 5-11 min, ~$0.50-0.80).
RESEARCH_MODE = os.environ.get("GTM_RESEARCH_MODE", "minimal").lower()
# advisory (default, demo): QA scores and flags every draft but never blocks; the best draft goes to the human
# approval with its flags. strict: a draft must pass QA before it can be packaged.
QA_GATE = os.environ.get("GTM_QA_GATE", "advisory").lower()


def qa_ok(qa: dict | None) -> bool:
    return bool(qa) and (bool(qa.get("passed")) or QA_GATE == "advisory")
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
