"""Scouting of bookshops not yet in the search: used only by the site check. Each shop is searched through the
form on its home page — no guessing of its search URL — and the result page is kept as a snapshot, so a parser
can be written from what the user's Edge actually saw."""
from __future__ import annotations

import logging
from typing import Callable, List, Tuple

from .extract import SEARCH_INPUT

log = logging.getLogger(__name__)

# spbdk.ru and mdk-arbat.ru, the old addresses, no longer open (31.10.2026).
SHOPS: List[Tuple[str, str, str]] = [
    ("dkspb", "Дом книги (СПб)", "https://dk-spb.ru/"),
    ("moscowbooks", "Московский дом книги", "https://www.moscowbooks.ru/"),
]
PRICES = r"() => ((document.body && document.body.innerText) || '').match(/₽|руб/g)?.length || 0"


def scout(browser, query: str, tag: str, say: Callable[[str], None]) -> None:
    for key, label, home in SHOPS:
        name = f"probe-{key}-{tag}"
        try:
            browser.open(home, name, ready=SEARCH_INPUT, ready_timeout=20)
            box = next((b for b in browser.page.query_selector_all(SEARCH_INPUT) if b.is_visible()), None)
            if not box:
                say(f"  {label}: на главной не нашлось видимое поле поиска")
                browser.snapshot(name, force=True)
                continue
            box.fill(query)
            box.press("Enter")
            browser.page.wait_for_timeout(7000)
            if browser.is_blocked():
                browser.wait_for_human(name)
            prices = browser.evaluate(PRICES)
            browser.snapshot(name, force=True)
            say(f"  {label}: {browser.page.url[:110]} — цен на странице: {prices}")
        except Exception as e:
            log.warning("%s: разведка не удалась: %s", key, e)
            say(f"  {label}: не получилось — {type(e).__name__}")
            browser.snapshot(name, force=True)
