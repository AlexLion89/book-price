"""The program's own browser window.

It runs with a separate profile folder, so it is a separate browser process: closing it can never touch the user's own
windows of the same browser, which live in another process with another profile. The process is found by that profile
folder, not by the id of the process we started — Edge often hands a launch over to another of its processes
(for instance when its own update is pending), and the started process exits at once.
"""
from __future__ import annotations

import logging
import subprocess
import time
import webbrowser
from pathlib import Path
from typing import Optional

from . import browsers
from .system import current as system

log = logging.getLogger(__name__)

# A fresh profile offers to sign in and sync with the system account; the program's windows need neither.
QUIET = ["--no-first-run", "--no-default-browser-check", "--disable-sync"]
FIND_TRIES, FIND_PAUSE = 8, 1.0


class OwnedWindow:
    def __init__(self, pid: int, profile: Path) -> None:
        self.pid = pid
        self.process = system.Process(pid, profile)

    def alive(self) -> bool:
        return self.process.alive()

    def close(self) -> None:
        self.process.close()


def find_browser(profile: Path, listing=None) -> Optional[int]:
    """The browser process (not a renderer or helper: those carry --type=) started with this profile folder."""
    for pid, command in listing if listing is not None else system.processes(browsers.exe_names()):
        if "--type=" not in command and browsers.started_with(command, profile):
            return pid
    return None


def open_window(url: str, data_dir: Path, own: bool = True) -> Optional[OwnedWindow]:
    """App mode looks like a program window: no tabs, no address bar. Without a suitable browser the page opens in
    the default one, which tells the user what to install."""
    browser = browsers.find()
    if not browser:
        log.warning("нет подходящего браузера — открываю страницу в браузере по умолчанию")
        webbrowser.open(url)
        return None
    profile = browsers.profile(data_dir, "ui", browser)
    log.info("окно программы: %s (%s)", browser.label, browser.path)
    subprocess.Popen([str(browser.path), f"--user-data-dir={profile}", *QUIET, *system.WINDOW_ARGS, f"--app={url}"],
                     stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
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
            return OwnedWindow(pid, profile)
    log.warning("не нашёл процесс окна программы — закрывать его придётся вручную")
    return None


def leftover_windows(data_dir: Path):
    """Windows with our profiles left by an older copy of the program — whichever browser drew them."""
    listing = system.processes(browsers.exe_names())
    for profile in browsers.ui_profiles(data_dir):
        pid = find_browser(profile, listing)
        if pid:
            yield OwnedWindow(pid, profile)


def close_window(window: Optional[OwnedWindow]) -> None:
    """Never raises: a window left open must not stop the program from quitting or restarting."""
    if window is None:
        return
    try:
        window.close()
    except Exception:
        log.exception("окно программы не закрылось")
