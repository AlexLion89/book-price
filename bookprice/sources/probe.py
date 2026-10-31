"""Scouting of bookshops not yet in the search: used only by the site check. A shop is searched by its results
address when the form on its home page shows where that is, otherwise through the form itself; the result page is
kept as a snapshot, so a parser can be written from what the user's Edge actually saw."""
from __future__ import annotations

import logging
import urllib.parse
from typing import Callable, List, Tuple

from .extract import SEARCH_INPUT

log = logging.getLogger(__name__)

# (key, label, home page, results address with {q} or "" to use the form). Empty: every scouted shop is in the
# search now (Moscowbooks since 0.5.3).
SHOPS: List[Tuple[str, str, str, str]] = []
PRICES = r"() => ((document.body && document.body.innerText) || '').match(/₽|руб/g)?.length || 0"


def scout(browser, query: str, tag: str, say: Callable[[str], None]) -> None:
    for key, label, home, results in SHOPS:
        name = f"probe-{key}-{tag}"
        try:
            if results:
                browser.open(results.format(q=urllib.parse.quote(query)), name)
            else:
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
