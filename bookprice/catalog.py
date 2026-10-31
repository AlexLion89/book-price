from __future__ import annotations

import logging
import re
from datetime import date
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
    primary.facts = {**extra.facts, **primary.facts}
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


def enrich(http: Http, book: Book) -> Book:
    """Title search on FantLab returns editions without cover and binding: fetch the full card of the chosen one."""
    m = re.search(r"fantlab\.ru/edition(\d+)", book.source_url or "")
    if not m or book.cover_url:
        return book
    try:
        full = fantlab.edition(http, int(m.group(1)), book.isbn)
    except Exception:
        log.exception("FantLab: карточка издания %s", m.group(1))
        return book
    return merge(full, book)


def facts(http: Http, book: Book) -> dict:
    """Facts for a book added before they were collected (or by hand): from its ISBN or FantLab edition."""
    found = None
    try:
        if book.isbn:
            found = identify(http, book.isbn)
        elif re.search(r"fantlab\.ru/edition(\d+)", book.source_url or ""):
            found = enrich(http, Book(title=book.title, source_url=book.source_url))
    except Exception:
        log.exception("сведения о книге «%s»", book.title)
    result = dict(found.facts) if found else {}
    result["checked"] = date.today().isoformat()
    return result


def find(http: Http, title: str, author: str = "") -> List[Book]:
    query = f"{title} {author}".strip()
    try:
        return fantlab.by_title(http, query)
    except Exception:
        log.exception("FantLab: ошибка при поиске «%s»", query)
        return []
