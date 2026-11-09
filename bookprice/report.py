from __future__ import annotations

import platform
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__, browsers, paths
from .system import current as system

RECENT = 3 * 24 * 3600


def build(data_dir: Path) -> Path:
    """Logs, recent page snapshots and the book database (found offers, marks) in one zip, shown to the user.
    Nothing is sent anywhere — the user passes the file on by hand."""
    target = paths.outbox() / f"отчёт-ценитель-{datetime.now():%Y%m%d-%H%M}.zip"
    cutoff = time.time() - RECENT
    found = browsers.find()
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("about.txt", f"Ценитель {__version__}\n{platform.platform()}\nPython {sys.version}\n"
                                f"Браузер: {found.label + ' — ' + str(found.path) if found else 'нет подходящего'}\n")
        if (data_dir / "books.sqlite").exists():
            z.write(data_dir / "books.sqlite", "books.sqlite")
        for folder in ("logs", "snapshots"):
            for f in sorted((data_dir / folder).glob("*")):
                if f.is_file() and (folder == "logs" or f.stat().st_mtime > cutoff):
                    z.write(f, f"{folder}/{f.name}")
    system.reveal(target)
    return target
