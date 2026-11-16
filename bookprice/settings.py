"""Choices the user makes in the program that outlive a run: settings.json in the data folder."""
from __future__ import annotations

import json
import os
import threading

from . import paths

FILE = "settings.json"
_LOCK = threading.Lock()


def load() -> dict:
    try:
        data = json.loads((paths.data_dir() / FILE).read_text(encoding="utf-8"))
        return data if isinstance(data, dict) else {}
    except (OSError, ValueError):
        return {}


def save(**changes) -> dict:
    # Browser choice and update checks may save settings from different request threads.
    with _LOCK:
        data = {**load(), **changes}
        target = paths.data_dir() / FILE
        tmp = target.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")
        os.replace(tmp, target)
        return data
