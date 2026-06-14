"""Shared utilities for all tools in the WAT framework."""

import os
from pathlib import Path
from dotenv import load_dotenv

ROOT = Path(__file__).parent.parent
TMP = ROOT / ".tmp"
TMP.mkdir(exist_ok=True)

load_dotenv(ROOT / ".env")


def get_env(key: str) -> str:
    value = os.getenv(key)
    if not value:
        raise EnvironmentError(f"Missing required env var: {key}")
    return value
