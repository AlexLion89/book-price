import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


class DocsTest(unittest.TestCase):
    def test_repository_page_shows_the_same_install_guide_as_the_releases(self):
        install = (ROOT / "docs" / "install.md").read_text(encoding="utf-8")
        self.assertIn(install, (ROOT / "README.md").read_text(encoding="utf-8"))

    def test_every_release_note_from_0_6_says_whom_it_is_for(self):
        for notes in (ROOT / "docs" / "releases").glob("*.md"):
            version = tuple(int(x) for x in notes.stem.split("."))
            if version >= (0, 6, 0):
                self.assertRegex(notes.read_text(encoding="utf-8"), r"(?m)^[\s*_]*Система:", notes.name)


if __name__ == "__main__":
    unittest.main()
