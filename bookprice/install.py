"""First run of the unpacked program: a desktop shortcut. The program itself stays where it was unpacked —
copying ~120 MB on first start looked like a hang, and user data lives in %LOCALAPPDATA% anyway."""
from __future__ import annotations

import logging
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

from . import paths

log = logging.getLogger(__name__)
SHORTCUT = "Ценитель.lnk"
OLD_SHORTCUTS = ["Цена книги.lnk"]
# Bump to recreate the shortcut once on users' desktops (new name or icon) — it arrives with an update.
SHORTCUT_VERSION = 2


def message(text: str) -> None:
    import ctypes
    ctypes.windll.user32.MessageBoxW(None, text, "Ценитель", 0x40)


def inside_temp(exe: Path) -> bool:
    temp = Path(tempfile.gettempdir()).resolve()
    return temp in exe.parents


def icon_file() -> Path:
    """The code folder changes with every update, so the shortcut points to a copy in the data folder."""
    source = Path(__file__).parent / "ui" / "img" / "fox.ico"
    target = paths.data_dir() / "fox.ico"
    if source.exists() and (not target.exists() or target.read_bytes() != source.read_bytes()):
        shutil.copyfile(source, target)
    return target


def make_shortcut(link: Path, target: Path, icon: Path) -> None:
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:BP_LINK);"
        "$s.TargetPath = $env:BP_TARGET; $s.WorkingDirectory = $env:BP_DIR;"
        "$s.IconLocation = $env:BP_ICON + ',0'; $s.Description = $env:BP_DESC; $s.Save()"
    )
    # Paths go through the environment: Cyrillic in PowerShell argv gets mangled on some setups.
    env = {**os.environ, "BP_LINK": str(link), "BP_TARGET": str(target), "BP_DIR": str(target.parent),
           "BP_ICON": str(icon if icon.exists() else target), "BP_DESC": "Ценитель — лисья оценка книг для Авито"}
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
    desktop = paths.desktop()
    link = desktop / SHORTCUT
    marker = paths.data_dir() / "shortcut.version"
    done = marker.read_text().strip() if marker.exists() else ""
    if link.exists() and done == str(SHORTCUT_VERSION):
        return True
    try:
        for old in OLD_SHORTCUTS:
            if (desktop / old).exists():
                (desktop / old).unlink()
        make_shortcut(link, exe, icon_file())
        marker.write_text(str(SHORTCUT_VERSION))
        log.info("ярлык создан: %s → %s", link, exe)
    except Exception:
        log.exception("ярлык не создан")
    return True
