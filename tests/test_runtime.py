import ast
import importlib.util
import sys
import unittest
from pathlib import Path

from bookprice import REQUIRES_RUNTIME

ROOT = Path(__file__).resolve().parent.parent
PACKED = set((Path(__file__).parent / f"runtime{REQUIRES_RUNTIME}_modules.txt").read_text(encoding="utf-8").split())


def imports():
    for path in sorted((ROOT / "bookprice").rglob("*.py")):
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


def available(name: str) -> bool:
    return name in PACKED or name in sys.builtin_module_names


class RuntimeTest(unittest.TestCase):
    def test_updates_import_only_what_every_published_program_has(self):
        """An update runs on the program the user once unpacked, which has only the modules its own build used."""
        missing = sorted({f"{path.relative_to(ROOT)}: {name}" for path, name in imports()
                          if name.split(".")[0] != "bookprice" and not available(name)})
        self.assertEqual(missing, [], "нет в старых сборках — обойтись без них или поднять REQUIRES_RUNTIME")


if __name__ == "__main__":
    unittest.main()
