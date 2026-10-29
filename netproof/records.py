"""Run records: one JSON file per run in runs/."""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Optional

from .config import RUNS_DIR


def new_run_id(agent: str, scenario_id: str, repeat: int = 0) -> str:
    return f"{time.strftime('%Y%m%d-%H%M%S')}-{agent}-{scenario_id}-r{repeat}"


def write_record(record: dict, subdir: Optional[str] = None, base: Optional[Path] = None) -> Path:
    root = Path(base) if base else RUNS_DIR
    folder = root / subdir if subdir else root
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / f"{record['run_id']}.json"
    path.write_text(json.dumps(record, indent=2, default=str))
    return path
