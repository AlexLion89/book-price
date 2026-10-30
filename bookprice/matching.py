from __future__ import annotations

import math
import re
from dataclasses import dataclass
from typing import List, Optional

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
YEAR = re.compile(r"\b(1[89]\d\d|20[0-4]\d)\b")


@dataclass
class Book:
    title: str
    author: str = ""
    year: Optional[int] = None


@dataclass
class MatchResult:
    verdict: str
    reason: str


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


def found_in(word: str, listing_words: List[str]) -> bool:
    if len(word) <= 3 or word.isdigit():
        return word in listing_words
    need = max(3, min(len(word) - 2, 7))
    return any(common_prefix(word, w) >= need for w in listing_words)


def significant(text: str) -> List[str]:
    return [w for w in words(text) if w not in STOP_WORDS and (len(w) >= 3 or w.isdigit())]


def has_phrase(text_norm: str, phrase: str) -> bool:
    return re.search(r"\b" + re.escape(phrase) + r"\b", text_norm) is not None


def match(book: Book, listing_title: str, listing_text: str = "") -> MatchResult:
    full = normalize(listing_title + " " + listing_text)
    full_words = full.split()
    title_norm = normalize(book.title)

    for phrase in FOREIGN_FORMAT:
        if has_phrase(full, phrase) and not has_phrase(title_norm, phrase):
            return MatchResult("no", f"похоже на другое: «{phrase}»")

    author_words = [w for w in words(book.author) if len(w) >= 4]
    if author_words and not any(found_in(w, full_words) for w in author_words):
        return MatchResult("no", "нет автора")

    title_words = significant(book.title)
    if title_words:
        found = sum(1 for w in title_words if found_in(w, full_words))
        need = max(1, math.ceil(len(title_words) * 0.6))
        if found < need:
            return MatchResult("no", f"из названия нашлось {found} слов из {len(title_words)}")

    if book.year:
        years = {int(y) for y in YEAR.findall(full)} - {int(y) for y in YEAR.findall(title_norm)}
        if book.year in years:
            return MatchResult("yes", "совпали автор, название и год")
        if years:
            return MatchResult("maybe", "другой год — возможно, другое издание")
    return MatchResult("maybe", "совпали автор и название, издание не указано")
