"""Paths, caps and names shared by every MainStreet AI tool CLI. Paths come from the environment."""
import os
from pathlib import Path

APP_NAME = "MainStreet AI"

CAPS = {"tinyfish_owner": 1.50, "setup": 1.00, "video_global": 20.00}
AGENT_USD_PER_STEP = 0.016
SETUP_MAX_STEPS = 60

PREVIEW_MAX_SECONDS = 8
PREVIEW_MIN_SECONDS = 2
PREVIEWS_PER_OWNER = 2
PREVIEWS_PER_DAY = 10
VIDEO_MODEL = "google/veo-3.1-lite"  # $0.05/s at 720p without audio (OpenRouter, 2026-11-08)
VIDEO_USD_PER_SEC = 0.05
VIDEO_DURATIONS = (4, 6, 8)  # what veo-3.1-lite accepts


def work() -> Path:
    return Path(os.environ.get("MS_WORK", "/work"))


def catalog_path() -> Path:
    return Path(os.environ.get("MS_CATALOG", "/sandbox/catalog.json"))


def global_budget() -> Path:
    return Path(os.environ.get("MS_GLOBAL_BUDGET", "/budget/global.json"))


def owner_budget() -> Path:
    return work() / "budget.json"


def owner_id() -> str:
    return os.environ.get("MS_OWNER_ID", "unknown")


def video_model() -> str:
    return os.environ.get("MS_VIDEO_MODEL", VIDEO_MODEL)


def video_usd_per_sec() -> float:
    return float(os.environ.get("MS_VIDEO_USD_PER_SEC", VIDEO_USD_PER_SEC))
