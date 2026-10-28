"""Settings loaded from environment variables (and .env if present)."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "lab"
RUNS_DIR = ROOT / "runs"


@dataclass(frozen=True)
class Settings:
    api_key: Optional[str]
    base_url: str
    model: str
    reasoning_effort: Optional[str]
    price_in: float       # USD per 1M fresh input tokens
    price_cached: float   # USD per 1M cached input tokens
    price_out: float      # USD per 1M output tokens
    max_steps: int        # max model calls per run
    max_plans: int        # max submit_plan attempts per run
    max_seconds: int      # wall-clock budget per run


def load_settings() -> Settings:
    return Settings(
        api_key=os.environ.get("MODEL_API_KEY"),
        base_url=os.environ.get("NP_BASE_URL", "https://api.meta.ai/v1"),
        model=os.environ.get("NP_MODEL", "muse-spark-1.3"),
        reasoning_effort=os.environ.get("NP_REASONING_EFFORT") or None,
        price_in=float(os.environ.get("NP_PRICE_IN", "1.25")),
        price_cached=float(os.environ.get("NP_PRICE_CACHED", "0.15")),
        price_out=float(os.environ.get("NP_PRICE_OUT", "4.25")),
        max_steps=int(os.environ.get("NP_MAX_STEPS", "25")),
        max_plans=int(os.environ.get("NP_MAX_PLANS", "3")),
        max_seconds=int(os.environ.get("NP_MAX_SECONDS", "420")),
    )
