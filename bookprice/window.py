"""The program's own Edge window.

It runs with a separate profile folder, so it is a separate Edge browser process: closing it can never touch the
user's own Edge windows, which live in another process with another profile. The process is found by that profile
folder, not by the id of the process we started — Edge often hands a launch over to another of its processes
(for instance when its own update is pending), and the started process exits at once.
"""
from __future__ import annotations

import ctypes
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
SYNCHRONIZE, QUERY_LIMITED = 0x00100000, 0x1000
WAIT_TIMEOUT = 0x102
# A fresh Edge profile offers to sign in and sync with the Windows account; the program's windows need neither.
QUIET_EDGE = ["--no-first-run", "--no-default-browser-check", "--disable-sync"]
FIND_TRIES, FIND_PAUSE = 8, 1.0
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)
PROCESSES = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
             "Get-CimInstance Win32_Process -Filter \"Name='msedge.exe'\" | "
             "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")


class OwnedWindow:
    """Our Edge browser process, held by an OS handle: its id cannot be reused while we hold it."""

    def __init__(self, pid: int) -> None:
        self.pid = pid
        self.handle = ctypes.windll.kernel32.OpenProcess(SYNCHRONIZE | QUERY_LIMITED, False, pid)

    def alive(self) -> bool:
        return bool(self.handle) and ctypes.windll.kernel32.WaitForSingleObject(self.handle, 0) == WAIT_TIMEOUT

    def close(self) -> None:
        if not self.alive():
            return
        for hwnd in windows_of(self.pid):
            ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        if ctypes.windll.kernel32.WaitForSingleObject(self.handle, 8000) == WAIT_TIMEOUT:
            log.warning("окно программы не закрылось само — завершаю его процесс")
            subprocess.run(["taskkill", "/PID", str(self.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)


def find_browser(profile: Path) -> Optional[int]:
    """The Edge browser process (not a renderer: those carry --type=) started with our profile folder."""
    mark = str(profile).lower()
    out = subprocess.run(["powershell", "-NoProfile", "-Command", PROCESSES], capture_output=True, timeout=30,
                         creationflags=NO_WINDOW).stdout.decode("utf-8", "replace")
    for line in out.splitlines():
        pid, _, command = line.partition("\t")
        if mark in command.lower() and "--type=" not in command and pid.strip().isdigit():
            return int(pid)
    return None


def open_window(url: str, profile: Path, own: bool = True) -> Optional[OwnedWindow]:
    """Edge in app mode looks like a program window: no tabs, no address bar."""
    edge = next((p for p in EDGE if p.is_file()), None)
    if not edge:
        webbrowser.open(url)
        return None
    subprocess.Popen([str(edge), f"--user-data-dir={profile}", *QUIET_EDGE, f"--app={url}", "--window-size=1150,900"])
    if not own:
        return None
    for _ in range(FIND_TRIES):
        time.sleep(FIND_PAUSE)
        try:
            pid = find_browser(profile)
        except Exception:
            log.exception("поиск окна программы")
            pid = None
        if pid:
            return OwnedWindow(pid)
    log.warning("не нашёл процесс окна программы — закрывать его придётся вручную")
    return None


def windows_of(pid: int) -> List[int]:
    # Plain ctypes types: ctypes.wintypes is missing from programs built before 0.2.2, and updates run on them.
    user32 = ctypes.windll.user32
    found = []

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p)
    def collect(hwnd, _):
        owner = ctypes.c_ulong()
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(owner))
        if owner.value == pid and user32.IsWindowVisible(hwnd):
            found.append(hwnd)
        return True

    user32.EnumWindows(collect, 0)
    return found


def close_window(window: Optional[OwnedWindow]) -> None:
    """Never raises: a window left open must not stop the program from quitting or restarting."""
    if window is None:
        return
    try:
        window.close()
    except Exception:
        log.exception("окно программы не закрылось")
