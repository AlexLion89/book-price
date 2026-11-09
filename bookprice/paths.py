from __future__ import annotations

from pathlib import Path

from .system import current as system


def data_dir() -> Path:
    base = system.data_root()
    path = base / "BookPrice" if base else Path.home() / ".bookprice"
    path.mkdir(parents=True, exist_ok=True)
    return path


def outbox() -> Path:
    """Where the program puts files for the user to pass on (reports, site checks)."""
    return system.outbox()
