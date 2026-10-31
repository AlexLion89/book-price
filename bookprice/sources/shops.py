"""Online shops opened in Edge: marketplaces (Ozon, Wildberries, Yandex Market) and bookshops (Labirint, Book24,
Bookvoed, Respublica, Biblio-Globus, Dom Knigi SPb, Moscowbooks). Search by ISBN when it is known."""
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
# "Предзаказ" stays in stock, as in Chitai-gorod: the book is coming and can be bought now.
OUT_OF_STOCK = re.compile(r"нет в наличии|нет в продаже|ожидается|сообщить о поступлении|узнать о поступлении|"
                          r"временно отсутствует", re.I)

# Bookshops put recommendations in carousels next to the results, or under a heading like "Возможно, вам
# понравится" instead of them on a miss (Biblio-Globus says "товаров сейчас нет" below a long catalogue menu).
SKIP_RECOMMENDATIONS = r"""
() => {
  let skipped = 0;
  const skip = el => { if (!el.closest('[data-bp-skip]')) { el.setAttribute('data-bp-skip', '1'); skipped++; } };
  for (const el of document.querySelectorAll('[class]')) {
    if (/slider|carousel|shelf|embla|swiper|recommend/i.test(el.getAttribute('class'))) skip(el);
  }
  // The whole heading, not its start: Book24's filter "Рекомендуемый возраст" sits right before the results.
  const marker = [...document.querySelectorAll('h1, h2, h3, h4, div, span')].find(e => e.children.length <= 2
    && /^(Возможно, вам понравится|Вам может понравиться|Рекомендуем|Похожие товары|Смотрите также)[\s:.!]*$/i
      .test((e.innerText || '').trim()));
  let block = marker;
  while (block && !block.nextElementSibling) block = block.parentElement;
  for (let el = block && block.nextElementSibling; el; el = el.nextElementSibling) skip(el);
  return skipped;
}
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
    prepare: str = ""
    currency: str = "₽"
    # A bookshop, not a marketplace: its sellers are the shop itself, tiles say when a book is out of stock,
    # and a single answer to an ISBN query is that very edition.
    bookshop: bool = False
    # Searched through the form on this home page: the shop answers its results address with 404.
    home: str = ""
    # ISBN queries are of no use there: Moscowbooks answers one with 97 unrelated books, Respublica with 403.
    by_title: bool = False

    def query(self, book: Book) -> str:
        return (not self.by_title and book.isbn) or f"{book.title} {book.author}".strip()

    def search_url(self, book: Book) -> str:
        return self.url(self.query(book))

    def read(self, browser, book: Book) -> List[Offer]:
        """Offers on the opened page of search results."""
        if self.prepare:
            browser.evaluate(self.prepare)
        offers = self._from_specific(browser) or extract.tiles(browser, self.link_pattern, self.name,
                                                               currency=self.currency)
        for o in offers:
            if USED_MARK.search(o.title):
                o.note = "б/у"
            if self.bookshop and OUT_OF_STOCK.search(o.text):
                o.in_stock, o.note = False, "нет в наличии"
        if self.bookshop and book.isbn and self.query(book) == book.isbn and len(offers) == 1:
            offers[0].by_isbn = True
        return offers

    def _from_specific(self, browser) -> List[Offer]:
        if not self.specific:
            return []
        raw = browser.evaluate(self.specific) or []
        return [Offer(source=self.name, price=float(r["price"]), url=r["url"], title=r["title"], text=r.get("text", ""),
                      ext_id=r.get("id") or r["url"]) for r in raw if r.get("price") and r.get("url")]

    def search(self, browser, book: Book) -> SourceResult:
        result = SourceResult(source=self.name, search_url=self.search_url(book))
        try:
            timeout = 12 if self.bookshop else 15
            if self.home:
                url = browser.search_form(self.home, self.query(book), self.name, self.ready, timeout)
                # A results page reached by POST cannot be opened again by its address: link the home page.
                result.search_url = url if "?" in url else self.home
            else:
                browser.open(result.search_url, self.name, ready=self.ready, ready_timeout=timeout)
                if self.bookshop and browser.forbidden():
                    # Respublica answered 403 to searches opened straight by address (check-home-7) and served
                    # the same search after its home page had been visited.
                    root = urllib.parse.urlsplit(result.search_url)
                    browser.open(f"{root.scheme}://{root.netloc}/", self.name)
                    browser.open(result.search_url, self.name, ready=self.ready, ready_timeout=timeout)
                    if browser.forbidden():
                        raise Forbidden("сайт не пустил (403)")
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
            result.offers = self.read(browser, book)
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


class Forbidden(Exception):
    pass


def _bookshop(name: str, label: str, url: Callable[[str], str], link_pattern: str, currency: str = "₽",
              home: str = "", by_title: bool = False) -> Shop:
    # Ready when a product link shows up or the shop says it has nothing: a miss must not cost the full wait.
    return Shop(name, label, url, link_pattern, extract.link_or_nothing(link_pattern), prepare=SKIP_RECOMMENDATIONS,
                currency=currency, bookshop=True, home=home, by_title=by_title)


# Addresses and page layout from the scouting snapshots of 31.10.2026 (check-home-5 in the task folder).
LABIRINT = _bookshop("labirint", "Лабиринт",
                     lambda q: f"https://www.labirint.ru/search/{urllib.parse.quote(q, safe='')}/?stype=0",
                     r"labirint\.ru/books/\d+")
BOOK24 = _bookshop("book24", "Book24", _q("https://book24.ru/search/", "q"), r"book24\.ru/product/")
BOOKVOED = _bookshop("bookvoed", "Буквоед", _q("https://www.bookvoed.ru/search", "q"), r"bookvoed\.ru/product/")
# Respublica draws the ruble sign with CSS: its prices are bare numbers in the page text. Its server answers
# 403 to an ISBN in the search address even after a visit to the home page (check-home-8), titles pass.
RESPUBLICA = _bookshop("respublica", "Республика", _q("https://www.respublica.ru/search", "query"),
                       r"respublica\.ru/knigi/.+/\d+-", currency="", by_title=True)
# Biblio-Globus answers /catalog/search?query=… with 404 (check-home-6): only its own form leads to results.
BIBLIOGLOBUS = _bookshop("biblioglobus", "Библио-Глобус", _q("https://www.biblio-globus.ru/catalog/search", "query"),
                         r"biblio-globus\.ru/product/\d+", home="https://www.biblio-globus.ru/")

# Saint Petersburg's Dom Knigi moved from spbdk.ru to dk-spb.ru; layout from check-home-6.
DKSPB = _bookshop("dkspb", "Дом книги (СПб)", _q("https://dk-spb.ru/catalog/", "q"),
                  r"dk-spb\.ru/catalog/[^/?#]+-\d+/?(?:[?#]|$)")

# Moscow's Dom Knigi on the Arbat sells as moscowbooks.ru; its form goes to /search/?text= (check-home-7).
MOSCOWBOOKS = _bookshop("moscowbooks", "Московский дом книги", _q("https://www.moscowbooks.ru/search/", "text"),
                        r"moscowbooks\.ru/book/\d+", by_title=True)

SHOPS = [OZON, WILDBERRIES, MARKET, LABIRINT, BOOK24, BOOKVOED, RESPUBLICA, BIBLIOGLOBUS, DKSPB, MOSCOWBOOKS]
