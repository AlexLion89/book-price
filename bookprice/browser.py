from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

from . import browsers
from .system import current as system
from .sources.extract import SEARCH_INPUT

log = logging.getLogger(__name__)

BLOCK_MARKERS = [
    "доступ ограничен",
    "подтвердите, что вы не робот",
    "вы не робот",
    "проверка браузера",
    "докажите, что вы человек",
    "captcha",
    "are you a robot",
]
BLOCK_URL = re.compile(r"captcha|challenge|abt-|blocked", re.I)
CAPTCHA_WAIT = 300
PAUSE = (2.0, 5.0)


class Blocked(Exception):
    pass


class Browser:
    """Visible browser window with its own profile: cookies survive restarts, so captchas get rarer.

    Playwright's sync API is bound to the thread that started it — create and use from one worker thread.
    """

    def __init__(self, data_dir: Path, on_captcha: Optional[Callable[[str], None]] = None,
                 headless: bool = False, keep_snapshots: bool = False, home: str = "") -> None:
        self.data_dir = data_dir
        self.home = home
        self.on_captcha = on_captcha or (lambda source: None)
        self.headless = headless
        self.keep_snapshots = keep_snapshots
        self.snapshot_dir = data_dir / "snapshots"
        self._pw = None
        self._ctx = None
        self._page = None
        self._last_visit = 0.0
        self.found = browsers.find()

    @property
    def profile_dir(self) -> Path:
        return browsers.profile(self.data_dir, "search", self.found) if self.found else self.data_dir / "edge-profile"

    def start(self) -> None:
        if self._ctx:
            return
        # The user may have chosen another browser since the last search.
        self.found = browsers.find()
        if not self.found:
            raise browsers.NoBrowser(browsers.NO_BROWSER)
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        # The visible window is maximized and the page takes the window's size: a fixed page taller than a laptop
        # screen hides the bottom of Avito's captcha, its slider included.
        size = {"viewport": {"width": 1280, "height": 900}} if self.headless else {"no_viewport": True}
        log.info("окно поиска: %s (%s)", self.found.label, self.found.path)
        self._ctx = self._pw.chromium.launch_persistent_context(
            str(self.profile_dir),
            **browsers.launch_options(self.found),
            headless=self.headless,
            locale="ru-RU",
            args=["--disable-blink-features=AutomationControlled", "--disable-sync", "--no-first-run",
                  *system.SEARCH_ARGS, *([] if self.headless else ["--start-maximized"])],
            ignore_default_args=["--enable-automation"],
            **size,
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        if self.home:
            try:
                self._page.goto(self.home, timeout=10000)
            except Exception:
                log.warning("не открылась страница окна поиска")

    def close(self) -> None:
        started = self._ctx is not None
        try:
            if self._ctx:
                self._ctx.close()
            if self._pw:
                self._pw.stop()
        finally:
            self._ctx = self._pw = self._page = None
        if started:
            from .window import sweep
            sweep(self.profile_dir)

    @property
    def page(self):
        self.start()
        return self._page

    def _polite_pause(self, pause=PAUSE) -> None:
        wait = random.uniform(*pause) - (time.monotonic() - self._last_visit)
        if wait > 0:
            time.sleep(wait)

    def is_blocked(self) -> bool:
        if BLOCK_URL.search(self.page.url):
            return True
        try:
            if any(m in self.page.title().lower() for m in BLOCK_MARKERS):
                return True
            text = self.page.inner_text("body", timeout=3000)[:3000].lower()
        except Exception:
            return False
        return len(text) < 3000 and any(m in text for m in BLOCK_MARKERS)

    def open(self, url: str, source: str, ready: str = "", ready_timeout: float = 15, pause=PAUSE) -> None:
        self._polite_pause(pause)
        log.info("%s: открываю %s", source, url)
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self.arrived(source, ready, ready_timeout)

    def search_form(self, home: str, query: str, source: str, ready: str, ready_timeout: float = 15) -> str:
        """Search through the form on a shop's home page — for shops whose result pages cannot be opened by
        address. Returns the address of the results."""
        self.open(home, source, ready=SEARCH_INPUT, ready_timeout=20)
        box = next((b for b in self.page.query_selector_all(SEARCH_INPUT) if b.is_visible()), None)
        if not box:
            raise RuntimeError("на главной странице нет поля поиска")
        box.fill(query)
        with self.page.expect_navigation(wait_until="domcontentloaded", timeout=60000):
            box.press("Enter")
        log.info("%s: результаты поиска — %s", source, self.page.url)
        self.arrived(source, ready, ready_timeout)
        return self.page.url

    def forbidden(self) -> bool:
        try:
            return self.page.title().strip().lower().startswith("403 forbidden")
        except Exception:
            return False

    def arrived(self, source: str, ready: str = "", ready_timeout: float = 15) -> None:
        self._last_visit = time.monotonic()
        if self.is_blocked():
            self.wait_for_human(source)
        if ready:
            try:
                self._wait_ready(ready, ready_timeout)
            except Exception:
                # Avito swaps the page for "Доступ ограничен" after it has loaded: look again before giving up.
                if not self.is_blocked():
                    log.warning("%s: не дождался %s", source, ready[:120])
                else:
                    self.wait_for_human(source)
                    try:
                        self._wait_ready(ready, ready_timeout)
                    except Exception:
                        log.warning("%s: после проверки не дождался %s", source, ready[:120])
        self.page.wait_for_timeout(1500)

    def _wait_ready(self, ready: str, timeout: float) -> None:
        """ready is a CSS selector or a JS predicate "() => …"."""
        if ready.lstrip().startswith("()"):
            self.page.wait_for_function(ready, timeout=timeout * 1000)
        else:
            self.page.wait_for_selector(ready, timeout=timeout * 1000)

    def wait_for_human(self, source: str) -> None:
        log.warning("%s: проверка «не робот», жду человека", source)
        self.page.bring_to_front()
        self.on_captcha(source)
        deadline = time.monotonic() + CAPTCHA_WAIT
        while time.monotonic() < deadline:
            self.page.wait_for_timeout(2000)
            if not self.is_blocked():
                log.info("%s: проверка пройдена", source)
                self.page.wait_for_timeout(2000)
                return
        raise Blocked(f"{source}: проверка «не робот» не пройдена за {CAPTCHA_WAIT // 60} мин")

    def snapshot(self, source: str, force: bool = False) -> str:
        if not (force or self.keep_snapshots):
            return ""
        self.snapshot_dir.mkdir(parents=True, exist_ok=True)
        stem = self.snapshot_dir / f"{datetime.now():%Y%m%d-%H%M%S}-{source}"
        try:
            stem.with_suffix(".html").write_text(self.page.content(), encoding="utf-8")
            self.page.screenshot(path=str(stem.with_suffix(".png")), full_page=False)
        except Exception:
            log.exception("%s: не удалось сохранить снимок", source)
        return str(stem)

    def evaluate(self, script: str, arg=None):
        return self.page.evaluate(script, arg)
