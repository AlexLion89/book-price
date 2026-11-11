"""Which installed browser the program drives.

Any browser of the Chromium family works the same way; Safari and Firefox cannot be driven, and without a suitable
browser the program cannot search at all. Each browser gets profile folders of its own inside the program's data:
the user's profiles are never opened, and a profile written by one browser is never handed to another.
"""
from __future__ import annotations

import os
import re
from dataclasses import dataclass
from pathlib import Path
from typing import List, Optional

from . import settings
from .system import current as system

ORDER = ["edge", "chrome", "yandex", "brave", "vivaldi", "chromium"]
LABELS = {"edge": "Microsoft Edge", "chrome": "Google Chrome", "yandex": "Яндекс Браузер", "brave": "Brave",
          "vivaldi": "Vivaldi", "chromium": "Chromium"}
DOWNLOADS = [
    {"label": "Google Chrome", "url": "https://www.google.com/chrome/"},
    {"label": "Microsoft Edge", "url": "https://www.microsoft.com/edge/download"},
    {"label": "Яндекс Браузер", "url": "https://browser.yandex.ru/"},
]
NO_BROWSER = ("Нет подходящего браузера: нужен Google Chrome, Microsoft Edge или Яндекс Браузер. Safari и Firefox "
              "программа не умеет — без одного из этих браузеров она не сможет искать цены.")


class NoBrowser(RuntimeError):
    pass


@dataclass(frozen=True)
class Found:
    key: str
    path: Path

    @property
    def label(self) -> str:
        return LABELS.get(self.key, self.path.stem)


def installed() -> List[Found]:
    found = []
    for key, path in sorted(system.browser_paths(), key=lambda kp: ORDER.index(kp[0])):
        if path.is_file() and all(f.key != key for f in found):
            found.append(Found(key, path))
    return found


def find() -> Optional[Found]:
    """The browser the user chose in the program, if it is still installed; otherwise the first in ORDER."""
    forced = os.environ.get("BOOKPRICE_BROWSER")
    if forced:
        key = next((k for k, p in system.browser_paths() if str(p) == forced), "chromium")
        return Found(key, Path(forced))
    found = installed()
    chosen = settings.load().get("browser")
    return next((f for f in found if f.key == chosen), found[0] if found else None)


def choose(key: str) -> Found:
    found = next((f for f in installed() if f.key == key), None)
    if not found:
        raise ValueError("такого браузера на компьютере нет")
    settings.save(browser=key)
    return found


def exe_names() -> set:
    return {p.name for _, p in system.browser_paths()} | ({Path(os.environ["BOOKPRICE_BROWSER"]).name}
                                                          if os.environ.get("BOOKPRICE_BROWSER") else set())


def profile(data_dir: Path, kind: str, browser: Found) -> Path:
    """kind: "ui" — the program's own window, "search" — the window that visits the shops. Edge keeps the folder names
    of the versions that knew only Edge, so its cookies and the leftover-window check carry over."""
    if browser.key == "edge":
        return data_dir / ("ui-profile" if kind == "ui" else "edge-profile")
    return data_dir / f"{kind}-profile-{browser.key}"


def ui_profiles(data_dir: Path) -> List[Path]:
    return [data_dir / "ui-profile"] + [data_dir / f"ui-profile-{k}" for k in ORDER if k != "edge"]


def launch_options(browser: Found) -> dict:
    """For Playwright. Edge on Windows goes by channel, as it always has; the rest by the file found."""
    if browser.key == "edge" and system.NAME == "windows":
        return {"channel": "msedge"}
    return {"executable_path": str(browser.path)}


def started_with(command: str, profile_dir: Path) -> bool:
    """Whether a process command line carries exactly this profile folder (not one whose name merely starts so)."""
    mark = str(profile_dir)
    flags = re.I if system.NAME == "windows" else 0
    return re.search(r"--user-data-dir=\"?" + re.escape(mark) + r"(?=[\"\s]|$)", command, flags) is not None
