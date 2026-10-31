import unittest

from bookprice.model import Book, Offer, SourceResult
from bookprice.search import classify, evaluate

BOOK = Book(title="Мастер и Маргарита", author="Михаил Булгаков", year=2012, isbn="9785389016866",
            publisher="Азбука, Азбука-Аттикус")
OLD = Book(title="Незнайка на Луне", author="Николай Носов", year=1986)


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

    def test_exact_isbn_shop_counts(self):
        found = classify(BOOK, [result("chitai_gorod", Offer("chitai_gorod", 319, title="Мастер и Маргарита", ext_id="c"))], {})
        self.assertEqual(found[0].verdict, "yes")
        self.assertTrue(found[0].counted)

    def test_marketplace_counts_only_same_edition(self):
        r = [result("ozon",
                    Offer("ozon", 238, title="Мастер и Маргарита", ext_id="pocket"),
                    Offer("ozon", 255, title="Мастер и Маргарита", text="255 ₽ Азбука Мастер и Маргарита", ext_id="azbuka"))]
        found = {f.offer.ext_id: f for f in classify(BOOK, r, {})}
        self.assertEqual(found["pocket"].verdict, "maybe")
        self.assertFalse(found["pocket"].counted)
        self.assertEqual(found["azbuka"].verdict, "yes")
        self.assertTrue(found["azbuka"].counted)

    def test_used_on_marketplace_is_a_dealer(self):
        r = [result("ozon", Offer("ozon", 3978, title="Мастер и Маргарита | Книга б/у", note="б/у", ext_id="u"))]
        found = classify(BOOK, r, {})
        self.assertEqual(found[0].kind, "dealer")
        self.assertFalse(found[0].counted)

    def test_reprints_do_not_cap_an_old_edition(self):
        r = [result("chitai_gorod", Offer("chitai_gorod", 960, title="Николай Носов — Незнайка на Луне", text="АСТ", ext_id="n"))]
        self.assertFalse(classify(OLD, r, {})[0].counted)

    def test_marketplace_resellers_when_out_of_print(self):
        r = [result("chitai_gorod", Offer("chitai_gorod", 209, title="Мастер и Маргарита", in_stock=False, ext_id="c")),
             result("ozon", Offer("ozon", 254, title="Булгаков Мастер и Маргарита Азбука 2012г", ext_id="o"))]
        found = {f.offer.source: f for f in classify(BOOK, r, {})}
        self.assertEqual(found["ozon"].kind, "dealer")
        v = evaluate(BOOK, list(found.values()), [], "excellent")
        self.assertNotEqual(v.scenario, "new_in_shops")

    def test_old_print_year_in_title_is_resale(self):
        r = [result("ozon", Offer("ozon", 254, title="Степной А. Сердце в броне Альфа-книга 2009г", ext_id="o"))]
        book = Book(title="Сердце в броне", author="Аркадий Степной", year=2009, isbn="9785992203721")
        self.assertEqual(classify(book, r, {})[0].kind, "dealer")

    def test_avito_year_from_description(self):
        r = [result("avito", Offer("avito", 300, title="Булгаков Мастер и Маргарита", desc="1994 г. Карелия", ext_id="a"))]
        found = classify(BOOK, r, {})
        self.assertEqual(found[0].verdict, "other")
        self.assertFalse(found[0].counted)

    def test_dealers_when_no_avito(self):
        r = [result("alib", *[Offer("alib", p, title="Булгаков М.А. Мастер и Маргарита.", text="М. Азбука. 2012г.", ext_id=str(p)) for p in (1000, 1200, 1500)])]
        v = evaluate(BOOK, classify(BOOK, r, {}), [], "excellent")
        self.assertEqual(v.scenario, "only_used")
        self.assertIn("букинист", v.reasons[0])
        self.assertEqual(v.start, 900)

    def test_dealer_without_year_needs_a_human(self):
        r = [result("alib", Offer("alib", 2000, title="Булгаков М. Мастер и Маргарита.", text="Самиздат", ext_id="s"))]
        self.assertFalse(classify(BOOK, r, {})[0].counted)

    def test_manual_price(self):
        v = evaluate(BOOK, [], [Offer("ozon", 500)], "excellent")
        self.assertEqual(v.scenario, "new_in_shops")
        self.assertEqual(v.start, 400)


if __name__ == "__main__":
    unittest.main()
