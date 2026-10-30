from __future__ import annotations

import logging
import random
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Optional

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
    """Visible Edge window with its own profile: cookies survive restarts, so captchas get rarer.

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

    def start(self) -> None:
        if self._ctx:
            return
        from playwright.sync_api import sync_playwright
        self._pw = sync_playwright().start()
        self._ctx = self._pw.chromium.launch_persistent_context(
            str(self.data_dir / "edge-profile"),
            channel="msedge",
            headless=self.headless,
            locale="ru-RU",
            viewport={"width": 1280, "height": 900},
            args=["--disable-blink-features=AutomationControlled"],
            ignore_default_args=["--enable-automation"],
        )
        self._page = self._ctx.pages[0] if self._ctx.pages else self._ctx.new_page()
        if self.home:
            try:
                self._page.goto(self.home, timeout=10000)
            except Exception:
                log.warning("не открылась страница окна поиска")

    def close(self) -> None:
        try:
            if self._ctx:
                self._ctx.close()
            if self._pw:
                self._pw.stop()
        finally:
            self._ctx = self._pw = self._page = None

    @property
    def page(self):
        self.start()
        return self._page

    def _polite_pause(self) -> None:
        wait = random.uniform(*PAUSE) - (time.monotonic() - self._last_visit)
        if wait > 0:
            time.sleep(wait)

    def is_blocked(self) -> bool:
        if BLOCK_URL.search(self.page.url):
            return True
        try:
            text = self.page.inner_text("body", timeout=3000)[:3000].lower()
        except Exception:
            return False
        return len(text) < 3000 and any(m in text for m in BLOCK_MARKERS)

    def open(self, url: str, source: str, ready: str = "", ready_timeout: float = 15) -> None:
        self._polite_pause()
        log.info("%s: открываю %s", source, url)
        self.page.goto(url, wait_until="domcontentloaded", timeout=60000)
        self._last_visit = time.monotonic()
        if self.is_blocked():
            self._wait_for_human(source)
        if ready:
            try:
                self.page.wait_for_selector(ready, timeout=ready_timeout * 1000)
            except Exception:
                log.warning("%s: не дождался %s", source, ready)
        self.page.wait_for_timeout(1500)

    def _wait_for_human(self, source: str) -> None:
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
