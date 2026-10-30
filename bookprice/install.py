"""First run of the unpacked program: a desktop shortcut. The program itself stays where it was unpacked —
copying ~120 MB on first start looked like a hang, and user data lives in %LOCALAPPDATA% anyway."""
from __future__ import annotations

import logging
import os
import subprocess
import sys
import tempfile
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)
SHORTCUT = "Цена книги.lnk"


def message(text: str) -> None:
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, "Цена книги", 0x40)


def inside_temp(exe: Path) -> bool:
    temp = Path(tempfile.gettempdir()).resolve()
    return temp in exe.parents


def make_shortcut(link: Path, target: Path) -> None:
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:BP_LINK);"
        "$s.TargetPath = $env:BP_TARGET; $s.WorkingDirectory = $env:BP_DIR;"
        "$s.IconLocation = $env:BP_TARGET + ',0'; $s.Description = $env:BP_DESC; $s.Save()"
    )
    # Paths go through the environment: Cyrillic in PowerShell argv gets mangled on some setups.
    env = {**os.environ, "BP_LINK": str(link), "BP_TARGET": str(target), "BP_DIR": str(target.parent),
           "BP_DESC": "Цена книги"}
    subprocess.run(["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", "-"],
                   input=script.encode("ascii"), env=env, check=True, timeout=60,
                   creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))


def first_run() -> bool:
    """False when the program must not start: it was launched from inside the zip."""
    if not getattr(sys, "frozen", False):
        return True
    exe = Path(sys.executable).resolve()
    if inside_temp(exe):
        message("Сначала распакуйте архив: правой кнопкой по нему → «Извлечь всё…», "
                "потом откройте BookPrice.exe в распакованной папке.")
        return False
    link = paths.desktop() / SHORTCUT
    if not link.exists():
        try:
            make_shortcut(link, exe)
            log.info("ярлык создан: %s → %s", link, exe)
        except Exception:
            log.exception("ярлык не создан")
    return True
