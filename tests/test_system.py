import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest import mock

from bookprice import browsers, window
from bookprice.system import current as system

WIN = sys.platform == "win32"
MAC = sys.platform == "darwin"


def sleeper(profile: Path) -> subprocess.Popen:
    """A stand-in for a browser: a process whose command line carries a profile folder."""
    return subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)", f"--user-data-dir={profile}"],
                            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class BrowsersTest(unittest.TestCase):
    def test_profile_folder_is_matched_exactly(self):
        base = Path(tempfile.gettempdir()) / "BookPrice"
        ours = base / "ui-profile"
        self.assertTrue(browsers.started_with(f'"x" --user-data-dir={ours} --app=http://127.0.0.1', ours))
        self.assertTrue(browsers.started_with(f'"x" "--user-data-dir={ours}" --no-first-run', ours))
        self.assertTrue(browsers.started_with(f'"x" --user-data-dir="{ours}"', ours))
        self.assertFalse(browsers.started_with(f'"x" --user-data-dir={ours}-chrome', ours))
        self.assertFalse(browsers.started_with(f'"x" --user-data-dir={base / "edge-profile"}', ours))
        self.assertFalse(browsers.started_with('"x" --app=http://127.0.0.1', ours))

    def test_each_browser_has_its_own_profiles_and_edge_keeps_the_old_ones(self):
        data = Path("data")
        edge, chrome = browsers.Found("edge", Path("msedge")), browsers.Found("chrome", Path("chrome"))
        self.assertEqual(browsers.profile(data, "ui", edge), data / "ui-profile")
        self.assertEqual(browsers.profile(data, "search", edge), data / "edge-profile")
        self.assertEqual(browsers.profile(data, "ui", chrome), data / "ui-profile-chrome")
        self.assertNotEqual(browsers.profile(data, "search", chrome), browsers.profile(data, "ui", chrome))
        self.assertIn(browsers.profile(data, "ui", chrome), browsers.ui_profiles(data))

    def test_preferred_browser_comes_first_whatever_the_path_order(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {k: Path(tmp) / f"{k}.bin" for k in ("yandex", "chrome")}
            for f in files.values():
                f.write_bytes(b"")
            with mock.patch.object(system, "browser_paths", lambda: [("yandex", files["yandex"]),
                                                                     ("edge", Path(tmp) / "missing"),
                                                                     ("chrome", files["chrome"])]), \
                    mock.patch.dict(os.environ, {"BOOKPRICE_BROWSER": ""}):
                self.assertEqual([f.key for f in browsers.installed()], ["chrome", "yandex"])
                self.assertEqual(browsers.find().label, "Google Chrome")

    def test_without_a_suitable_browser_there_is_nothing_to_drive(self):
        with mock.patch.object(system, "browser_paths", lambda: [("chrome", Path("/nowhere/chrome"))]), \
                mock.patch.dict(os.environ, {"BOOKPRICE_BROWSER": ""}):
            self.assertIsNone(browsers.find())
            with self.assertRaises(browsers.NoBrowser):
                from bookprice.browser import Browser
                Browser(Path(tempfile.mkdtemp(prefix="bp-nobrowser-"))).start()

    def test_edge_on_windows_goes_by_channel_others_by_file(self):
        chrome = browsers.Found("chrome", Path("/Applications/Google Chrome.app/Contents/MacOS/Google Chrome"))
        self.assertEqual(browsers.launch_options(chrome), {"executable_path": str(chrome.path)})
        edge = browsers.launch_options(browsers.Found("edge", Path("msedge.exe")))
        self.assertEqual(edge, {"channel": "msedge"} if WIN else {"executable_path": "msedge.exe"})


class ProcessesTest(unittest.TestCase):
    def setUp(self):
        self.base = Path(tempfile.mkdtemp(prefix="bp-proc-"))
        self.ours, self.users = self.base / "ui-profile", self.base / "ui-profile-user"
        self.procs = [sleeper(self.ours), sleeper(self.users)]
        time.sleep(1)

    def tearDown(self):
        for p in self.procs:
            if p.poll() is None:
                p.kill()
            p.wait(timeout=10)

    def names(self):
        return {Path(sys.executable).name}

    def test_our_process_is_found_by_its_profile_and_only_it(self):
        with mock.patch.object(browsers, "exe_names", self.names):
            self.assertEqual(window.find_browser(self.ours), self.procs[0].pid)
            self.assertEqual(window.find_browser(self.users), self.procs[1].pid)
            self.assertIsNone(window.find_browser(self.base / "ui-profile-chrome"))

    @unittest.skipUnless(WIN, "Windows")
    def test_winapi_sees_the_same_command_lines_as_powershell(self):
        native = dict(system._native(self.names()))
        shell = dict(system._powershell(self.names()))
        for p in self.procs:
            self.assertEqual(native[p.pid].strip(), shell[p.pid].strip())

    @unittest.skipUnless(MAC, "macOS")
    def test_closing_ours_leaves_the_users_process_alone(self):
        ours = system.Process(self.procs[0].pid, self.ours)
        self.assertTrue(ours.alive() and ours.ours())
        ours.close()
        self.assertFalse(ours.alive())
        self.assertIsNone(self.procs[1].poll())

    @unittest.skipUnless(MAC, "macOS")
    def test_a_process_without_our_profile_is_never_signalled(self):
        stranger = system.Process(self.procs[1].pid, self.ours)
        stranger.close()
        time.sleep(0.5)
        self.assertIsNone(self.procs[1].poll())


if __name__ == "__main__":
    unittest.main()
