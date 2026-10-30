"""Entry point of the .exe: prefer the newest downloaded update the bundled runtime can run."""
import os
import re
import sys
from pathlib import Path

RUNTIME = 1


def version_key(path: Path):
    return tuple(int(x) for x in path.name.split("."))


def pick_update() -> None:
    base = os.environ.get("LOCALAPPDATA")
    updates = (Path(base) / "BookPrice" if base else Path.home() / ".bookprice") / "updates"
    if not updates.is_dir():
        return
    versions = [p for p in updates.iterdir() if re.fullmatch(r"\d+\.\d+\.\d+", p.name)]
    for candidate in sorted(versions, key=version_key, reverse=True):
        init = candidate / "bookprice" / "__init__.py"
        if not init.is_file():
            continue
        need = re.search(r"REQUIRES_RUNTIME\s*=\s*(\d+)", init.read_text(encoding="utf-8"))
        if need and int(need.group(1)) <= RUNTIME:
            sys.path.insert(0, str(candidate))
            return


if __name__ == "__main__":
    if "--check" in sys.argv:
        sys.argv.remove("--check")
        pick_update()
        from bookprice import check
        check.main(sys.argv[1:])
        input("\nНажмите Enter, чтобы закрыть окно")
    else:
        pick_update()
        from bookprice import main
        main.main()
