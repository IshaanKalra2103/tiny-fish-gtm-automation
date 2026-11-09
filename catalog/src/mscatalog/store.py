"""Where the pipeline keeps its files (catalog/data/, git-ignored) and the jobs taxonomy (catalog/needs.yaml)."""
import json
import os
from pathlib import Path

import yaml

CATALOG_DIR = Path(__file__).resolve().parents[2]  # catalog/
REPO = CATALOG_DIR.parent


def data_dir() -> Path:
    return Path(os.environ.get("MS_CATALOG_DATA", CATALOG_DIR / "data"))


def pages_dir() -> Path:
    return data_dir() / "pages"


def records_dir() -> Path:
    return data_dir() / "records"


def candidates_path() -> Path:
    return data_dir() / "candidates.json"


def load_needs() -> dict:
    return yaml.safe_load((CATALOG_DIR / "needs.yaml").read_text())


def load_json(path: Path):
    return json.loads(Path(path).read_text())


def save_json(path: Path, data) -> None:
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(data, indent=1, ensure_ascii=False))
    tmp.replace(path)


def records() -> list[dict]:
    d = records_dir()
    return [load_json(p) for p in sorted(d.glob("*.json"))] if d.exists() else []
