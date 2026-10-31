"""Modules present in every published program: python tools/runtime_modules.py ../dist/BookPrice-*.zip

An update brings only the bookprice code; everything else it imports comes from the program the user once unpacked,
and PyInstaller packs only what the code of that build imported. The list printed here (modules found in all given
builds) is what tests/test_runtime.py holds the code to; refresh it when publishing a new zip with a higher
REQUIRES_RUNTIME, not for each update.
"""
from __future__ import annotations

import sys
import tempfile
import zipfile
from pathlib import Path, PurePosixPath
from typing import Set

from PyInstaller.archive.readers import CArchiveReader

OUT = Path(__file__).resolve().parent.parent / "tests" / "runtime1_modules.txt"


def module_name(path: str) -> str:
    parts = list(PurePosixPath(path).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts.pop()
    return ".".join(parts)


def modules(build: Path) -> Set[str]:
    found: Set[str] = set()
    with zipfile.ZipFile(build) as z, tempfile.TemporaryDirectory() as tmp:
        names = z.namelist()
        exe = next(n for n in names if n.endswith("/BookPrice.exe"))
        internal = exe.rsplit("/", 1)[0] + "/_internal/"
        exe_path = Path(tmp) / "BookPrice.exe"
        exe_path.write_bytes(z.read(exe))
        archive = CArchiveReader(str(exe_path))
        pyz = next(name for name in archive.toc if name.endswith(".pyz"))
        found.update(archive.open_embedded_archive(pyz).toc)
        base = Path(tmp) / "base_library.zip"
        base.write_bytes(z.read(internal + "base_library.zip"))
        with zipfile.ZipFile(base) as lib:
            found.update(module_name(n) for n in lib.namelist() if n.endswith(".pyc"))
        for n in names:
            if n.startswith(internal) and n.endswith(".pyd"):
                # _ctypes.pyd, greenlet/_greenlet.cp39-win_amd64.pyd
                found.add(n[len(internal):-len(".pyd")].split(".cp3")[0].replace("/", "."))
    return found


def main(builds) -> None:
    common = None
    for build in builds:
        mods = modules(Path(build))
        print(f"{Path(build).name}: {len(mods)}", file=sys.stderr)
        common = mods if common is None else common & mods
    with open(OUT, "w", encoding="utf-8", newline="\n") as f:
        f.writelines(f"{m}\n" for m in sorted(common or ()))
    print(f"{OUT}: {len(common or ())}", file=sys.stderr)


if __name__ == "__main__":
    main(sys.argv[1:])
