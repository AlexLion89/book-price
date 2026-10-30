"""Extractors run inside a real Edge on synthetic pages; skipped when Playwright or Edge is missing."""
import unittest

from bookprice.sources import avito, extract

AVITO_PAGE = """
<div data-marker="item" data-item-id="4011">
  <a data-marker="item-title" href="https://www.avito.ru/sankt-peterburg/knigi_i_zhurnaly/master_i_margarita_4011?slocation=1"
     title="Булгаков Мастер и Маргарита">Булгаков Мастер и Маргарита</a>
  <meta itemprop="price" content="450">
  <span data-marker="item-price">450 ₽</span>
  <meta itemprop="description" content="Азбука 2016, твёрдый переплёт">
  <div data-marker="item-address">Петроградская</div>
  <p data-marker="item-date">3 дня назад</p>
  <span>Доставка</span>
</div>
<div data-marker="item" data-item-id="4012">
  <a data-marker="item-title" href="https://www.avito.ru/sankt-peterburg/knigi_i_zhurnaly/sobachye_serdce_4012">Собачье сердце</a>
  <span data-marker="item-price">1 200 ₽</span>
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
        offers = avito._offers(b.evaluate(avito.ITEMS), "Санкт-Петербург")
        self.assertEqual([o.price for o in offers], [450, 1200])
        first = offers[0]
        self.assertEqual(first.ext_id, "4011")
        self.assertEqual(first.url, "https://www.avito.ru/sankt-peterburg/knigi_i_zhurnaly/master_i_margarita_4011")
        self.assertEqual(first.text, "Азбука 2016, твёрдый переплёт")
        self.assertEqual(first.place, "Петроградская")
        self.assertEqual(first.age, "3 дня назад")
        self.assertEqual(first.note, "с доставкой")
        self.assertEqual(offers[1].place, "Санкт-Петербург")

    def test_tiles(self):
        b = self.load(SHOP_PAGE)
        offers = extract.tiles(b, r"ozon\.ru/product/", "ozon")
        by_url = {o.url: o for o in offers}
        self.assertEqual(set(by_url), {"https://www.ozon.ru/product/master-1001/", "https://www.ozon.ru/product/sumka-1002/"})
        master = by_url["https://www.ozon.ru/product/master-1001/"]
        self.assertEqual(master.price, 319)
        self.assertEqual(master.title, "Мастер и Маргарита | Булгаков М.")

    def test_nothing_found(self):
        self.assertTrue(extract.nothing_found(self.load("<h1>По вашему запросу ничего не нашлось</h1>")))
        self.assertFalse(extract.nothing_found(self.load(SHOP_PAGE)))


if __name__ == "__main__":
    unittest.main()
