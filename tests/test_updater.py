import unittest
from unittest import mock

from bookprice import updater


class FakeHttp:
    def __init__(self, releases):
        self.releases = releases

    def json(self, url, *a, **k):
        return self.releases


def release(tag, body="x", **extra):
    return {"tag_name": tag, "body": body, "html_url": "u/" + tag, **extra}


class UpdaterTest(unittest.TestCase):
    def test_summary_is_first_paragraph_without_markdown(self):
        notes = "**Досье** книги и надбавка за редкость. Ставится кнопкой «Обновления».\n\nДальше подробности."
        self.assertEqual(updater.summary(notes), "Досье книги и надбавка за редкость. Ставится кнопкой «Обновления».")
        self.assertTrue(updater.summary("слово " * 100).endswith("…"))

    def test_available_only_when_newer(self):
        with mock.patch.object(updater, "__version__", "0.4.0"):
            self.assertIsNone(updater.available(FakeHttp([release("v0.4.0")])))
            self.assertIsNone(updater.available(FakeHttp([release("v0.3.9")])))
            found = updater.available(FakeHttp([release("v0.4.1", "Исправления."), release("v0.4.0")]))
            self.assertEqual((found["version"], found["summary"]), ("0.4.1", "Исправления."))

    def test_release_for_the_other_system_is_not_offered(self):
        releases = [release("v0.6.1", "Мак: окно поиска.\n\n**Система:** только macOS"),
                    release("v0.6.0", "Общая.\n\nСистема: Windows и macOS")]
        self.assertIsNone(updater.newest(releases, "windows", "0.6.0"))
        self.assertEqual(updater.newest(releases, "mac", "0.6.0")["version"], "0.6.1")
        self.assertEqual(updater.newest(releases, "windows", "0.5.5")["version"], "0.6.0")

    def test_next_common_release_skips_the_other_systems_fix(self):
        releases = [release("v0.6.2", "Общая.\n\nСистема: Windows и macOS"),
                    release("v0.6.1", "Мак.\n\nСистема: только macOS"), release("v0.6.0", "Общая.")]
        self.assertEqual(updater.newest(releases, "windows", "0.6.0")["version"], "0.6.2")

    def test_release_without_a_system_line_is_for_everyone(self):
        for system in ("windows", "mac"):
            self.assertEqual(updater.newest([release("v0.6.0", "Общая.")], system, "0.5.5")["version"], "0.6.0")

    def test_drafts_prereleases_and_odd_tags_are_skipped(self):
        releases = [release("v0.7.0", prerelease=True), release("v0.6.9", draft=True), release("ci-screens"),
                    release("v0.6.1")]
        self.assertEqual(updater.newest(releases, "windows", "0.6.0")["version"], "0.6.1")

    def test_version_order_is_numeric(self):
        releases = [release("v0.9.0"), release("v0.10.0")]
        self.assertEqual(updater.newest(releases, "mac", "0.8.0")["version"], "0.10.0")


if __name__ == "__main__":
    unittest.main()
