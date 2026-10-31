import unittest
from unittest import mock

from bookprice import updater


class FakeHttp:
    def __init__(self, release):
        self.release = release

    def json(self, url, *a, **k):
        return self.release


class UpdaterTest(unittest.TestCase):
    def test_summary_is_first_paragraph_without_markdown(self):
        notes = "**Досье** книги и надбавка за редкость. Ставится кнопкой «Обновления».\n\nДальше подробности."
        self.assertEqual(updater.summary(notes), "Досье книги и надбавка за редкость. Ставится кнопкой «Обновления».")
        self.assertTrue(updater.summary("слово " * 100).endswith("…"))

    def test_available_only_when_newer(self):
        with mock.patch.object(updater, "__version__", "0.4.0"):
            self.assertIsNone(updater.available(FakeHttp({"tag_name": "v0.4.0", "body": "x"})))
            self.assertIsNone(updater.available(FakeHttp({"tag_name": "v0.3.9", "body": "x"})))
            found = updater.available(FakeHttp({"tag_name": "v0.4.1", "body": "Исправления.", "html_url": "u"}))
            self.assertEqual((found["version"], found["summary"]), ("0.4.1", "Исправления."))


if __name__ == "__main__":
    unittest.main()
