import unittest

from bookprice import copymarks
from bookprice.listing import ad_text
from bookprice.model import Book, Offer, SourceResult
from bookprice.search import classify, evaluate

BOOK = Book(title="Сердце в броне", author="Аркадий Степной", year=2009, isbn="9785992203721")
RESULTS = [SourceResult(source="avito", offers=[Offer("avito", p, title="Степной Сердце в броне", ext_id=str(p))
                                               for p in (300, 320, 340, 360, 380)])]


class CopyMarksTest(unittest.TestCase):
    def test_factor_and_limits(self):
        self.assertAlmostEqual(copymarks.factor(["autograph", "first"]), 1.45)
        self.assertAlmostEqual(copymarks.factor(["library", "inscription"]), 0.75)
        self.assertEqual(copymarks.factor(["autograph", "first", "case", "jacket", "nonsense"]), 1.6)

    def test_marks_move_start_and_floor(self):
        plain = evaluate(BOOK, classify(BOOK, RESULTS, {}), [], "excellent")
        signed = evaluate(BOOK, classify(BOOK, RESULTS, {}), [], "excellent", copy_marks=["autograph"])
        self.assertEqual((plain.start, plain.floor), (340, 290))
        self.assertEqual((signed.start, signed.floor), (440, 380))
        self.assertIn("с автографом автора +30 %", signed.reasons[-1])

    def test_ad_text(self):
        text = ad_text(BOOK, "good", ["autograph", "library"])
        self.assertIn("Особенности: с автографом автора.", text)
        self.assertIn("Честно: есть библиотечные штампы.", text)


if __name__ == "__main__":
    unittest.main()
