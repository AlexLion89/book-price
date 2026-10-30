"""Online shops opened in Edge: Ozon, Wildberries, Yandex Market. Search by ISBN when it is known."""
from __future__ import annotations

import re
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

# Ozon shows its own search results in several tile grids, then "Возможно, вам понравится" with unrelated goods.
OZON_SKIP_RECOMMENDATIONS = r"""
() => {
  const marker = [...document.querySelectorAll('h2, h3, span, div')].find(e =>
    e.children.length <= 2 && /^(Возможно, вам понравится|Вам может понравиться|Похожие товары|Рекомендуем)/i
      .test((e.innerText || '').trim()));
  if (!marker) return 0;
  let skipped = 0;
  for (const grid of document.querySelectorAll('[data-widget="tileGridDesktop"]')) {
    if (marker.compareDocumentPosition(grid) & Node.DOCUMENT_POSITION_FOLLOWING) {
      grid.setAttribute('data-bp-skip', '1');
      skipped++;
    }
  }
  return skipped;
}
"""

# Wildberries hashes its CSS classes; data-testid attributes and the link's aria-label stay.
WB_CARDS = r"""
() => [...document.querySelectorAll('article.product-card, [data-nm-id]')].filter(c => c.getAttribute('data-nm-id')).map(c => {
  const link = c.querySelector('a[data-testid="product-card-link"]') || c.querySelector('a[href*="/catalog/"]');
  const brand = c.querySelector('[data-testid="productBrand"]');
  const name = c.querySelector('[data-testid="productName"]');
  const price = c.querySelector('[data-testid="product-card-current-price"]') || c.querySelector('ins');
  const title = (link && link.getAttribute('aria-label')) || (name && name.innerText) || '';
  return {
    url: link ? link.href.split('?')[0] : '',
    title: title.replace(/\s+/g, ' ').trim(),
    text: [brand && brand.innerText, name && name.innerText].filter(Boolean).join(' / ').replace(/\s+/g, ' ').trim(),
    price: parseInt(((price && price.innerText) || '').replace(/\D/g, ''), 10) || 0,
    id: c.getAttribute('data-nm-id') || '',
  };
})
"""
USED_MARK = re.compile(r"\bб/у\b|\bбу\b|уценк", re.I)

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
    prepare: str = ""

    def search_url(self, book: Book) -> str:
        return self.url(book.isbn or f"{book.title} {book.author}".strip())

    def _from_specific(self, browser) -> List[Offer]:
        if not self.specific:
            return []
        raw = browser.evaluate(self.specific) or []
        return [Offer(source=self.name, price=float(r["price"]), url=r["url"], title=r["title"], text=r.get("text", ""),
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
            if self.prepare:
                browser.evaluate(self.prepare)
            result.offers = self._from_specific(browser) or extract.tiles(browser, self.link_pattern, self.name)
            for o in result.offers:
                if USED_MARK.search(o.title):
                    o.note = "б/у"
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
            r"ozon\.ru/product/", '[data-widget="tileGridDesktop"], [data-widget="webPrice"]',
            prepare=OZON_SKIP_RECOMMENDATIONS)
WILDBERRIES = Shop("wildberries", "Wildberries", _q("https://www.wildberries.ru/catalog/0/search.aspx", "search"),
                   r"wildberries\.ru/catalog/\d+/detail", "[data-nm-id]", WB_CARDS)
MARKET = Shop("market", "Яндекс Маркет", _q("https://market.yandex.ru/search", "text"),
              r"market\.yandex\.ru/(product--|card/)", '[data-auto="snippet-title"]', MARKET_SNIPPETS)

SHOPS = [OZON, WILDBERRIES, MARKET]
