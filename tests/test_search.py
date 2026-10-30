import unittest

from bookprice.model import Book, Offer, SourceResult
from bookprice.search import classify, evaluate

BOOK = Book(title="Мастер и Маргарита", author="Михаил Булгаков", year=2012, isbn="9785389016866")


def result(source, *offers):
    return SourceResult(source=source, offers=list(offers))


class SearchTest(unittest.TestCase):
    def test_marks_override_filter(self):
        r = [result("avito",
                    Offer("avito", 400, title="Булгаков Мастер и Маргарита", ext_id="1"),
                    Offer("avito", 300, title="Булгаков Мастер и Маргарита", ext_id="2"))]
        found = classify(BOOK, r, {("avito", "2"): False})
        self.assertEqual([f.counted for f in found], [True, False])
        self.assertTrue(found[1].marked)

    def test_shop_by_isbn_needs_no_author(self):
        found = classify(BOOK, [result("ozon", Offer("ozon", 350, title="Мастер и Маргарита", ext_id="u"))], {})
        self.assertTrue(found[0].counted)

    def test_dealers_when_no_avito(self):
        r = [result("alib", *[Offer("alib", p, title="Булгаков М.А. Мастер и Маргарита.", ext_id=str(p)) for p in (1000, 1200, 1500)])]
        v = evaluate(BOOK, classify(BOOK, r, {}), [], "excellent")
        self.assertEqual(v.scenario, "only_used")
        self.assertIn("букинист", v.reasons[0])
        self.assertEqual(v.start, 800)

    def test_manual_price(self):
        v = evaluate(BOOK, [], [Offer("ozon", 500)], "excellent")
        self.assertEqual(v.scenario, "new_in_shops")
        self.assertEqual(v.start, 300)


if __name__ == "__main__":
    unittest.main()
