from __future__ import annotations

import platform
import subprocess
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from . import __version__, paths

RECENT = 3 * 24 * 3600


def build(data_dir: Path) -> Path:
    """Logs, recent page snapshots and the book database (found offers, marks) in one zip on the desktop.
    Nothing is sent anywhere — the user passes the file on by hand."""
    target = paths.desktop() / f"отчёт-ценитель-{datetime.now():%Y%m%d-%H%M}.zip"
    cutoff = time.time() - RECENT
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        z.writestr("about.txt", f"Ценитель {__version__}\n{platform.platform()}\nPython {sys.version}\n")
        if (data_dir / "books.sqlite").exists():
            z.write(data_dir / "books.sqlite", "books.sqlite")
        for folder in ("logs", "snapshots"):
            for f in sorted((data_dir / folder).glob("*")):
                if f.is_file() and (folder == "logs" or f.stat().st_mtime > cutoff):
                    z.write(f, f"{folder}/{f.name}")
    if sys.platform == "win32":
        subprocess.Popen(["explorer", "/select,", str(target)])
    return target
