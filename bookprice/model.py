from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import List, Optional


@dataclass
class Book:
    title: str
    author: str = ""
    year: Optional[int] = None
    isbn: str = ""
    publisher: str = ""
    cover_url: str = ""
    binding: str = ""
    pages: Optional[int] = None
    # Same ISBN is reprinted for years; a listing saying "2016" can still be this edition.
    reprint_years: List[int] = field(default_factory=list)
    source: str = ""
    source_url: str = ""

    def years(self) -> List[int]:
        return sorted({y for y in [self.year, *self.reprint_years] if y})

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Offer:
    source: str
    price: float
    url: str = ""
    title: str = ""
    text: str = ""
    in_stock: bool = True
    ext_id: str = ""
    place: str = ""
    age: str = ""
    note: str = ""

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class SourceResult:
    source: str
    offers: List[Offer] = field(default_factory=list)
    search_url: str = ""
    error: str = ""
    snapshot: str = ""

    @property
    def ok(self) -> bool:
        return not self.error

    def to_dict(self) -> dict:
        d = asdict(self)
        d["ok"] = self.ok
        return d
