import unittest
from datetime import datetime

from bookprice.listing import ad_text, binding_text, next_step
from bookprice.model import Book


class NextStepTest(unittest.TestCase):
    def test_too_early(self):
        self.assertIsNone(next_step(1500, "2026-10-28T10:00:00", 800, today=datetime(2026, 10, 30)))

    def test_week_passed(self):
        self.assertEqual(next_step(1500, "2026-10-20T10:00:00", 800, today=datetime(2026, 10, 30)), {"days": 10, "price": 1350})

    def test_never_below_floor(self):
        self.assertEqual(next_step(850, "2026-10-01T10:00:00", 800, today=datetime(2026, 10, 30))["price"], 800)

    def test_at_floor_nothing_to_do(self):
        self.assertIsNone(next_step(800, "2026-10-01T10:00:00", 800, today=datetime(2026, 10, 30)))


class AdTextTest(unittest.TestCase):
    def test_full(self):
        book = Book(title="Мастер и Маргарита", author="Михаил Булгаков", year=2012, publisher="Азбука",
                    binding="твёрдая", pages=480, isbn="9785389016866")
        text = ad_text(book, "good")
        self.assertIn("Азбука, 2012 г., твёрдый переплёт, 480 стр.", text)
        self.assertIn("Состояние: хорошее.", text)

    def test_binding(self):
        self.assertEqual(binding_text("Мягкая"), "мягкая обложка")
        self.assertEqual(binding_text("Твердый переплёт"), "твердый переплёт")


if __name__ == "__main__":
    unittest.main()
