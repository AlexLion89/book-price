"""Entry point of the built program: prefer the newest downloaded update the bundled runtime can run.

Frozen into every build and never updated — keep it small, and in step with bookprice/paths.py and the system modules.
"""
import os
import re
import sys
from pathlib import Path

RUNTIME = 1
MAC = sys.platform == "darwin"
NEED = re.compile(r"REQUIRES_RUNTIME_MAC\s*=\s*(\d+)" if MAC else r"REQUIRES_RUNTIME\s*=\s*(\d+)")


def version_key(path: Path):
    return tuple(int(x) for x in path.name.split("."))


def bundled_version(base: str):
    """The version packed into this build: a downloaded update older than it must not win — a newly downloaded
    program would otherwise run the old code a previous install left in the shared data folder."""
    try:
        text = (Path(base) / "bookprice" / "__init__.py").read_text(encoding="utf-8")
        return tuple(int(x) for x in re.search(r'__version__ = "(\d+)\.(\d+)\.(\d+)"', text).groups())
    except (OSError, AttributeError):
        return ()


def data_dir() -> Path:
    if MAC:
        return Path.home() / "Library" / "Application Support" / "BookPrice"
    base = os.environ.get("LOCALAPPDATA")
    return Path(base) / "BookPrice" if base else Path.home() / ".bookprice"


def pick_update(bundled=()) -> None:
    updates = data_dir() / "updates"
    if not updates.is_dir():
        return
    versions = [p for p in updates.iterdir() if re.fullmatch(r"\d+\.\d+\.\d+", p.name) and version_key(p) > bundled]
    for candidate in sorted(versions, key=version_key, reverse=True):
        init = candidate / "bookprice" / "__init__.py"
        if not init.is_file():
            continue
        need = NEED.search(init.read_text(encoding="utf-8"))
        if need and int(need.group(1)) <= RUNTIME:
            sys.path.insert(0, str(candidate))
            return


if __name__ == "__main__":
    bundled = ()
    if getattr(sys, "frozen", False):
        base = getattr(sys, "_MEIPASS", str(Path(sys.executable).parent))
        sys.path.insert(0, base)
        bundled = bundled_version(base)
    pick_update(bundled)
    from bookprice import main
    main.main()
