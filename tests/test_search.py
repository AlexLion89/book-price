import unittest

from bookprice.model import Book, Offer, SourceResult
from bookprice.search import classify, evaluate, evaluate_with_dossier

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

    def test_premium_raises_start_not_floor(self):
        book = Book(title="Сердце в броне", author="Аркадий Степной", year=2009, isbn="9785992203721",
                    facts={"work_last_year": 2010, "work_rating": 7.96, "work_voters": 636})
        r = [result("chitai_gorod", Offer("chitai_gorod", 209, title="Сердце в броне", in_stock=False, ext_id="c")),
             result("avito", Offer("avito", 170, title="Степной Сердце в броне", ext_id="1"),
                    Offer("avito", 279, title="Степной Сердце в броне", ext_id="2"))]
        v, dossier = evaluate_with_dossier(book, classify(book, r, {}), [], "excellent")
        self.assertAlmostEqual(dossier.premium, 0.25)
        self.assertEqual((v.start, v.floor), (260, 190))
        self.assertFalse(v.as_lot)

    def test_manual_price(self):
        v = evaluate(BOOK, [], [Offer("ozon", 500)], "excellent")
        self.assertEqual(v.scenario, "new_in_shops")
        self.assertEqual(v.start, 400)


MO_YAN = Book(title="Устал рождаться и умирать", author="Мо Янь", year=2014, isbn="9785367032819", publisher="Амфора")
AVITO_MO_YAN = result("avito", *[Offer("avito", p, title="Мо Янь Устал рождаться и умирать", ext_id=str(p))
                                 for p in (1200, 1500, 1700, 2000)])


class ReprintTest(unittest.TestCase):
    def reasons(self, *results):
        return evaluate(MO_YAN, classify(MO_YAN, [*results, AVITO_MO_YAN], {}), [], "excellent").reasons

    def test_reprint_sold_new_is_mentioned_but_does_not_count(self):
        reasons = self.reasons(
            result("chitai_gorod", Offer("chitai_gorod", 799, title="Мо Янь — Устал рождаться и умирать", in_stock=False)),
            result("moscowbooks", Offer("moscowbooks", 2176, title="Устал рождаться и умирать", text="Мо Янь"),
                   Offer("moscowbooks", 2023, title="Устал рождаться и умирать", text="Мо Янь"),
                   Offer("moscowbooks", 1309, title="Нежелательные: как наука решает", text="Иванов")))
        self.assertIn("в магазинах есть другие издания — от 2023 ₽ (Московский дом книги)", " ".join(reasons))
        self.assertTrue(reasons[0].startswith("в магазинах нет в продаже"))

    def test_no_note_when_the_edition_itself_is_in_a_shop(self):
        reasons = self.reasons(
            result("chitai_gorod", Offer("chitai_gorod", 2500, title="Мо Янь — Устал рождаться и умирать")),
            result("moscowbooks", Offer("moscowbooks", 2023, title="Устал рождаться и умирать", text="Мо Янь")))
        self.assertFalse(any("другие издания" in r for r in reasons))

    def test_another_volume_is_not_a_reprint(self):
        reasons = self.reasons(
            result("labirint", Offer("labirint", 900, title="Устал рождаться и умирать. Часть 2", text="Мо Янь")))
        self.assertFalse(any("другие издания" in r for r in reasons))


if __name__ == "__main__":
    unittest.main()
