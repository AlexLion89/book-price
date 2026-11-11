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


# A stand-in for a browser: its command line carries a profile folder and, like a real one, it holds that folder's
# lock — or, with hold=False, only names the folder, as Edge does when it has fallen back to the user's own profile.
SLEEPER = """
import os, sys, time
profile, hold = sys.argv[1].split("=", 1)[1], sys.argv[2] == "hold"
os.makedirs(profile, exist_ok=True)
if hold and sys.platform == "win32":
    import ctypes
    handle = ctypes.windll.kernel32.CreateFileW(os.path.join(profile, "lockfile"), 0x40000000, 0, None, 2, 0x04000080, None)
elif hold:
    os.symlink(f"host-{os.getpid()}", os.path.join(profile, "SingletonLock"))
time.sleep(60)
"""


SLEEPER_FILE = Path(tempfile.mkdtemp(prefix="bp-sleeper-")) / "sleeper.py"
SLEEPER_FILE.write_text(SLEEPER, encoding="utf-8")


def sleeper(profile: Path, hold: bool = True) -> subprocess.Popen:
    return subprocess.Popen([sys.executable, str(SLEEPER_FILE), f"--user-data-dir={profile}", "hold" if hold else "name"],
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

    def test_the_users_choice_wins_while_that_browser_is_installed(self):
        with tempfile.TemporaryDirectory() as tmp:
            files = {k: Path(tmp) / f"{k}.bin" for k in ("edge", "yandex")}
            for f in files.values():
                f.write_bytes(b"")
            data = Path(tmp) / "data"
            data.mkdir()
            with mock.patch.object(system, "browser_paths", lambda: list(files.items())), \
                    mock.patch.dict(os.environ, {"BOOKPRICE_BROWSER": ""}), \
                    mock.patch("bookprice.paths.data_dir", lambda: data):
                self.assertEqual(browsers.find().key, "edge")
                self.assertEqual(browsers.choose("yandex").label, "Яндекс Браузер")
                self.assertEqual(browsers.find().key, "yandex")
                with self.assertRaises(ValueError):
                    browsers.choose("chrome")
                files["yandex"].unlink()
                self.assertEqual(browsers.find().key, "edge", "выбранный браузер удалили — берётся следующий")

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
        self.fallen = self.base / "ui-profile-chrome"
        self.procs = [sleeper(self.ours), sleeper(self.users), sleeper(self.fallen, hold=False)]
        time.sleep(1.5)

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
            self.assertIsNone(window.find_browser(self.base / "ui-profile-yandex"))

    def test_a_process_that_only_names_our_folder_is_not_ours(self):
        """Edge started through some launchers falls back to the user's own profile with our folder still in its
        command line: closing it would close the user's browser."""
        with mock.patch.object(browsers, "exe_names", self.names):
            self.assertIsNone(window.find_browser(self.fallen))
        self.assertFalse(system.profile_in_use(self.fallen, self.procs[2].pid))
        self.assertTrue(system.profile_in_use(self.ours, self.procs[0].pid))

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
        for pid in (self.procs[1].pid, self.procs[2].pid):
            system.Process(pid, self.ours).close()
        system.Process(self.procs[2].pid, self.fallen).close()
        time.sleep(0.5)
        self.assertIsNone(self.procs[1].poll())
        self.assertIsNone(self.procs[2].poll())


if __name__ == "__main__":
    unittest.main()
