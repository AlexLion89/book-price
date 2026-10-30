"""Online shops opened in Edge: Ozon, Wildberries, Yandex Market. Search by ISBN when it is known."""
from __future__ import annotations

import urllib.parse
from dataclasses import dataclass
from typing import Callable, List

from ..model import Book, Offer, SourceResult
from . import extract

OZON_PRODUCT = r"""
() => {
  if (!location.pathname.startsWith('/product/')) return null;
  const h1 = document.querySelector('h1');
  const priceBox = document.querySelector('[data-widget="webPrice"]');
  const m = ((priceBox && priceBox.innerText) || '').match(/(\d[\d\s]*)\s*₽/);
  const out = /нет в наличии|закончился|товар закончился/i.test((document.body.innerText || '').slice(0, 4000))
              || !!document.querySelector('[data-widget="webOutOfStock"]');
  return {url: location.href.split('?')[0], title: h1 ? h1.innerText.trim() : document.title,
          price: m ? parseInt(m[1].replace(/\D/g, ''), 10) : 0, out};
}
"""

WB_CARDS = r"""
() => [...document.querySelectorAll('.product-card')].map(c => {
  const link = c.querySelector('a.product-card__link') || c.querySelector('a[href*="/catalog/"]');
  const brand = c.querySelector('.product-card__brand');
  const name = c.querySelector('.product-card__name');
  const price = c.querySelector('.price__lower-price') || c.querySelector('[class*="price"]');
  return {
    url: link ? link.href.split('?')[0] : '',
    title: [brand && brand.innerText, name && name.innerText].filter(Boolean).join(' ').replace(/\s+/g, ' ').trim(),
    price: parseInt(((price && price.innerText) || '').replace(/\D/g, ''), 10) || 0,
    id: c.getAttribute('data-nm-id') || '',
  };
})
"""

MARKET_SNIPPETS = r"""
() => [...document.querySelectorAll('[data-auto="snippet-title"], [data-auto="snippet-title-header"]')].map(t => {
  let tile = t;
  for (let i = 0; i < 8 && tile && !tile.querySelector('[data-auto="snippet-price-current"]'); i++) tile = tile.parentElement;
  const price = tile && tile.querySelector('[data-auto="snippet-price-current"]');
  const link = t.closest('a') || (tile && tile.querySelector('a[href*="/product--"], a[href*="/card/"]'));
  return {
    url: link ? link.href.split('?')[0] : '',
    title: t.innerText.replace(/\s+/g, ' ').trim(),
    price: parseInt(((price && price.innerText) || '').replace(/\D/g, ''), 10) || 0,
  };
})
"""


@dataclass
class Shop:
    name: str
    label: str
    url: Callable[[str], str]
    link_pattern: str
    ready: str
    specific: str = ""

    def search_url(self, book: Book) -> str:
        return self.url(book.isbn or f"{book.title} {book.author}".strip())

    def _from_specific(self, browser) -> List[Offer]:
        if not self.specific:
            return []
        raw = browser.evaluate(self.specific) or []
        return [Offer(source=self.name, price=float(r["price"]), url=r["url"], title=r["title"],
                      ext_id=r.get("id") or r["url"]) for r in raw if r.get("price") and r.get("url")]

    def search(self, browser, book: Book) -> SourceResult:
        result = SourceResult(source=self.name, search_url=self.search_url(book))
        try:
            browser.open(result.search_url, self.name, ready=self.ready)
            if self.name == "ozon":
                product = browser.evaluate(OZON_PRODUCT)
                if product and product.get("price"):
                    result.offers = [Offer(source=self.name, price=float(product["price"]), url=product["url"],
                                           title=product["title"], in_stock=not product["out"], ext_id=product["url"],
                                           note="нет в наличии" if product["out"] else "")]
                    browser.snapshot(self.name)
                    return result
            if extract.nothing_found(browser):
                browser.snapshot(self.name)
                return result
            result.offers = self._from_specific(browser) or extract.tiles(browser, self.link_pattern, self.name)
            if not result.offers:
                result.snapshot = browser.snapshot(self.name, force=True)
            else:
                browser.snapshot(self.name)
        except Exception as e:
            result.error = f"{type(e).__name__}: {e}"
            result.snapshot = browser.snapshot(self.name, force=True)
        return result


def _q(base: str, key: str, extra: str = ""):
    return lambda q: f"{base}?" + urllib.parse.urlencode({key: q}) + extra


OZON = Shop("ozon", "Озон", _q("https://www.ozon.ru/search/", "text", "&from_global=true"),
            r"ozon\.ru/product/", '[data-widget="searchResultsV2"], [data-widget="webPrice"]')
WILDBERRIES = Shop("wildberries", "Wildberries", _q("https://www.wildberries.ru/catalog/0/search.aspx", "search"),
                   r"wildberries\.ru/catalog/\d+/detail", ".product-card", WB_CARDS)
MARKET = Shop("market", "Яндекс Маркет", _q("https://market.yandex.ru/search", "text"),
              r"market\.yandex\.ru/(product--|card/)", '[data-auto="snippet-title"]', MARKET_SNIPPETS)

SHOPS = [OZON, WILDBERRIES, MARKET]
