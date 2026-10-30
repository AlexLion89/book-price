from __future__ import annotations

import urllib.parse
from typing import List, Optional

from ..net import Http
from ..model import Book, Offer, SourceResult

NAME = "chitai_gorod"
LABEL = "Читай-город"
SITE = "https://www.chitai-gorod.ru"
API = "https://web-gate.chitai-gorod.ru/api/v2/search/product"
IMAGES = "https://content.img-gorod.ru"
IN_STOCK = {"canBuy": "", "offline": "только в магазинах", "preOrder": "предзаказ"}


def search_url(phrase: str) -> str:
    return f"{SITE}/search?{urllib.parse.urlencode({'phrase': phrase})}"


def _token(http: Http) -> str:
    token = http.cookie("access-token")
    if not token:
        http.get(SITE + "/")
        token = http.cookie("access-token")
    if not token:
        raise RuntimeError("сайт не выдал токен сессии")
    return token


def _products(http: Http, phrase: str, per_page: int = 30) -> List[dict]:
    d = http.json(API, {
        "phrase": phrase,
        "customerCityId": 2,
        "products[page]": 1,
        "products[per-page]": per_page,
    }, {"Authorization": _token(http)})
    return [x["attributes"] for x in d.get("included") or [] if x.get("type") == "product"]


def _author(a: dict) -> str:
    return ", ".join(
        " ".join(p for p in [x.get("firstName"), x.get("lastName")] if p) for x in a.get("authors") or []
    )


def _offer(a: dict) -> Offer:
    status = a.get("status") or ""
    year = a.get("yearPublishing") or ""
    publisher = (a.get("publisher") or {}).get("title") or ""
    return Offer(
        source=NAME,
        price=float(a.get("price") or 0),
        url=f"{SITE}/{a.get('url', '')}",
        title=f"{_author(a)} — {a.get('title', '')}",
        text=", ".join(str(x) for x in [publisher, year, a.get("cover") or ""] if x),
        in_stock=status in IN_STOCK,
        ext_id=str(a.get("id") or ""),
        note=IN_STOCK.get(status, "нет в продаже"),
    )


def search(http: Http, book: Book) -> SourceResult:
    phrase = book.isbn or f"{book.title} {book.author}".strip()
    result = SourceResult(source=NAME, search_url=search_url(phrase))
    try:
        products = [a for a in _products(http, phrase) if a.get("isBook") and a.get("price")]
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        return result
    result.offers = [_offer(a) for a in products]
    return result


def lookup(http: Http, isbn: str) -> Optional[Book]:
    products = [a for a in _products(http, isbn, per_page=5) if a.get("isBook")]
    if not products:
        return None
    a = products[0]
    picture = a.get("picture") or ""
    return Book(
        title=a.get("title") or "",
        author=_author(a),
        year=a.get("yearPublishing") or None,
        isbn=isbn,
        publisher=(a.get("publisher") or {}).get("title") or "",
        cover_url=IMAGES + picture if picture else "",
        binding=a.get("cover") or "",
        source=NAME,
        source_url=f"{SITE}/{a.get('url', '')}",
    )
