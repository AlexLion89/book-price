import ast
import importlib.util
import sys
import unittest
from pathlib import Path

from bookprice import REQUIRES_RUNTIME, REQUIRES_RUNTIME_MAC

ROOT = Path(__file__).resolve().parent.parent
HERE = Path(__file__).parent
# Code that runs only on one system needs only that system's builds.
ONLY_ON = {"windows": ROOT / "bookprice" / "system" / "windows.py", "mac": ROOT / "bookprice" / "system" / "mac.py"}
LISTS = {"windows": HERE / f"runtime{REQUIRES_RUNTIME}_modules.txt",
         "mac": HERE / f"runtime_mac{REQUIRES_RUNTIME_MAC}_modules.txt"}


def imports(system: str):
    skip = {p for s, p in ONLY_ON.items() if s != system}
    for path in sorted((ROOT / "bookprice").rglob("*.py")):
        if path in skip:
            continue
        for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    yield path, alias.name
            elif isinstance(node, ast.ImportFrom) and node.level == 0:
                yield path, node.module
                for alias in node.names:
                    try:
                        if importlib.util.find_spec(f"{node.module}.{alias.name}"):
                            yield path, f"{node.module}.{alias.name}"
                    except (ImportError, ValueError):
                        pass


def missing(system: str):
    packed = set(LISTS[system].read_text(encoding="utf-8").split())
    return sorted({f"{path.relative_to(ROOT)}: {name}" for path, name in imports(system)
                   if name.split(".")[0] != "bookprice" and name not in packed and name not in sys.builtin_module_names})


class RuntimeTest(unittest.TestCase):
    """An update runs on the program the user once unpacked, which has only the modules its own build used."""

    def test_windows_updates_import_only_what_every_published_windows_program_has(self):
        self.assertEqual(missing("windows"), [], "нет в старых сборках — обойтись без них или поднять REQUIRES_RUNTIME")

    def test_mac_updates_import_only_what_every_published_mac_program_has(self):
        if not LISTS["mac"].exists():
            self.skipTest("список модулей первой сборки для macOS ещё не снят")
        self.assertEqual(missing("mac"), [], "нет в старых сборках — обойтись без них или поднять REQUIRES_RUNTIME_MAC")


if __name__ == "__main__":
    unittest.main()
