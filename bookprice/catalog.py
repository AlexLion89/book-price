from __future__ import annotations

import logging
from typing import List, Optional

from . import isbn as isbn_mod
from .model import Book
from .net import Http
from .sources import chitai_gorod, fantlab

log = logging.getLogger(__name__)


def merge(primary: Optional[Book], extra: Optional[Book]) -> Optional[Book]:
    if not primary:
        return extra
    if not extra:
        return primary
    for name in ("title", "author", "publisher", "cover_url", "binding"):
        if not getattr(primary, name):
            setattr(primary, name, getattr(extra, name))
    primary.year = primary.year or extra.year
    if extra.year and extra.year != primary.year and extra.year not in primary.reprint_years:
        primary.reprint_years = sorted(primary.reprint_years + [extra.year])
    return primary


def identify(http: Http, raw_isbn: str) -> Optional[Book]:
    code = isbn_mod.normalize(raw_isbn)
    if not code:
        raise ValueError("это не ISBN: проверьте 13 цифр под штрихкодом")
    found = []
    for name, lookup in (("FantLab", fantlab.by_isbn), ("Читай-город", chitai_gorod.lookup)):
        try:
            found.append(lookup(http, code))
        except Exception:
            log.exception("%s: ошибка при поиске ISBN %s", name, code)
            found.append(None)
    book = merge(*found)
    if book:
        book.isbn = code
    return book


def find(http: Http, title: str, author: str = "") -> List[Book]:
    query = f"{title} {author}".strip()
    try:
        return fantlab.by_title(http, query)
    except Exception:
        log.exception("FantLab: ошибка при поиске «%s»", query)
        return []
