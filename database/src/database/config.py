"""Database URL resolution and engine construction."""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

DEFAULT_DATABASE_URL = "sqlite:///./data/openwrt_ai.db"


def database_url() -> str:
    return os.getenv("DATABASE_URL", DEFAULT_DATABASE_URL)


def engine_kwargs() -> dict[str, Any]:
    """Engine options that depend on the database dialect."""
    url = database_url()
    if url.startswith("sqlite"):
        path = url.removeprefix("sqlite:///")
        if path not in ("", ":memory:") and not path.startswith("/"):
            Path(path).parent.mkdir(parents=True, exist_ok=True)
        return {"connect_args": {"check_same_thread": False}}
    return {}
