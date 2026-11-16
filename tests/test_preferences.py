import json
import os
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from pathlib import Path
from unittest import mock

from bookprice import browsers, settings, updater
from bookprice.app import App, Server, make_handler
from tests.test_extract import edge
from tests.test_updater import FakeHttp, release


class PreferencesBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix="bp-preferences-")
        self.addCleanup(self.tmp.cleanup)
        self.data = Path(self.tmp.name)
        self.paths = mock.patch("bookprice.paths.data_dir", return_value=self.data)
        self.paths.start()
        self.addCleanup(self.paths.stop)
        self.app = App(self.data)
        self.addCleanup(self.app.store.db.close)


class PreferencesTest(PreferencesBase):
    def test_default_channel_and_browser_settings_survive_each_other(self):
        self.assertEqual(updater.channel(), "stable")
        settings.save(browser="chrome")
        updater.choose_channel("preview")
        self.assertEqual(settings.load(), {"browser": "chrome", "update_channel": "preview"})
        settings.save(browser="edge")
        self.assertEqual(updater.channel(), "preview")
        updater.choose_channel("stable")
        self.assertEqual(settings.load()["browser"], "edge")
        with self.assertRaises(ValueError):
            updater.choose_channel("unknown")
        self.assertEqual(updater.channel(), "stable")

    def test_changing_channels_discards_the_old_offer_and_wakes_the_checker(self):
        self.app.http = FakeHttp([release("v0.7.0", prerelease=True)])
        self.app.choose_update_channel("preview")
        self.app.check_updates()
        self.assertEqual(self.app.update_status()["available"]["version"], "0.7.0")
        self.app.update_wakeup.clear()
        status = self.app.choose_update_channel("stable")
        self.assertIsNone(status["available"])
        self.assertFalse(status["checked"])
        self.assertTrue(self.app.update_wakeup.is_set())
        self.app.check_updates()
        self.assertIsNone(self.app.update_status()["available"])
        self.assertTrue(self.app.update_status()["checked"])

    def test_late_preview_response_cannot_restore_offer_after_disabling_preview(self):
        self.app.choose_update_channel("preview")
        def late_response(http, selected):
            self.assertEqual(selected, "preview")
            self.app.choose_update_channel("stable")
            return {"version": "0.7.0", "prerelease": True}
        with mock.patch.object(updater, "available", side_effect=late_response):
            self.app.check_updates()
        status = self.app.update_status()
        self.assertEqual(status["channel"], "stable")
        self.assertIsNone(status["available"])
        self.assertFalse(status["checked"])


class PreferencesUiTest(PreferencesBase):
    @classmethod
    def setUpClass(cls):
        cls.browser_env = edge()
        if not cls.browser_env:
            raise unittest.SkipTest("нет Playwright или браузера Chromium")

    @classmethod
    def tearDownClass(cls):
        cls.browser_env[1].close()
        cls.browser_env[0].stop()

    def setUp(self):
        super().setUp()
        self.found = [browsers.Found(k, Path(k)) for k in ("edge", "chrome")]
        patcher = mock.patch.object(browsers, "installed", return_value=self.found)
        patcher.start()
        self.addCleanup(patcher.stop)
        patcher = mock.patch.dict(os.environ, {"BOOKPRICE_BROWSER": ""})
        patcher.start()
        self.addCleanup(patcher.stop)
        self.server = Server(("127.0.0.1", 0), make_handler(self.app))
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()
        self.addCleanup(self.close_server)
        self.url = "http://127.0.0.1:%d/" % self.server.server_port
        self.context = self.browser_env[1].new_context(viewport={"width": 1000, "height": 700})
        self.page = self.context.new_page()
        self.addCleanup(self.context.close)
        self.page_errors = []
        self.page.on("pageerror", lambda error: self.page_errors.append(str(error)))

    def close_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)

    def post(self, path, body):
        req = urllib.request.Request(self.url + path, data=json.dumps(body).encode(),
                                     headers={"Content-Type": "application/json"})
        with urllib.request.urlopen(req, timeout=5) as response:
            return json.load(response)

    def test_first_choice_is_saved_and_does_not_reappear_after_reload(self):
        self.page.goto(self.url)
        self.page.locator("#browser-setup[open]").wait_for()
        self.page.keyboard.press("Escape")
        self.assertTrue(self.page.locator("#browser-setup").is_visible())
        self.page.get_by_role("button", name="Продолжить", exact=True).click()
        self.page.locator("#browser-setup").wait_for(state="hidden")
        self.assertEqual(settings.load()["browser"], "edge")
        self.page.reload()
        self.page.get_by_role("heading", name="Мои книги").wait_for()
        self.assertFalse(self.page.locator("#browser-setup").is_visible())
        self.assertEqual(self.page_errors, [])

    def test_another_browser_is_saved_before_restart(self):
        self.page.goto(self.url)
        self.page.locator("#browser-setup[open]").wait_for()
        self.page.select_option("#first-browser", "chrome")
        with mock.patch.object(self.app, "quit") as quit_app:
            self.page.get_by_role("button", name="Продолжить", exact=True).click()
            self.page.locator("#browser-setup").wait_for(state="hidden")
            self.assertTrue(self.app.restart)
            quit_app.assert_called_once()
        self.assertEqual(settings.load()["browser"], "chrome")
        self.assertEqual(self.page_errors, [])

    def test_help_switches_channel_and_clears_preview_banner(self):
        settings.save(browser="edge", update_channel="preview")
        self.app.http = FakeHttp([release("v0.7.0", prerelease=True)])
        self.app.check_updates()
        self.page.goto(self.url + "#/help")
        self.page.locator("#update-banner").wait_for(state="visible")
        self.assertIn("пробная версия 0.7.0", self.page.locator("#update-banner").inner_text())
        self.page.select_option("#update-channel", "stable")
        self.page.locator("#update-banner").wait_for(state="hidden")
        self.assertEqual(updater.channel(), "stable")
        self.page.reload()
        self.page.locator("#update-channel").wait_for()
        self.assertEqual(self.page.locator("#update-channel").input_value(), "stable")
        self.assertEqual(self.page_errors, [])

    def test_api_rejects_an_uninstalled_browser_or_invalid_channel(self):
        for path, body in (("api/browser", {"key": "missing"}), ("api/update-channel", {"channel": "unknown"})):
            with self.assertRaises(urllib.error.HTTPError) as caught:
                self.post(path, body)
            self.assertEqual(caught.exception.code, 400)
        self.assertEqual(settings.load(), {})
