from __future__ import annotations

import os
from pathlib import Path

CSIDL_DESKTOPDIRECTORY = 0x10


def data_dir() -> Path:
    base = os.environ.get("LOCALAPPDATA")
    path = Path(base) / "BookPrice" if base else Path.home() / ".bookprice"
    path.mkdir(parents=True, exist_ok=True)
    return path


def desktop() -> Path:
    """Ask Windows: with OneDrive or a Russian locale the desktop is not simply ~/Desktop."""
    try:
        import ctypes
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, CSIDL_DESKTOPDIRECTORY, None, 0, buf) == 0:
            path = Path(buf.value)
            if path.is_dir():
                return path
    except (AttributeError, OSError):
        pass
    fallback = Path.home() / "Desktop"
    return fallback if fallback.is_dir() else data_dir()
