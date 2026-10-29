"""Settings: run budgets from environment variables, model endpoints from models.yaml profiles."""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import yaml

try:
    from dotenv import load_dotenv

    load_dotenv()
except ImportError:  # python-dotenv is optional at runtime
    pass

ROOT = Path(__file__).resolve().parent.parent
LAB_DIR = ROOT / "lab"
RUNS_DIR = ROOT / "runs"
REPORTS_DIR = ROOT / "reports"
DB_PATH = RUNS_DIR / "netproof.db"
MODELS_FILE = ROOT / "models.yaml"


@dataclass(frozen=True)
class Settings:
    profile: str
    api_key: Optional[str]
    key_env: str
    base_url: str
    model: str
    reasoning_effort: Optional[str]
    price_in: float       # USD per 1M fresh input tokens
    price_cached: float   # USD per 1M cached input tokens
    price_out: float      # USD per 1M output tokens
    max_steps: int        # max model calls per run
    max_plans: int        # max submit_plan attempts per run
    max_seconds: int      # wall-clock budget per run


def load_profiles(path: Optional[Path] = None) -> dict:
    p = Path(path or MODELS_FILE)
    if not p.exists():
        return {"default": "env", "profiles": {}}
    return yaml.safe_load(p.read_text())


def load_settings(profile: Optional[str] = None, models_file: Optional[Path] = None) -> Settings:
    """Profile from the argument, else NP_PROFILE, else models.yaml `default`.

    With no models.yaml, falls back to the Phase 1 environment variables.
    """
    data = load_profiles(models_file)
    name = profile or os.environ.get("NP_PROFILE") or data.get("default", "env")
    budgets = dict(
        max_steps=int(os.environ.get("NP_MAX_STEPS", "25")),
        max_plans=int(os.environ.get("NP_MAX_PLANS", "3")),
        max_seconds=int(os.environ.get("NP_MAX_SECONDS", "420")),
    )
    if name == "env" or name not in data.get("profiles", {}):
        if name != "env" and data.get("profiles"):
            raise KeyError(f"unknown model profile {name!r}; known: {sorted(data['profiles'])}")
        return Settings(
            profile="env", api_key=os.environ.get("MODEL_API_KEY"), key_env="MODEL_API_KEY",
            base_url=os.environ.get("NP_BASE_URL", "https://api.meta.ai/v1"),
            model=os.environ.get("NP_MODEL", "muse-spark-1.3"),
            reasoning_effort=os.environ.get("NP_REASONING_EFFORT") or None,
            price_in=float(os.environ.get("NP_PRICE_IN", "1.25")),
            price_cached=float(os.environ.get("NP_PRICE_CACHED", "0.15")),
            price_out=float(os.environ.get("NP_PRICE_OUT", "4.25")),
            **budgets,
        )
    prof = data["profiles"][name]
    price = prof.get("price", {})
    effort = os.environ.get("NP_REASONING_EFFORT") or prof.get("reasoning_effort") or None
    return Settings(
        profile=name, api_key=os.environ.get(prof["key_env"]), key_env=prof["key_env"],
        base_url=prof["base_url"], model=prof["model"], reasoning_effort=effort,
        price_in=float(price.get("in", 0)), price_cached=float(price.get("cached", 0)),
        price_out=float(price.get("out", 0)), **budgets,
    )
