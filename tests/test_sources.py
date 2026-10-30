import unittest

from bookprice.catalog import merge
from bookprice.model import Book
from bookprice.sources import alib, chitai_gorod, fantlab

ALIB_PAGE = """<h3><a href="//www.alib.ru/t19poem.phtml">Поэзия</a></h3>
<p><b>Булгаков М.А. Мастер и Маргарита. </b>Художник Максимук Антонина. М РООССА. 2010г. 264 с.,илл.
Твердый переплет. <br>(До заказа внимательно прочтите условия продажи продавца
<a href="https://www.alib.ru/bs.php4?bs=Drok-u">BS - Drok-u</a>, Санкт-Петербург.) Цена: 5 000 руб.
<a href="https://www.alib.ru/5_bulgakov_master_w1t123abc.html"><b>Купить</b></a> <br>Аннотация про Булгакова и 1966 год.
<p><b>Пушкин А.С. Граф Нулин. </b>Псков. 2004г. (До заказа ... <a href="x">BS - P</a>, Москва.) Цена: 858 руб.
<a href="https://www.alib.ru/5_pushkin_w1t999.html"><b>Купить</b></a>
"""

CG_PRODUCT = {
    "id": 2335267, "title": "Мастер и Маргарита", "price": 319, "status": "preOrder", "isBook": True,
    "authors": [{"firstName": "Михаил", "lastName": "Булгаков"}], "yearPublishing": 2026,
    "publisher": {"title": "Азбука"}, "cover": "Твердый переплёт", "url": "product/master-i-margarita-2335267",
}


class AlibTest(unittest.TestCase):
    def test_parse(self):
        offers = alib.parse(ALIB_PAGE)
        self.assertEqual(len(offers), 2)
        first = offers[0]
        self.assertEqual(first.price, 5000)
        self.assertEqual(first.title, "Булгаков М.А. Мастер и Маргарита.")
        self.assertIn("2010г", first.text)
        self.assertNotIn("Аннотация", first.text)
        self.assertEqual(first.place, "Санкт-Петербург")
        self.assertTrue(first.url.endswith("w1t123abc.html"))

    def test_query_drops_stop_words(self):
        self.assertEqual(alib.query(Book(title="Мастер и Маргарита", author="Михаил Булгаков")), "булгаков мастер маргарита")


class ChitaiGorodTest(unittest.TestCase):
    def test_offer(self):
        o = chitai_gorod._offer(CG_PRODUCT)
        self.assertEqual(o.price, 319)
        self.assertTrue(o.in_stock)
        self.assertEqual(o.note, "предзаказ")
        self.assertEqual(o.title, "Михаил Булгаков — Мастер и Маргарита")
        self.assertEqual(o.url, "https://www.chitai-gorod.ru/product/master-i-margarita-2335267")

    def test_subscribe_is_not_in_stock(self):
        o = chitai_gorod._offer(dict(CG_PRODUCT, status="canSubscribe"))
        self.assertFalse(o.in_stock)


class FantlabTest(unittest.TestCase):
    def test_reprint_years(self):
        notes = "[u]Доп.тиражи:[/u]\r\n2015 г. - 12000 экз. (подписано в печать 08.12.2014)\r\n2016 г. - 10 000 экз."
        self.assertEqual(fantlab.reprint_years(notes), [2015, 2016])

    def test_strip_markup(self):
        self.assertEqual(fantlab.strip_markup("[autor=186]Михаил Булгаков[/autor]"), "Михаил Булгаков")


class MergeTest(unittest.TestCase):
    def test_shop_year_becomes_reprint(self):
        fl = Book(title="Мастер и Маргарита", author="Михаил Булгаков", year=2012, reprint_years=[2015])
        cg = Book(title="Мастер и Маргарита", year=2026, cover_url="https://img/x.jpg")
        book = merge(fl, cg)
        self.assertEqual(book.year, 2012)
        self.assertEqual(book.reprint_years, [2015, 2026])
        self.assertEqual(book.cover_url, "https://img/x.jpg")

    def test_only_shop(self):
        cg = Book(title="Х", year=2020)
        self.assertIs(merge(None, cg), cg)


if __name__ == "__main__":
    unittest.main()
