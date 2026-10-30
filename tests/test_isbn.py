import unittest

from bookprice.isbn import normalize


class IsbnTest(unittest.TestCase):
    def test_isbn13_with_hyphens(self):
        self.assertEqual(normalize("978-5-389-01686-6"), "9785389016866")

    def test_isbn10_to_13(self):
        self.assertEqual(normalize("5-389-01686-6"), "9785389016866")

    def test_isbn10_with_x(self):
        self.assertEqual(normalize("0-8044-2957-X"), "9780804429573")

    def test_bad_checksum(self):
        self.assertIsNone(normalize("9785389016867"))

    def test_not_a_book_barcode(self):
        self.assertIsNone(normalize("4600000000003"))

    def test_garbage(self):
        self.assertIsNone(normalize("мастер"))


if __name__ == "__main__":
    unittest.main()
