import unittest

from bookprice.matching import match
from bookprice.model import Book

MASTER = Book(title="Мастер и Маргарита", author="Михаил Булгаков", year=2019)


class MatchTest(unittest.TestCase):
    def verdict(self, book, title, text=""):
        return match(book, title, text).verdict

    def test_author_title_and_year(self):
        self.assertEqual(self.verdict(MASTER, "Булгаков. Мастер и Маргарита", "Издательство АСТ, 2019 год"), "yes")

    def test_declension_and_yo(self):
        book = Book(title="Ёлка и её друзья", author="Иванов")
        self.assertEqual(self.verdict(book, "книга Ивановой Елки и ее друзей"), "maybe")

    def test_no_year_in_listing(self):
        self.assertEqual(self.verdict(MASTER, "Мастер и Маргарита Булгаков книга"), "maybe")

    def test_other_year_is_other_edition(self):
        result = match(MASTER, "Мастер и Маргарита Булгаков", "1989 г., Худ. лит.")
        self.assertEqual(result.verdict, "other")
        self.assertIn("другой год", result.reason)

    def test_year_glued_to_letter(self):
        self.assertEqual(self.verdict(MASTER, "Булгаков М.А. Мастер и Маргарита.", "М. АСТ. 2019г. 480с."), "yes")

    def test_first_name_alone_is_not_author(self):
        self.assertEqual(self.verdict(MASTER, "Пушкин. Мастер и Маргарита", "музей Михайловское"), "no")

    def test_alib_author_format(self):
        self.assertEqual(self.verdict(MASTER, "Булгаков М.А. Мастер и Маргарита."), "maybe")

    def test_coauthors(self):
        book = Book(title="Двенадцать стульев", author="Илья Ильф, Евгений Петров")
        self.assertEqual(self.verdict(book, "Ильф и Петров. Двенадцать стульев"), "maybe")

    def test_set_is_rejected(self):
        self.assertEqual(self.verdict(MASTER, "Булгаков собрание сочинений 5 томов, Мастер и Маргарита"), "no")

    def test_format_word_inside_title_is_allowed(self):
        book = Book(title="Набор слов", author="Петров")
        self.assertEqual(self.verdict(book, "Петров Набор слов"), "maybe")

    def test_merch_is_rejected(self):
        self.assertEqual(self.verdict(MASTER, "Закладка Мастер и Маргарита Булгаков"), "no")

    def test_missing_author(self):
        self.assertEqual(self.verdict(MASTER, "Мастер и Маргарита, подарочное издание"), "no")

    def test_missing_title_words(self):
        self.assertEqual(self.verdict(MASTER, "Булгаков Собачье сердце"), "no")

    def test_number_title_is_not_a_year(self):
        book = Book(title="1984", author="Джордж Оруэлл", year=2021)
        self.assertEqual(self.verdict(book, "Оруэлл 1984 мягкая обложка"), "maybe")

    def test_reprint_year_is_same_edition(self):
        book = Book(title="Мастер и Маргарита", author="Михаил Булгаков", year=2012, reprint_years=[2015, 2016])
        self.assertEqual(self.verdict(book, "Булгаков Мастер и Маргарита", "Азбука, 2016"), "yes")

    def test_description_is_not_checked_for_format_words(self):
        result = match(MASTER, "Булгаков Мастер и Маргарита", desc="в том числе закладка, 2019 год")
        self.assertEqual(result.verdict, "yes")

    def test_publisher_match(self):
        book = Book(title="Мастер и Маргарита", author="Михаил Булгаков", publisher="Азбука, Азбука-Аттикус")
        self.assertEqual(match(book, "Булгаков Мастер и Маргарита", desc="изд. Азбука").verdict, "yes")

    def test_marketplace_title_without_author(self):
        self.assertEqual(match(MASTER, "Мастер и Маргарита", need_author=False).verdict, "maybe")
        self.assertEqual(match(MASTER, "Мастер и Маргарита").verdict, "no")

    def test_word_boundary_for_format(self):
        self.assertEqual(self.verdict(MASTER, "Мастер и Маргарита Булгаков, Томск, самовывоз"), "maybe")


if __name__ == "__main__":
    unittest.main()
