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

    def test_preview_channel_includes_both_kinds_of_release_but_never_drafts(self):
        releases = [release("v0.6.9", draft=True, prerelease=True), release("v0.6.4", prerelease=True),
                    release("v0.6.3")]
        self.assertEqual(updater.newest(releases, "mac", "0.6.2")["version"], "0.6.3")
        found = updater.newest(releases, "mac", "0.6.2", "preview")
        self.assertEqual(found["version"], "0.6.4")
        self.assertTrue(found["prerelease"])
        releases.append(release("v0.6.5"))
        self.assertEqual(updater.newest(releases, "mac", "0.6.4", "preview")["version"], "0.6.5")

    def test_preview_still_respects_system_and_never_downgrades(self):
        releases = [release("v0.6.5", "Система: только Windows", prerelease=True),
                    release("v0.6.4", "Система: только macOS", prerelease=True), release("v0.5.5")]
        self.assertEqual(updater.newest(releases, "mac", "0.6.3", "preview")["version"], "0.6.4")
        self.assertIsNone(updater.newest(releases, "mac", "0.6.4", "preview"))
        self.assertIsNone(updater.newest(releases, "mac", "0.6.4", "stable"))

    def test_available_uses_explicit_channel_or_saved_choice(self):
        http = FakeHttp([release("v0.7.0", prerelease=True)])
        with mock.patch.object(updater, "__version__", "0.6.4"), mock.patch.object(updater, "channel", return_value="preview"):
            self.assertEqual(updater.available(http)["version"], "0.7.0")
            self.assertIsNone(updater.available(http, "stable"))

    def test_version_order_is_numeric(self):
        releases = [release("v0.9.0"), release("v0.10.0")]
        self.assertEqual(updater.newest(releases, "mac", "0.8.0")["version"], "0.10.0")


if __name__ == "__main__":
    unittest.main()
