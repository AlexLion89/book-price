"""Re-run the extractors on page snapshots from a site-check zip, offline: python tools/replay.py check.zip

Shows what the current code finds on the pages the user's Edge saw, and the resulting verdicts —
the way to fix a parser without access to the sites.
"""
import json
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from bookprice.model import Book, Offer, SourceResult  # noqa: E402
from bookprice.search import classify, evaluate  # noqa: E402
from bookprice.sources import avito, extract, meshok  # noqa: E402
from bookprice.sources.shops import SHOPS  # noqa: E402


ORIGIN = {
    "avito": "https://www.avito.ru/all/knigi_i_zhurnaly",
    "ozon": "https://www.ozon.ru/search/",
    "wildberries": "https://www.wildberries.ru/catalog/0/search.aspx",
    "market": "https://market.yandex.ru/search",
    "meshok": "https://meshok.net/listing",
    "labirint": "https://www.labirint.ru/search/q/",
    "book24": "https://book24.ru/search/",
    "bookvoed": "https://www.bookvoed.ru/search",
    "respublica": "https://www.respublica.ru/search",
    "biblioglobus": "https://www.biblio-globus.ru/catalog/search",
}


class Page:
    def __init__(self, page):
        self.page = page

    def evaluate(self, script, arg=None):
        return self.page.evaluate(script, arg)


def serve(html: str, url: str):
    def handler(route):
        if route.request.url == url:
            route.fulfill(body=html, content_type="text/html; charset=utf-8")
        else:
            route.abort()
    return handler


def extract_offers(browser, source: str, book: Book):
    if source == avito.NAME:
        return avito._offers(browser.evaluate(avito.ITEMS))
    if source == meshok.NAME:
        return extract.tiles(browser, meshok.ITEM_LINK, meshok.NAME, currency="₽|руб")
    shop = next(s for s in SHOPS if s.name == source)
    return [] if extract.nothing_found(browser) else shop.read(browser, book)


def main(zip_path: str) -> None:
    from playwright.sync_api import sync_playwright
    work = Path(tempfile.mkdtemp(prefix="bookprice-replay-"))
    with zipfile.ZipFile(zip_path) as z:
        z.extractall(work)
    report = json.loads((work / "results.json").read_text(encoding="utf-8"))
    snaps = sorted((work / "snapshots").glob("*.html"))
    by_source = {}
    for s in snaps:
        by_source.setdefault(s.stem.split("-", 2)[2], []).append(s)

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page(java_script_enabled=False)
        replayed = {}
        for source, files in by_source.items():
            if source not in ORIGIN:
                continue
            # Avito saves two pages per book (city and delivery), shops one.
            per_book = 2 if source == avito.NAME else 1
            for i, f in enumerate(files):
                book = Book(**report[min(i // per_book, len(report) - 1)]["book"])
                # Served from the site's own address: relative links ("/product/...") resolve as in the live page.
                page.unroute("**/*")
                page.route("**/*", serve(f.read_text(encoding="utf-8"), ORIGIN[source]))
                page.goto(ORIGIN[source], wait_until="domcontentloaded")
                replayed.setdefault(source, []).append(extract_offers(Page(page), source, book))
        browser.close()

    for n, item in enumerate(report):
        book = Book(**item["book"])
        results = []
        for r in item["results"]:
            offers = [Offer(**o) for o in r["offers"]]
            if r["source"] in replayed:
                # Avito saves two pages per book (city and delivery), shops one.
                per_book = 2 if r["source"] == avito.NAME else 1
                pages = replayed[r["source"]][n * per_book:(n + 1) * per_book]
                seen, offers = set(), []
                for page_offers in pages:
                    for o in page_offers:
                        if (o.ext_id or o.url) not in seen:
                            seen.add(o.ext_id or o.url)
                            offers.append(o)
            results.append(SourceResult(source=r["source"], offers=offers))
        found = classify(book, results, {})
        print(f"\n=== {book.author} — {book.title} ({book.year}) {book.isbn}")
        for r in results:
            mine = [f for f in found if f.offer.source == r.source]
            print(f"  {r.source:<13} {len(r.offers):>3} шт. {dict(Counter(f.verdict for f in mine))}, "
                  f"засчитано {sum(f.counted for f in mine)}")
            for f in sorted(mine, key=lambda f: (not f.counted, f.offer.price))[:3]:
                o = f.offer
                print(f"      [{f.verdict:<5}{'+' if f.counted else ' '}] {o.price:>7.0f} {o.title[:55]!r} "
                      f"{o.place!r} {o.note!r} | {f.reason}")
        v = evaluate(book, found, [], "excellent")
        print(f"  → выставить за {v.start}, не ниже {v.floor} ({v.scenario})")
        for reason in v.reasons:
            print("     -", reason)


if __name__ == "__main__":
    main(sys.argv[1])
