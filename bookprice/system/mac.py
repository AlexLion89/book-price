"""macOS: data in ~/Library/Application Support, the program in «Программы» (no shortcut needed).

The user may run the very same browser app with a hundred tabs. Ours is a separate instance only because it is started
from the app's binary with its own profile folder — never through `open` or AppleScript, which would hand the job to
the user's running browser. Every signal goes to one process id that was just checked to carry our profile folder and
to hold its lock.
"""
from __future__ import annotations

import json
import logging
import os
import signal
import ssl
import subprocess
import sys
import threading
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)

NAME = "mac"
LABEL = "macOS"
OUTBOX_WHERE = "в папке, которую программа открыла в Finder"
# Without the mock keychain a browser with a fresh profile asks for the login keychain password; our windows keep
# no passwords.
WINDOW_ARGS = ["--use-mock-keychain", "--password-store=basic", "--start-maximized"]
CLOSE_WAIT = 8.0
# Without SO_REUSEADDR the port stays taken for half a minute after the program quits (TIME_WAIT), and the copy that
# restarts it after an update cannot start. Here it never lets two copies listen at once.
REUSE_ADDRESS = True
APPS = [Path("/Applications"), Path.home() / "Applications"]
BUNDLES = [
    ("edge", "Microsoft Edge.app/Contents/MacOS/Microsoft Edge"),
    ("chrome", "Google Chrome.app/Contents/MacOS/Google Chrome"),
    ("yandex", "Yandex.app/Contents/MacOS/Yandex"),
    ("brave", "Brave Browser.app/Contents/MacOS/Brave Browser"),
    ("vivaldi", "Vivaldi.app/Contents/MacOS/Vivaldi"),
    ("chromium", "Chromium.app/Contents/MacOS/Chromium"),
]
ROOTS = "/System/Library/Keychains/SystemRootCertificates.keychain"
# New-tab pages of the browsers we drive: what a browser shows in a window it opens by itself.
NEW_TAB = ("chrome://newtab", "chrome://new-tab-page", "chrome-search://", "edge://newtab", "browser://tune",
           "chrome://vivaldi-webui/startpage", "about:newtab", "chrome://whats-new", "edge://welcome")
# The shell hands our two pipes to the browser as descriptors 3 and 4, where --remote-debugging-pipe expects them.
PIPE_SHELL = 'exec "$0" "$@" 3<&0 4>&1 0</dev/null 1>/dev/null'


def data_root() -> Optional[Path]:
    return Path.home() / "Library" / "Application Support"


def outbox() -> Path:
    """Not the desktop: macOS asks the user before a program may write there. Shown in Finder instead."""
    from .. import paths
    path = paths.data_dir() / "Отчёты"
    path.mkdir(parents=True, exist_ok=True)
    return path


def message(text: str) -> None:
    script = ['-e', 'on run argv', '-e',
              'display dialog (item 1 of argv) with title "Ценитель" buttons {"OK"} default button 1 with icon note',
              '-e', 'end run']
    try:
        subprocess.run(["osascript", *script, text], capture_output=True, timeout=600)
    except Exception:
        log.exception("сообщение не показано: %s", text)


def reveal(path: Path) -> None:
    subprocess.Popen(["open", "-R", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


_context = {}


def ssl_context():
    """Python from python.org brings no certificates of its own: trust the roots macOS itself keeps."""
    if "ctx" not in _context:
        ctx = None
        try:
            pem = subprocess.run(["security", "find-certificate", "-a", "-p", ROOTS], capture_output=True,
                                 timeout=30).stdout.decode("ascii", "ignore")
            if "BEGIN CERTIFICATE" in pem:
                ctx = ssl.create_default_context(cadata=pem)
        except Exception:
            log.exception("корневые сертификаты macOS не прочитаны")
        _context["ctx"] = ctx
    return _context["ctx"]


def launch_window(command: List[str], url: str) -> None:
    """The program's window, watched over a DevTools pipe. Clicking the Dock icon of a browser whose only window is an
    app window makes it open an empty new-tab window (seen on a Mac with Chrome, 10.11.2026); the watcher closes such
    pages in our browser copy. Pages the user opens from the program — links to shops — are left alone."""
    proc = subprocess.Popen(["/bin/sh", "-c", PIPE_SHELL, *command, "--remote-debugging-pipe"],
                            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    threading.Thread(target=_watch_new_tabs, args=(proc,), daemon=True, name="window-pipe").start()


def _watch_new_tabs(proc: subprocess.Popen) -> None:
    def send(message: dict) -> None:
        proc.stdin.write(json.dumps(message).encode() + b"\0")
        proc.stdin.flush()

    try:
        send({"id": 1, "method": "Target.setDiscoverTargets", "params": {"discover": True}})
        buf, next_id = b"", 2
        while True:
            chunk = os.read(proc.stdout.fileno(), 65536)
            if not chunk:
                break
            buf += chunk
            while b"\0" in buf:
                raw, buf = buf.split(b"\0", 1)
                message = json.loads(raw or b"{}")
                if message.get("method") not in ("Target.targetCreated", "Target.targetInfoChanged"):
                    continue
                info = message["params"]["targetInfo"]
                if info.get("type") == "page" and info.get("url", "").startswith(NEW_TAB):
                    log.info("браузер открыл пустое окно (%s) — закрываю", info.get("url"))
                    send({"id": next_id, "method": "Target.closeTarget", "params": {"targetId": info["targetId"]}})
                    next_id += 1
    except (OSError, ValueError, KeyError):
        log.exception("наблюдение за окном программы")
    finally:
        try:
            proc.wait(timeout=1)
        except Exception:
            pass


def browser_paths() -> List[Tuple[str, Path]]:
    return [(key, folder / inside) for key, inside in BUNDLES for folder in APPS]


def processes(exe_names: Iterable[str] = ()) -> List[Tuple[int, str]]:
    """(id, command line) of every process of this user that was started with a profile folder."""
    out = subprocess.run(["ps", "-axww", "-o", "pid=,command="], capture_output=True, timeout=30).stdout
    found = []
    for line in out.decode("utf-8", "replace").splitlines():
        pid, _, command = line.strip().partition(" ")
        if pid.isdigit() and "--user-data-dir=" in command:
            found.append((int(pid), command.strip()))
    return found


def profile_in_use(profile: Path, pid: int) -> bool:
    """A running browser keeps <profile>/SingletonLock, a link to "<host>-<process id>". A process that only names
    our folder is not proof — it may have fallen back to the user's own profile."""
    try:
        target = os.readlink(profile / "SingletonLock")
    except OSError:
        return False
    return target.rsplit("-", 1)[-1] == str(pid)


def _command_of(pid: int) -> str:
    out = subprocess.run(["ps", "-ww", "-o", "stat=,command=", "-p", str(pid)], capture_output=True, timeout=10)
    line = out.stdout.decode("utf-8", "replace").strip()
    state, _, command = line.partition(" ")
    # A zombie has finished; only its exit status is left to collect.
    return "" if state.startswith("Z") else command


class Process:
    def __init__(self, pid: int, profile: Path) -> None:
        self.pid = pid
        self.mark = str(profile)

    def _reaped(self) -> bool:
        """Our own child stays a zombie until collected — and a zombie still answers kill(pid, 0)."""
        try:
            done, _ = os.waitpid(self.pid, os.WNOHANG)
            return done == self.pid
        except ChildProcessError:
            return False

    def alive(self) -> bool:
        if self._reaped():
            return False
        try:
            os.kill(self.pid, 0)
        except ProcessLookupError:
            return False
        except PermissionError:
            return False
        return True

    def ours(self) -> bool:
        return self.alive() and self.mark in _command_of(self.pid) and profile_in_use(Path(self.mark), self.pid)

    def close(self) -> None:
        if not self.ours():
            return
        # A browser quits on SIGTERM the way it does from its menu: our profile is saved, nothing else is touched.
        os.kill(self.pid, signal.SIGTERM)
        deadline = time.monotonic() + CLOSE_WAIT
        while time.monotonic() < deadline:
            if not self.alive():
                return
            time.sleep(0.2)
        if self.ours():
            log.warning("окно программы не закрылось само — завершаю его процесс")
            os.kill(self.pid, signal.SIGKILL)


def first_run() -> bool:
    """False when the program must not start: it runs straight from the downloaded disk image, which goes away."""
    exe = Path(sys.executable).resolve()
    if getattr(sys, "frozen", False) and str(exe).startswith("/Volumes/"):
        message("Сначала перетащите «Ценитель» в папку «Программы» (окно, которое открылось из скачанного файла), "
                "потом откройте его оттуда — через Launchpad или Finder → Программы.")
        return False
    return True
