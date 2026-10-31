import unittest
from datetime import date

from bookprice.model import Book
from bookprice.value import assess

TODAY = date(2026, 10, 31)
HEART = Book(title="Сердце в броне", author="Аркадий Степной", year=2009, isbn="9785992203721", binding="твёрдая",
             facts={"copies": 15000, "series": ["Магия фэнтези"], "cover": "твёрдая", "format": "84x108/32",
                    "work_rating": 7.96, "work_voters": 636, "work_editions": 2, "work_last_year": 2010,
                    "work_planned": False})


class ValueTest(unittest.TestCase):
    def test_long_out_of_print_few_listings_known_book(self):
        d = assess(HEART, used_count=2, new_in_stock=False, today=TODAY)
        self.assertAlmostEqual(d.premium, 0.25)
        self.assertEqual([f.label for f in d.factors if f.premium], ["Давно не переиздавалась", "Мало предложений", "Спрос"])
        self.assertIn(("Тираж", "15 000 экз."), d.facts)

    def test_no_premium_when_new_copy_in_shop(self):
        d = assess(HEART, used_count=2, new_in_stock=True, today=TODAY)
        self.assertEqual(d.premium, 0)

    def test_fresh_reprint_or_plans_cancel_rarity(self):
        fresh = Book(title="Мастер и Маргарита", facts={"work_last_year": 2025, "work_rating": 9.07, "work_voters": 11903})
        d = assess(fresh, used_count=30, new_in_stock=False, today=TODAY)
        self.assertEqual([f.label for f in d.factors][:1], ["Текст переиздают"])
        self.assertAlmostEqual(d.premium, 0.10)
        planned = Book(title="X", facts={"work_last_year": 2001, "work_planned": True})
        self.assertEqual(assess(planned, 10, False, TODAY).premium, 0)

    def test_collectible_signs(self):
        gift = Book(title="Мастер и Маргарита", year=2005,
                    facts={"copies": 2000, "cover": "твёрдая + суперобложка", "format": "70x100/16",
                           "description": "Подарочное издание с цветными иллюстрациями", "work_last_year": 2025})
        d = assess(gift, used_count=10, new_in_stock=False, today=TODAY)
        self.assertEqual(len(d.collectible), 5)
        self.assertAlmostEqual(d.premium, 0.30)

    def test_edition_year_alone_needs_sold_out(self):
        bare = Book(title="Мастер и Маргарита", year=2012)
        self.assertEqual(assess(bare, 10, False, today=TODAY).premium, 0)
        self.assertAlmostEqual(assess(bare, 10, False, sold_out=True, today=TODAY).premium, 0.10)

    def test_chapter_drawings_are_not_collectible(self):
        mass = Book(title="Сердце в броне", facts={"description": "Иллюстрация на обложке и внутренние иллюстрации"})
        self.assertEqual(assess(mass, 10, False, today=TODAY).collectible, [])

    def test_cap(self):
        rare = Book(title="X", year=1915, facts={"copies": 1000, "cover": "суперобложка", "work_last_year": 1915,
                                                 "work_rating": 9.0, "work_voters": 5000})
        self.assertEqual(assess(rare, used_count=1, new_in_stock=False, today=TODAY).premium, 0.5)


if __name__ == "__main__":
    unittest.main()
