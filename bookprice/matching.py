from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List

from .model import Book

STOP_WORDS = {
    "и", "в", "во", "на", "с", "со", "о", "об", "по", "за", "из", "к", "у", "а", "но", "не",
    "или", "the", "a", "an", "of", "and",
}
# Listings with these words are sets, merch or other formats, unless the book title itself has them.
FOREIGN_FORMAT = [
    "комплект", "собрание сочинений", "собр соч", "том", "тома", "томов", "лот", "набор",
    "аудиокнига", "mp3", "диск", "журнал", "открытка", "открытки", "плакат", "постер",
    "закладка", "футболка", "пазл", "раскраска", "блокнот", "ежедневник",
]
YEAR = re.compile(r"(?<!\d)(1[89]\d\d|20[0-4]\d)(?!\d)")
FIRST_NAMES = set("""
александр алексей анатолий андрей антон аркадий борис вадим валентин валерий василий виктор
виталий владимир владислав вячеслав геннадий георгий глеб григорий даниил денис дмитрий евгений
егор иван игорь илья кирилл константин лев леонид максим марк михаил никита николай олег павел
петр роман руслан сергей станислав степан тимур федор эдуард юрий яков
александра алла анастасия анна валентина вера виктория галина дарья евгения екатерина елена
елизавета жанна зинаида инна ирина карина кристина лариса лидия любовь людмила маргарита марина
мария надежда наталья нина ольга полина светлана софья тамара татьяна ульяна юлия
агата артур генри джеймс джек джоан джозеф джон джордж дэн дэниел кэтлин льюис нил рэй стивен
терри уильям фрэнсис чарльз эрих эрнест
""".split())

# Verdicts: "yes" — same edition; "maybe" — same book, edition not stated;
# "other" — same book, another year; "no" — something else.
COUNTED_BY_DEFAULT = {"yes", "maybe"}


@dataclass
class MatchResult:
    verdict: str
    reason: str

    @property
    def counted(self) -> bool:
        return self.verdict in COUNTED_BY_DEFAULT


def normalize(text: str) -> str:
    text = text.lower().replace("ё", "е")
    text = re.sub(r"[^0-9a-zа-я]+", " ", text)
    return " ".join(text.split())


def words(text: str) -> List[str]:
    return normalize(text).split()


def common_prefix(a: str, b: str) -> int:
    n = 0
    for x, y in zip(a, b):
        if x != y:
            break
        n += 1
    return n


def found_in(word: str, listing_words: List[str], strict: bool = False) -> bool:
    if len(word) <= 3 or word.isdigit():
        return word in listing_words
    need = max(4 if strict else 3, min(len(word) - 2, 7))
    return any(common_prefix(word, w) >= need for w in listing_words)


def surnames(author: str) -> List[str]:
    """Word order varies ("Михаил Булгаков", "Булгаков М.А."), so drop initials and common first names
    instead of guessing the surname position; a bare first name would match "Михайловское"."""
    result = []
    for one in author.split(","):
        candidates = [w for w in words(one) if len(w) >= 3]
        rest = [w for w in candidates if w not in FIRST_NAMES]
        result.extend(rest or candidates)
    return result


def significant(text: str) -> List[str]:
    return [w for w in words(text) if w not in STOP_WORDS and (len(w) >= 3 or w.isdigit())]


def has_phrase(text_norm: str, phrase: str) -> bool:
    return re.search(r"\b" + re.escape(phrase) + r"\b", text_norm) is not None


def match(book: Book, listing_title: str, listing_text: str = "", by_isbn: bool = False) -> MatchResult:
    """by_isbn: the shop was searched by ISBN, so only weed out recommendations and merch."""
    full = normalize(listing_title + " " + listing_text)
    full_words = full.split()
    title_norm = normalize(book.title)

    for phrase in FOREIGN_FORMAT:
        if has_phrase(full, phrase) and not has_phrase(title_norm, phrase):
            return MatchResult("no", f"похоже на другое: «{phrase}»")

    author_words = surnames(book.author)
    if not by_isbn and author_words and not any(found_in(w, full_words, strict=True) for w in author_words):
        return MatchResult("no", "нет автора")

    title_words = significant(book.title)
    if title_words:
        found = sum(1 for w in title_words if found_in(w, full_words))
        need = max(1, math.ceil(len(title_words) * 0.6))
        if found < need:
            return MatchResult("no", f"из названия нашлось {found} слов из {len(title_words)}")

    if by_isbn:
        return MatchResult("yes", "найдено по ISBN")

    known = set(book.years())
    if known:
        years = {int(y) for y in YEAR.findall(full)} - {int(y) for y in YEAR.findall(title_norm)}
        if known & years:
            return MatchResult("yes", "совпали автор, название и год")
        if years:
            return MatchResult("other", "другой год — скорее всего, другое издание")
    return MatchResult("maybe", "совпали автор и название, издание не указано")
