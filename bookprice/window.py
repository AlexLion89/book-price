"""The program's own Edge window.

It runs with a separate profile folder, so it is a separate Edge process started by us: closing it by our process
id can never touch the user's own Edge windows, which live in another process with another profile.
"""
from __future__ import annotations

import logging
import os
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import List, Optional

log = logging.getLogger(__name__)

EDGE = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
]
WM_CLOSE = 0x0010
# A process that is gone this fast handed the window to an Edge already running with the same profile
# (a second launch of the program): that window is not ours to close.
HANDOFF_SECONDS = 2


def open_window(url: str, profile: Path) -> Optional[subprocess.Popen]:
    """Edge in app mode looks like a program window: no tabs, no address bar."""
    edge = next((p for p in EDGE if p.is_file()), None)
    if not edge:
        webbrowser.open(url)
        return None
    proc = subprocess.Popen([str(edge), f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
                             f"--app={url}", "--window-size=1150,900"])
    time.sleep(HANDOFF_SECONDS)
    return proc if proc.poll() is None else None


def windows_of(pid: int) -> List[int]:
    import ctypes
    from ctypes import wintypes
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)
    def collect(hwnd, _):
        owner = wintypes.DWORD()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(collect, 0)
    return found


def close_window(proc: Optional[subprocess.Popen]) -> None:
    """Ask our Edge to close its windows; kill only our own process tree if it does not listen.
    The Popen handle keeps the process id from being reused while we hold it."""
    if proc is None or proc.poll() is not None:
        return
    try:
        import ctypes
        for hwnd in windows_of(proc.pid):
            ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        proc.wait(timeout=8)
    except Exception:
        log.warning("окно программы не закрылось само — завершаю его процесс")
        subprocess.run(["taskkill", "/PID", str(proc.pid), "/T", "/F"], capture_output=True,
                       creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
