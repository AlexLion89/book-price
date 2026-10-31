from __future__ import annotations

import urllib.parse
from typing import List

from ..matching import significant
from ..model import Book, Offer, SourceResult
from . import extract

NAME = "avito"
LABEL = "Авито"
SITE = "https://www.avito.ru"
CITY = "sankt-peterburg"
CATEGORY = "knigi_i_zhurnaly"
# Avito answers frequent queries with "Доступ ограничен: проблема с IP" — longer pauses than other sites.
PAUSE = (6.0, 10.0)
ITEM_LINK = r"avito\.ru/[^/]+/knigi_i_zhurnaly/[^/?#]+_\d{6,}"

# Avito mixes other cities into a city search (delivery). The city is only in the link's title attribute:
# "Мастер и Маргарита в Казани", while the visible link text is the bare title.
ITEMS = r"""
() => [...document.querySelectorAll('[data-marker="item"]')].map(el => {
  const a = el.querySelector('a[data-marker="item-title"]') || el.querySelector('a[itemprop="url"]');
  const priceMeta = el.querySelector('meta[itemprop="price"]');
  const priceEl = el.querySelector('[data-marker="item-price"]');
  const descMeta = el.querySelector('meta[itemprop="description"]');
  const descEl = el.querySelector('[class*="bottomBlock"] p') || el.querySelector('[class*="description"]');
  const pick = sel => { const x = el.querySelector(sel); return x ? x.innerText.trim() : ''; };
  const shown = a ? (a.innerText || '').trim() : '';
  const full = a ? (a.getAttribute('title') || shown).trim() : '';
  const city = full.startsWith(shown) ? full.slice(shown.length).trim() : '';
  return {
    id: el.getAttribute('data-item-id') || el.id || '',
    url: a ? a.href.split('?')[0] : '',
    title: shown || full,
    price: priceMeta ? parseInt(priceMeta.content, 10) : parseInt(((priceEl && priceEl.innerText) || '').replace(/\D/g, ''), 10) || 0,
    desc: descMeta ? descMeta.content : (descEl ? descEl.innerText.trim() : ''),
    age: pick('[data-marker="item-date"]'),
    place: /^в\s/.test(city) ? city : (pick('[data-marker="item-location"]') || pick('[data-marker="item-address"]')),
    delivery: /доставк/i.test(el.innerText || ''),
  };
})
"""


def query(book: Book) -> str:
    surname = significant(book.author)[-1:] if book.author else []
    return " ".join(surname + significant(book.title))


def urls(book: Book) -> List[str]:
    q = query(book)
    city = f"{SITE}/{CITY}/{CATEGORY}?" + urllib.parse.urlencode({"q": q})
    delivery = f"{SITE}/all/{CATEGORY}?" + urllib.parse.urlencode({"q": q, "d": 1})
    return [city, delivery]


def _offers(raw: List[dict]) -> List[Offer]:
    offers = []
    for r in raw:
        if not r.get("url") or not r.get("price"):
            continue
        offers.append(Offer(
            source=NAME,
            price=float(r["price"]),
            url=r["url"],
            title=r.get("title", ""),
            desc=r.get("desc", ""),
            ext_id=r.get("id") or r["url"].rsplit("_", 1)[-1],
            place=r.get("place", ""),
            age=r.get("age", ""),
            note="с доставкой" if r.get("delivery") else "",
        ))
    return offers


def search(browser, book: Book) -> SourceResult:
    city_url, delivery_url = urls(book)
    result = SourceResult(source=NAME, search_url=city_url)
    seen = set()
    try:
        for url in (city_url, delivery_url):
            browser.open(url, NAME, ready='[data-marker="item"]', pause=PAUSE)
            raw = browser.evaluate(ITEMS)
            offers = _offers(raw) or extract.tiles(browser, ITEM_LINK, NAME)
            if not offers and not extract.nothing_found(browser):
                result.snapshot = browser.snapshot(NAME, force=True)
            else:
                browser.snapshot(NAME)
            for o in offers:
                if o.ext_id not in seen:
                    seen.add(o.ext_id)
                    result.offers.append(o)
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        result.snapshot = browser.snapshot(NAME, force=True)
    return result
