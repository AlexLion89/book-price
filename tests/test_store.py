import tempfile
import unittest
from pathlib import Path

from bookprice.model import Book
from bookprice.search import evaluate
from bookprice.store import Store

MASTER = Book(title="Мастер и Маргарита", author="Михаил Булгаков", year=2012, isbn="9785389016866")


class StoreTest(unittest.TestCase):
    def setUp(self):
        self.dir = tempfile.TemporaryDirectory()
        self.store = Store(Path(self.dir.name) / "books.sqlite")

    def tearDown(self):
        self.store.db.close()
        self.dir.cleanup()

    def sell(self, book, price, when):
        book_id = self.store.add_book(book)
        self.store.update(book_id, status="sold", sold_price=price, sold_at=when)
        return book_id

    def test_sold_like_by_isbn_and_by_title(self):
        self.sell(MASTER, 400, "2026-09-01T10:00:00")
        self.sell(Book(title="Мастер и Маргарита", author="Михаил Булгаков"), 350, "2026-10-01T10:00:00")
        self.sell(Book(title="Собачье сердце", author="Михаил Булгаков"), 300, "2026-10-02T10:00:00")
        current = self.store.add_book(MASTER)
        self.assertEqual([s["sold_price"] for s in self.store.sold_like(current, MASTER)], [400])
        no_isbn = Book(title="Мастер и Маргарита", author="Михаил Булгаков")
        current = self.store.add_book(no_isbn)
        self.assertEqual([s["sold_price"] for s in self.store.sold_like(current, no_isbn)], [350])

    def test_own_sale_is_history_and_a_reason(self):
        sales = [{"sold_price": 800, "sold_at": "2026-09-01T10:00:00"}]
        v = evaluate(MASTER, [], [], "excellent", sales)
        self.assertEqual(v.scenario, "history_only")
        self.assertEqual(v.floor, 800)
        self.assertTrue(any("вы уже продавали такую: за 800 ₽ 2026-09-01" in r for r in v.reasons))


if __name__ == "__main__":
    unittest.main()
