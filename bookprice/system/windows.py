"""Windows: data in %LOCALAPPDATA%, a desktop shortcut, processes read through the WinAPI.

Not through PowerShell: an unknown program that keeps starting PowerShell is exactly what antivirus software watches
for. PowerShell is left only as a fallback and for the one-time shortcut.
Plain ctypes types only — ctypes.wintypes is missing from programs built before 0.2.2, and updates run on them.
"""
from __future__ import annotations

import ctypes
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

log = logging.getLogger(__name__)

NAME = "windows"
LABEL = "Windows"
OUTBOX_WHERE = "на рабочем столе"
WINDOW_ARGS = ["--start-maximized"]
# With SO_REUSEADDR Windows lets a second socket listen on a taken port: two copies of the program would both answer,
# and the second window would talk to either.
REUSE_ADDRESS = False
NO_WINDOW = getattr(subprocess, "CREATE_NO_WINDOW", 0)

CSIDL_DESKTOPDIRECTORY, CSIDL_LOCAL_APPDATA = 0x10, 0x1C
WM_CLOSE = 0x0010
SYNCHRONIZE, QUERY_LIMITED = 0x00100000, 0x1000
WAIT_TIMEOUT = 0x102
CLOSE_WAIT, NO_WINDOW_GRACE = 8.0, 2.0
TH32CS_SNAPPROCESS = 0x2
PROCESS_COMMAND_LINE = 60
# A command line is at most 32767 characters, plus the UNICODE_STRING header in front of it.
COMMAND_LINE_BYTES = 65536 + 64

SHORTCUT = "Ценитель.lnk"
OLD_SHORTCUTS = ["Цена книги.lnk"]
# Bump to recreate the shortcut once on users' desktops (new name or icon) — it arrives with an update.
SHORTCUT_VERSION = 2


def data_root() -> Optional[Path]:
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) if base else None


def _folder(csidl: int) -> Optional[Path]:
    """Ask Windows: with OneDrive or a Russian locale the desktop is not simply ~/Desktop."""
    try:
        buf = ctypes.create_unicode_buffer(260)
        if ctypes.windll.shell32.SHGetFolderPathW(None, csidl, None, 0, buf) == 0:
            path = Path(buf.value)
            if path.is_dir():
                return path
    except (AttributeError, OSError):
        pass
    return None


def outbox() -> Path:
    """Where files for the user to pass on go: the desktop."""
    found = _folder(CSIDL_DESKTOPDIRECTORY)
    if found:
        return found
    fallback = Path.home() / "Desktop"
    if fallback.is_dir():
        return fallback
    from .. import paths
    return paths.data_dir()


def message(text: str) -> None:
    ctypes.windll.user32.MessageBoxW(None, text, "Ценитель", 0x40)


def reveal(path: Path) -> None:
    subprocess.Popen(["explorer", "/select,", str(path)])


def ssl_context():
    # Python on Windows reads the system certificate store itself.
    return None


def browser_paths() -> List[Tuple[str, Path]]:
    program_files = Path(os.environ.get("ProgramFiles", r"C:\Program Files"))
    program_files_x86 = Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))
    # The real local AppData, not %LOCALAPPDATA%: tests point that at their own data folder.
    local = _folder(CSIDL_LOCAL_APPDATA) or Path.home() / "AppData" / "Local"
    return [
        ("edge", program_files_x86 / "Microsoft/Edge/Application/msedge.exe"),
        ("edge", program_files / "Microsoft/Edge/Application/msedge.exe"),
        ("chrome", program_files / "Google/Chrome/Application/chrome.exe"),
        ("chrome", program_files_x86 / "Google/Chrome/Application/chrome.exe"),
        ("chrome", local / "Google/Chrome/Application/chrome.exe"),
        ("yandex", local / "Yandex/YandexBrowser/Application/browser.exe"),
        ("yandex", program_files / "Yandex/YandexBrowser/Application/browser.exe"),
        ("brave", program_files / "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ("brave", local / "BraveSoftware/Brave-Browser/Application/brave.exe"),
        ("vivaldi", local / "Vivaldi/Application/vivaldi.exe"),
        ("vivaldi", program_files / "Vivaldi/Application/vivaldi.exe"),
        ("chromium", local / "Chromium/Application/chrome.exe"),
    ]


class _Entry(ctypes.Structure):
    """PROCESSENTRY32W."""
    _fields_ = [("size", ctypes.c_ulong), ("usage", ctypes.c_ulong), ("pid", ctypes.c_ulong),
                ("heap", ctypes.c_size_t), ("module", ctypes.c_ulong), ("threads", ctypes.c_ulong),
                ("parent", ctypes.c_ulong), ("priority", ctypes.c_long), ("flags", ctypes.c_ulong),
                ("exe", ctypes.c_wchar * 260)]


class _UnicodeString(ctypes.Structure):
    _fields_ = [("length", ctypes.c_ushort), ("maximum", ctypes.c_ushort), ("buffer", ctypes.c_void_p)]


_api = {}


def _kernel32():
    """A private copy of kernel32: setting argument types on ctypes.windll's shared one would change it for all."""
    if "k" not in _api:
        k = ctypes.WinDLL("kernel32")
        k.CreateToolhelp32Snapshot.restype = ctypes.c_void_p
        k.CreateToolhelp32Snapshot.argtypes = [ctypes.c_ulong, ctypes.c_ulong]
        k.Process32FirstW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Entry)]
        k.Process32NextW.argtypes = [ctypes.c_void_p, ctypes.POINTER(_Entry)]
        k.OpenProcess.restype = ctypes.c_void_p
        k.OpenProcess.argtypes = [ctypes.c_ulong, ctypes.c_int, ctypes.c_ulong]
        k.CloseHandle.argtypes = [ctypes.c_void_p]
        k.WaitForSingleObject.restype = ctypes.c_ulong
        k.WaitForSingleObject.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
        _api["k"] = k
    return _api["k"]


def _ntdll():
    if "nt" not in _api:
        nt = ctypes.WinDLL("ntdll")
        nt.NtQueryInformationProcess.restype = ctypes.c_long
        nt.NtQueryInformationProcess.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p, ctypes.c_ulong,
                                                 ctypes.POINTER(ctypes.c_ulong)]
        _api["nt"] = nt
    return _api["nt"]


def _command_line(pid: int) -> Optional[str]:
    k = _kernel32()
    handle = k.OpenProcess(QUERY_LIMITED, False, pid)
    if not handle:
        return None
    try:
        buf = ctypes.create_string_buffer(COMMAND_LINE_BYTES)
        size = ctypes.c_ulong(0)
        if _ntdll().NtQueryInformationProcess(handle, PROCESS_COMMAND_LINE, buf, len(buf), ctypes.byref(size)) != 0:
            return None
        text = _UnicodeString.from_buffer(buf)
        return ctypes.wstring_at(text.buffer, text.length // 2) if text.buffer else ""
    finally:
        k.CloseHandle(handle)


def _native(names: set) -> List[Tuple[int, str]]:
    k = _kernel32()
    snap = k.CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0)
    if not snap or snap == ctypes.c_void_p(-1).value:
        raise OSError("CreateToolhelp32Snapshot")
    found = []
    try:
        entry = _Entry()
        entry.size = ctypes.sizeof(_Entry)
        more = k.Process32FirstW(snap, ctypes.byref(entry))
        while more:
            if entry.exe.lower() in names:
                command = _command_line(entry.pid)
                if command is not None:
                    found.append((int(entry.pid), command))
            more = k.Process32NextW(snap, ctypes.byref(entry))
    finally:
        k.CloseHandle(snap)
    return found


def _powershell(names: set) -> List[Tuple[int, str]]:
    where = " OR ".join(f"Name='{n}'" for n in sorted(names))
    script = ("[Console]::OutputEncoding = [Text.Encoding]::UTF8; "
              f"Get-CimInstance Win32_Process -Filter \"{where}\" | "
              "ForEach-Object { \"$($_.ProcessId)`t$($_.CommandLine)\" }")
    out = subprocess.run(["powershell", "-NoProfile", "-Command", script], capture_output=True, timeout=30,
                         creationflags=NO_WINDOW).stdout.decode("utf-8", "replace")
    found = []
    for line in out.splitlines():
        pid, _, command = line.partition("\t")
        if pid.strip().isdigit():
            found.append((int(pid), command))
    return found


def processes(exe_names: Iterable[str]) -> List[Tuple[int, str]]:
    """(id, command line) of running processes with one of these executable names."""
    names = {n.lower() for n in exe_names}
    try:
        return _native(names)
    except Exception:
        log.exception("список процессов через WinAPI — пробую PowerShell")
        return _powershell(names)


def launch_window(command: List[str], url: str) -> None:
    subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def profile_in_use(profile: Path, pid: int) -> bool:
    """A browser holds <profile>/lockfile open, unshared, for as long as it runs on that folder. A process that only
    names our folder is not proof: Edge launched through some starters falls back to the user's own profile and keeps
    that command line — such a process must never be taken for ours."""
    lock = profile / "lockfile"
    if not lock.exists():
        return False
    try:
        with open(lock, "rb"):
            return False
    except PermissionError:
        return True
    except OSError:
        return False


def _windows_of(pid: int) -> List[int]:
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


class Process:
    """A browser process of ours, held by an OS handle: its id cannot be reused while we hold it."""

    def __init__(self, pid: int, profile: Path) -> None:
        self.pid = pid
        self.handle = _kernel32().OpenProcess(SYNCHRONIZE | QUERY_LIMITED, False, pid)

    def alive(self) -> bool:
        return bool(self.handle) and _kernel32().WaitForSingleObject(self.handle, 0) == WAIT_TIMEOUT

    def close(self) -> None:
        if not self.alive():
            return
        windows = _windows_of(self.pid)
        for hwnd in windows:
            ctypes.windll.user32.PostMessageW(hwnd, WM_CLOSE, 0, 0)
        # Some browsers (Yandex) close the window but keep running in the background: once no window is left, a short
        # grace for saving the profile, then the process goes.
        deadline, no_window_since = time.monotonic() + CLOSE_WAIT, None
        while time.monotonic() < deadline:
            if _kernel32().WaitForSingleObject(self.handle, 250) != WAIT_TIMEOUT:
                return
            if not _windows_of(self.pid):
                no_window_since = no_window_since or time.monotonic()
                if time.monotonic() - no_window_since > NO_WINDOW_GRACE:
                    break
        if no_window_since is None:
            log.warning("окно программы не закрылось само — завершаю его процесс")
        subprocess.run(["taskkill", "/PID", str(self.pid), "/T", "/F"], capture_output=True, creationflags=NO_WINDOW)


def _inside_temp(exe: Path) -> bool:
    temp = Path(tempfile.gettempdir()).resolve()
    return temp in exe.parents


def _icon_file() -> Path:
    """The code folder changes with every update, so the shortcut points to a copy in the data folder."""
    from .. import paths
    source = Path(__file__).resolve().parent.parent / "ui" / "img" / "fox.ico"
    target = paths.data_dir() / "fox.ico"
    if source.exists() and (not target.exists() or target.read_bytes() != source.read_bytes()):
        shutil.copyfile(source, target)
    return target


def _make_shortcut(link: Path, target: Path, icon: Path) -> None:
    script = (
        "$s = (New-Object -ComObject WScript.Shell).CreateShortcut($env:BP_LINK);"
        "$s.TargetPath = $env:BP_TARGET; $s.WorkingDirectory = $env:BP_DIR;"
        "$s.IconLocation = $env:BP_ICON + ',0'; $s.Description = $env:BP_DESC; $s.Save()"
    )
    # Paths go through the environment: Cyrillic in PowerShell argv gets mangled on some setups. Commands read from
    # stdin are not scripts, so no execution policy applies and none is overridden.
    env = {**os.environ, "BP_LINK": str(link), "BP_TARGET": str(target), "BP_DIR": str(target.parent),
           "BP_ICON": str(icon if icon.exists() else target), "BP_DESC": "Ценитель — лисья оценка книг для Авито"}
    subprocess.run(["powershell", "-NoProfile", "-Command", "-"], input=script.encode("ascii"), env=env, check=True,
                   timeout=60, creationflags=NO_WINDOW)


def first_run() -> bool:
    """A desktop shortcut once. False when the program must not start: it was launched from inside the zip.
    The program itself stays where it was unpacked — copying ~120 MB on first start looked like a hang."""
    from .. import paths
    if not getattr(sys, "frozen", False):
        return True
    exe = Path(sys.executable).resolve()
    if _inside_temp(exe):
        message("Сначала распакуйте архив: правой кнопкой по нему → «Извлечь всё…», "
                "потом откройте BookPrice.exe в распакованной папке.")
        return False
    desktop = outbox()
    link = desktop / SHORTCUT
    marker = paths.data_dir() / "shortcut.version"
    done = marker.read_text().strip() if marker.exists() else ""
    if link.exists() and done == str(SHORTCUT_VERSION):
        return True
    try:
        for old in OLD_SHORTCUTS:
            if (desktop / old).exists():
                (desktop / old).unlink()
        _make_shortcut(link, exe, _icon_file())
        marker.write_text(str(SHORTCUT_VERSION))
        log.info("ярлык создан: %s → %s", link, exe)
    except Exception:
        log.exception("ярлык не создан")
    return True
