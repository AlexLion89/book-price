import importlib.util
import os
import tempfile
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parent.parent
spec = importlib.util.spec_from_file_location("bp_run", ROOT / "run.py")
run = importlib.util.module_from_spec(spec)
spec.loader.exec_module(run)


def update(updates: Path, version: str, runtime: str = "REQUIRES_RUNTIME = 1\nREQUIRES_RUNTIME_MAC = 1\n"):
    folder = updates / version / "bookprice"
    folder.mkdir(parents=True)
    (folder / "__init__.py").write_text(f'__version__ = "{version}"\n{runtime}', encoding="utf-8")


class LauncherTest(unittest.TestCase):
    def picked(self, bundled=()):
        with tempfile.TemporaryDirectory() as tmp, mock.patch.object(run, "data_dir", lambda: Path(tmp)), \
                mock.patch.object(run.sys, "path", []) as path:
            for v in self.versions:
                update(Path(tmp) / "updates", v, *self.extra.get(v, ()))
            run.pick_update(bundled)
            return [Path(p).name for p in path]

    def test_newest_compatible_update_wins(self):
        self.versions, self.extra = ["0.5.5", "0.6.0", "0.6.1"], {"0.6.1": ("REQUIRES_RUNTIME = 2\nREQUIRES_RUNTIME_MAC = 2\n",)}
        self.assertEqual(self.picked(), ["0.6.0"])

    def test_an_update_older_than_the_program_itself_is_ignored(self):
        self.versions, self.extra = ["0.5.5"], {}
        self.assertEqual(self.picked(bundled=(0, 6, 0)), [])
        self.assertEqual(self.picked(bundled=(0, 5, 4)), ["0.5.5"])

    def test_bundled_version_is_read_from_the_packed_code(self):
        self.assertEqual(run.bundled_version(str(ROOT)), tuple(int(x) for x in
                         __import__("bookprice").__version__.split(".")))
        self.assertEqual(run.bundled_version(tempfile.gettempdir()), ())


if __name__ == "__main__":
    unittest.main()
