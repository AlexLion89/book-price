"""Bookshop pages shaped like the scouting snapshots of 31.10.2026, read inside a real Edge."""
import tempfile
import unittest
from pathlib import Path

from bookprice.model import Book, Offer, SourceResult
from bookprice.search import classify, out_of_print
from bookprice.sources import extract
from bookprice.sources.shops import BIBLIOGLOBUS, BOOK24, BOOKVOED, DKSPB, LABIRINT, RESPUBLICA
from tests.test_extract import FakeBrowser, edge

MASTER = Book(title="Мастер и Маргарита", author="Михаил Булгаков", isbn="9785389016866", year=2012)

BOOKVOED_ISBN = """
<div class="app-catalog__products product-list">
  <div class="product-card">
    <a href="https://www.bookvoed.ru/product/master-i-margarita-5422094"><img alt=""></a>
    <div class="product-description"><a class="product-description__link"
       href="https://www.bookvoed.ru/product/master-i-margarita-5422094">Мастер и Маргарита</a>
       <a href="https://www.bookvoed.ru/author/bulgakov-1">Михаил Булгаков</a></div>
    <div class="price-info"><span class="price-info__old-price">395 ₽</span>
      <span class="price-info__current-price"><span class="price-info__price">319 ₽</span></span></div>
    <button>Предзаказ</button>
  </div>
</div>
<div class="product-slider"><ul class="product-slider__book-list"><li>
  <div class="product-card"><a href="https://www.bookvoed.ru/product/feeria-8857136">Феерия</a>
    <span class="price-info__price">449 ₽</span><button>Купить</button></div></li></ul></div>
"""

RESPUBLICA_TITLE = """
<div class="flex flex-wrap">
  <div class="p-5">
    <a href="https://www.respublica.ru/knigi/detskie-knigi/hudozhestvennaya-literatura/1541802-nosov-n-n-neznayka-na-lune">
      <img alt=""><div>-14%</div></a>
    <div class="mb-1.5 flex flex-row"><span class="text-xl font-medium">2 550</span>
      <span class="text-gray-300 line-through whitespace-nowrap">2 950</span></div>
    <div><span>+76</span></div>
    <h3><a class="title-link text-sm"
      href="https://www.respublica.ru/knigi/detskie-knigi/hudozhestvennaya-literatura/1541802-nosov-n-n-neznayka-na-lune">Незнайка на Луне. Юбилейное издание</a></h3>
    <a href="https://www.respublica.ru/authors/44730">Николай Носов</a>
    <button>В корзину</button>
  </div>
</div>
"""

LABIRINT_TITLE = """
<div class="search-result">
  <div class="product-card">
    <div class="product-card__top"><a class="product-card__label" href="https://www.labirint.ru/books/570265/">еще 1 день −50% по акции</a></div>
    <div class="product-card__price-container"><div class="product-card__price-current">2 664 ₽</div>
      <div class="product-card__price-val-old tooltip"><div>5 327</div></div><div>-2 664 ₽ по акции</div></div>
    <a class="product-card__name" href="https://www.labirint.ru/books/570265/">Незнайка на Луне</a>
    <div class="product-card__info">Носов Николай Николаевич Издательский дом Мещерякова</div>
    <button>В КОРЗИНУ</button>
  </div>
  <div class="product-card">
    <div class="product-card__price-current">1 952 ₽</div>
    <a class="product-card__name" href="https://www.labirint.ru/books/911553/">Незнайка на Луне</a>
    <div class="product-card__info">Носов Николай Николаевич Махаон</div>
    <span>Ожидается</span>
  </div>
</div>
"""

BIBLIOGLOBUS_MISS = """
<div class="box title_box">
  <div class="catalog-menu">Художественная литература Книги для детей</div>
  <p>По запросу «9785389016866» товаров сейчас нет.</p>
  <h4>Возможно, вам понравится</h4>
  <div class="row products">
    <div class="card"><h5 class="card-title">Россия плюс Китай <span class="card-author">Зуенко И.Ю.</span></h5>
      <div class="price_item_wrapper"><span class="price_item_title">Цена в магазине:</span><s>939 ₽</s> 610 ₽</div>
      <a href="https://www.biblio-globus.ru/product/11107207">Подробнее</a></div>
  </div>
</div>
"""

BOOK24_TITLE = """
<div class="catalog">
  <div class="catalog__sidebar"><div class="filter"><div class="filter-holder filter__item">Рекомендуемый возраст<br>7-11 лет</div></div></div>
  <div class="catalog__product-list-holder"><div class="product-list catalog__product-list">
    <article class="product-card"><div class="product-card-price"><span>1 699 ₽</span>
      <div class="product-card-price__old"><span class="product-card-price__old-value">2 039 ₽</span></div></div>
      <a class="product-card__name" href="https://book24.ru/product/neznajka-na-lune-7756781/">Незнайка на Луне</a>
      <button>В корзину</button></article>
  </div></div>
</div>
"""

MESHOK_LOT = """
<div class="itemCard_2d878">
  <a class="wrapper_2d878" href="https://meshok.net/item/364324247_Nosov_1996">
    <div class="price_2d878 withStrikePrice_2d878"><span>6 000 ₽</span><div class="strikePrice_2d878">8 500 ₽</div></div>
    <div class="itemTitle_2d878">Носов Н.Н. Незнайка на Луне. М.: Дом, 1996</div></a>
  <div><span>700 ₽</span><span class="free_009e1"> или бесплатно</span></div>
  <span class="name_e6b31"><a href="https://meshok.net/user/baton">baton 2</a></span>
</div>
"""


DKSPB_PAGE = """
<div class="catalog-items">
  <div class="item"><a href="https://dk-spb.ru/catalog/neznayka-na-lune-ill-o-gorbushina-900147591"><img alt=""></a>
    <a class="item-title" href="https://dk-spb.ru/catalog/neznayka-na-lune-ill-o-gorbushina-900147591">Незнайка на Луне (илл. О. Горбушина)</a>
    <div>1 750 ₽</div><button>В корзину</button></div>
  <div class="item"><a href="https://dk-spb.ru/catalog/master-i-margarita-5810">Мастер и Маргарита</a>
    <span>Нет в наличии</span><button>В лист ожидания</button></div>
  <a href="https://dk-spb.ru/catalog/knigi/detskaya-literatura/">Детская литература — от 99 ₽</a>
</div>
"""


class BookshopPagesTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.env = edge()
        if not cls.env:
            raise unittest.SkipTest("нет Playwright или Edge")
        cls.page = cls.env[1].new_page()

    @classmethod
    def tearDownClass(cls):
        cls.env[1].close()
        cls.env[0].stop()

    def load(self, html):
        self.page.set_content(html)
        return FakeBrowser(self.page)

    def test_single_isbn_answer_is_that_edition(self):
        offers = BOOKVOED.read(self.load(BOOKVOED_ISBN), MASTER)
        self.assertEqual([(o.price, o.title, o.by_isbn, o.in_stock) for o in offers],
                         [(319, "Мастер и Маргарита", True, True)])
        found = classify(MASTER, [SourceResult(source="bookvoed", offers=offers)], {})
        self.assertEqual((found[0].verdict, found[0].counted), ("yes", True))

    def test_title_search_is_not_taken_as_exact(self):
        no_isbn = Book(title="Мастер и Маргарита", author="Михаил Булгаков")
        self.assertFalse(BOOKVOED.read(self.load(BOOKVOED_ISBN), no_isbn)[0].by_isbn)

    def test_bare_numbers_when_ruble_sign_is_drawn_by_css(self):
        offers = RESPUBLICA.read(self.load(RESPUBLICA_TITLE), Book(title="Незнайка на Луне"))
        self.assertEqual([(o.price, o.title) for o in offers], [(2550, "Незнайка на Луне. Юбилейное издание")])

    def test_labirint_promo_label_old_price_and_waiting_list(self):
        offers = LABIRINT.read(self.load(LABIRINT_TITLE), Book(title="Незнайка на Луне"))
        self.assertEqual([(o.price, o.title, o.in_stock) for o in offers],
                         [(2664, "Незнайка на Луне", True), (1952, "Незнайка на Луне", False)])

    def test_miss_with_recommendations_gives_nothing(self):
        b = self.load(BIBLIOGLOBUS_MISS)
        self.assertEqual(BIBLIOGLOBUS.read(b, MASTER), [])

    def test_filter_named_like_a_heading_keeps_results(self):
        offers = BOOK24.read(self.load(BOOK24_TITLE), Book(title="Незнайка на Луне"))
        self.assertEqual([o.price for o in offers], [1699])

    def test_meshok_lot_with_strike_price_and_delivery(self):
        offers = extract.tiles(self.load(MESHOK_LOT), r"meshok\.net/item/\d+", "meshok", currency="₽|руб")
        self.assertEqual([o.price for o in offers], [6000])
        self.assertNotIn("baton", offers[0].title)

    def test_dom_knigi_products_not_categories(self):
        offers = DKSPB.read(self.load(DKSPB_PAGE), Book(title="Незнайка на Луне"))
        self.assertEqual([(o.price, o.title) for o in offers], [(1750, "Незнайка на Луне (илл. О. Горбушина)")])

    def test_kopecks_are_dropped(self):
        page = """<div><a href="https://www.moscowbooks.ru/book/50091533/">Незнайка на Луне</a><b>1 851.00 ₽</b></div>"""
        offers = extract.tiles(self.load(page), r"moscowbooks\.ru/book/\d+", "moscowbooks")
        self.assertEqual([o.price for o in offers], [1851])

    def test_page_ready_on_miss(self):
        b = self.load("<p>По вашему запросу товары не найдены.</p>")
        self.assertTrue(b.evaluate(RESPUBLICA.ready))
        self.assertTrue(extract.nothing_found(b))


BG_HOME = """<title>Библио-Глобус</title><form action="/Search" method="post">
  <input type="text" name="search" placeholder="Поиск..."></form>"""
BG_RESULTS = """<title>Результаты поиска</title><div class="row products">
  <div class="card"><h5 class="card-title">Незнайка на Луне <span class="card-author">Носов Н.Н.</span></h5>
    <div class="price_item_wrapper"><span class="price_item_title">Цена в магазине:</span> 1689 ₽</div>
    <a href="https://www.biblio-globus.ru/product/10827165">Подробнее</a></div></div>"""


class FormSearchTest(unittest.TestCase):
    def test_shop_searched_through_its_home_form(self):
        try:
            from bookprice.browser import Browser
            browser = Browser(Path(tempfile.mkdtemp(prefix="bp-form-")), headless=True)
            browser.start()
        except Exception:
            raise unittest.SkipTest("нет Playwright или Edge")
        pages = {"https://www.biblio-globus.ru/": BG_HOME, "https://www.biblio-globus.ru/Search": BG_RESULTS}
        seen = []

        def handler(route):
            url = route.request.url
            seen.append((route.request.method, url))
            if url in pages:
                route.fulfill(body=pages[url], content_type="text/html; charset=utf-8")
            else:
                route.abort()

        try:
            browser.page.route("**/*", handler)
            result = BIBLIOGLOBUS.search(browser, Book(title="Незнайка на Луне", author="Николай Носов"))
        finally:
            browser.close()
        self.assertEqual(result.error, "")
        self.assertEqual(result.search_url, "https://www.biblio-globus.ru/Search")
        self.assertIn(("POST", "https://www.biblio-globus.ru/Search"), seen)
        self.assertEqual([(o.price, o.title) for o in result.offers], [(1689, "Незнайка на Луне Носов Н.Н.")])


class BookshopKindTest(unittest.TestCase):
    def test_bookshop_is_never_a_reseller(self):
        book = Book(title="Мастер и Маргарита", author="Михаил Булгаков", isbn="9785389016866", year=2012)
        cg = Offer(source="chitai_gorod", price=799, title="Мастер и Маргарита", in_stock=False)
        lab = Offer(source="labirint", price=450, title="Мастер и Маргарита (1990)", text="Махаон")
        oz = Offer(source="ozon", price=900, title="Мастер и Маргарита | Булгаков")
        results = [SourceResult(source="chitai_gorod", offers=[cg]), SourceResult(source="labirint", offers=[lab]),
                   SourceResult(source="ozon", offers=[oz])]
        kinds = {f.offer.source: f.kind for f in classify(book, results, {})}
        self.assertEqual(kinds, {"chitai_gorod": "shop", "labirint": "shop", "ozon": "dealer"})

    def test_exact_bookshop_in_stock_means_not_out_of_print(self):
        cg = Offer(source="chitai_gorod", price=799, in_stock=False)
        bv = Offer(source="bookvoed", price=319, by_isbn=True)
        self.assertFalse(out_of_print([SourceResult(source="chitai_gorod", offers=[cg]),
                                       SourceResult(source="bookvoed", offers=[bv])]))
        self.assertTrue(out_of_print([SourceResult(source="chitai_gorod", offers=[cg])]))


if __name__ == "__main__":
    unittest.main()
