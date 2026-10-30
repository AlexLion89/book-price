"""Extractors run inside a real Edge on synthetic pages shaped like the snapshots from 30.10.2026;
skipped when Playwright or Edge is missing."""
import unittest

from bookprice.sources import avito, extract
from bookprice.sources.shops import OZON_SKIP_RECOMMENDATIONS, USED_MARK, WB_CARDS

AVITO_PAGE = """
<div data-marker="item" data-item-id="4011">
  <a data-marker="item-title" href="https://www.avito.ru/kazan/knigi_i_zhurnaly/master_i_margarita_4011?slocation=1"
     title="Булгаков Мастер и Маргарита в Казани">Булгаков Мастер и Маргарита</a>
  <meta itemprop="price" content="450">
  <span data-marker="item-price">450 ₽</span>
  <div class="body-_6cab"><div class="bottomBlock-_6cab"><div class="ivaItemRedesign-_6cab">
    <p class="root-d45d">Азбука 2016, твёрдый переплёт, в том числе закладка</p></div></div></div>
  <div class="userInfoStep-_6cab"><p>Книжный клуб</p></div>
  <p data-marker="item-date">3 дня назад</p>
  <span>Доставка от 2 дней</span>
</div>
<div data-marker="item" data-item-id="4012">
  <a data-marker="item-title" href="https://www.avito.ru/sankt-peterburg/knigi_i_zhurnaly/sobachye_serdce_4012">Собачье сердце</a>
  <span data-marker="item-price">1 200 ₽</span>
  <div data-marker="item-location">Санкт-Петербург, Петроградская</div>
</div>
"""

SHOP_PAGE = """
<div class="grid">
  <div class="x1"><a href="https://www.ozon.ru/product/master-1001/?at=1"><img alt=""></a>
    <div><span>319 ₽</span><span>395 ₽</span></div>
    <a href="https://www.ozon.ru/product/master-1001/">Мастер и Маргарита | Булгаков М.</a></div>
  <div class="x1"><a href="https://www.ozon.ru/product/sumka-1002/">Сумка-шоппер</a><div>990 ₽</div></div>
  <div class="x1"><a href="https://www.ozon.ru/product/bez-ceny-1003/">Нет цены</a></div>
</div>
"""

OZON_PAGE = """
<div data-widget="tileGridDesktop">
  <div><a href="https://www.ozon.ru/product/ustal-1/">Устал рождаться и умирать | Янь Мо | Книга б/у</a><span>3 978 ₽</span></div>
</div>
<div data-widget="infiniteVirtualPaginator">
  <div><div>Возможно, вам понравится</div>
    <div data-widget="tileGridDesktop">
      <div><a href="https://www.ozon.ru/product/krossovki-2/">Кроссовки мужские зимние</a><span>4 174 ₽</span></div>
      <div><a href="https://www.ozon.ru/product/skotch-3/">Двухсторонний скотч</a><span>78 ₽</span></div>
    </div></div>
</div>
"""

WB_PAGE = """
<article class="product-card j-card-item" data-nm-id="996440118">
  <div class="catalogCard--KV2df">
    <a class="catalogCardLink--CgiYl" href="https://www.wildberries.ru/catalog/996440118/detail.aspx" aria-label="Мастер и Маргарита Азбука" data-testid="product-card-link"></a>
    <span data-testid="saleBadge">−6%</span>
    <div data-testid="product-card-price"><ins data-testid="product-card-current-price">439&nbsp;₽</ins><del>485&nbsp;₽</del></div>
    <span data-testid="productBrand">Азбука</span><span data-testid="productName">Мастер и Маргарита</span>
  </div>
</article>
"""


def edge():
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None
    try:
        pw = sync_playwright().start()
        browser = pw.chromium.launch(channel="msedge", headless=True)
        return pw, browser
    except Exception:
        return None


class FakeBrowser:
    def __init__(self, page):
        self.page = page

    def evaluate(self, script, arg=None):
        return self.page.evaluate(script, arg)


class ExtractTest(unittest.TestCase):
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

    def test_avito_items(self):
        b = self.load(AVITO_PAGE)
        offers = avito._offers(b.evaluate(avito.ITEMS))
        self.assertEqual([o.price for o in offers], [450, 1200])
        first, second = offers
        self.assertEqual(first.ext_id, "4011")
        self.assertEqual(first.url, "https://www.avito.ru/kazan/knigi_i_zhurnaly/master_i_margarita_4011")
        self.assertEqual(first.title, "Булгаков Мастер и Маргарита")
        self.assertEqual(first.place, "в Казани")
        self.assertEqual(first.desc, "Азбука 2016, твёрдый переплёт, в том числе закладка")
        self.assertEqual(first.age, "3 дня назад")
        self.assertEqual(first.note, "с доставкой")
        self.assertEqual(second.place, "Санкт-Петербург, Петроградская")

    def test_tiles(self):
        b = self.load(SHOP_PAGE)
        offers = extract.tiles(b, r"ozon\.ru/product/", "ozon")
        by_url = {o.url: o for o in offers}
        self.assertEqual(set(by_url), {"https://www.ozon.ru/product/master-1001/", "https://www.ozon.ru/product/sumka-1002/"})
        master = by_url["https://www.ozon.ru/product/master-1001/"]
        self.assertEqual(master.price, 319)
        self.assertEqual(master.title, "Мастер и Маргарита | Булгаков М.")

    def test_ozon_recommendations_are_cut(self):
        b = self.load(OZON_PAGE)
        self.assertEqual(b.evaluate(OZON_SKIP_RECOMMENDATIONS), 1)
        offers = extract.tiles(b, r"ozon\.ru/product/", "ozon")
        self.assertEqual([o.url for o in offers], ["https://www.ozon.ru/product/ustal-1/"])
        self.assertTrue(USED_MARK.search(offers[0].title))

    def test_wildberries_cards(self):
        cards = self.load(WB_PAGE).evaluate(WB_CARDS)
        self.assertEqual(cards, [{"url": "https://www.wildberries.ru/catalog/996440118/detail.aspx",
                                  "title": "Мастер и Маргарита Азбука", "text": "Азбука / Мастер и Маргарита",
                                  "price": 439, "id": "996440118"}])

    def test_rubles_written_as_word(self):
        page = """<div><a href="https://meshok.net/item/123456_Bulgakov">Булгаков. Мастер и Маргарита, 1989</a>
                  <span>Текущая ставка: 450 руб.</span></div>"""
        offers = extract.tiles(self.load(page), r"meshok\.net/item/\d+", "meshok", currency="₽|руб")
        self.assertEqual([(o.price, o.title) for o in offers], [(450, "Булгаков. Мастер и Маргарита, 1989")])

    def test_nothing_found(self):
        self.assertTrue(extract.nothing_found(self.load("<h1>Ничего не нашлось по запросу «978»</h1>")))
        self.assertFalse(extract.nothing_found(self.load(SHOP_PAGE)))


if __name__ == "__main__":
    unittest.main()
