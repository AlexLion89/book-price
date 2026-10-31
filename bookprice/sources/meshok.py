"""Мешок — auction of collectibles and old books. Searched through the site's own form: its search URL
format is not known to be stable, the form is."""
from __future__ import annotations

import re

from ..model import Book, Offer, SourceResult
from . import alib, extract

NAME = "meshok"
LABEL = "Мешок (аукцион)"
SITE = "https://meshok.net/"
LEADING_PRICE = re.compile(r"^\s*[\d\s]+(₽|руб\.?)\s*")
ITEM_LINK = r"meshok\.net/item/\d+"
SEARCH_INPUT = ('input[type="search"], input[name="search"], input[name*="search" i], '
                'input[placeholder*="оиск"], input[placeholder*="айти"]')


def clean(offer: Offer) -> Offer:
    """A lot's link wraps the whole card: "170 ₽ Книга … / А. Степной, 2009 г. Условия и стоимость доставки …"."""
    title = LEADING_PRICE.sub("", offer.title)
    offer.title = title.split("Условия")[0].strip(" .,")
    return offer


def search(browser, book: Book) -> SourceResult:
    query = alib.query(book)
    result = SourceResult(source=NAME, search_url=SITE)
    try:
        browser.open(SITE, NAME, ready=SEARCH_INPUT)
        box = browser.page.query_selector(SEARCH_INPUT)
        if not box:
            raise RuntimeError("на главной странице не нашлось поле поиска")
        box.fill(query)
        with browser.page.expect_navigation(wait_until="domcontentloaded", timeout=30000):
            box.press("Enter")
        browser.page.wait_for_timeout(2500)
        if browser.is_blocked():
            browser.wait_for_human(NAME)
        result.search_url = browser.page.url
        if extract.nothing_found(browser):
            browser.snapshot(NAME)
            return result
        result.offers = [clean(o) for o in extract.tiles(browser, ITEM_LINK, NAME, currency="₽|руб")]
        result.snapshot = browser.snapshot(NAME, force=not result.offers)
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        result.snapshot = browser.snapshot(NAME, force=True)
    return result
