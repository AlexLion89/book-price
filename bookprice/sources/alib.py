from __future__ import annotations

import html
import re
import urllib.parse
from typing import List

from ..matching import significant
from ..model import Book, Offer, SourceResult
from ..net import Http

NAME = "alib"
LABEL = "alib (букинисты)"
SITE = "https://www.alib.ru"
ENTRY = re.compile(r"<p>\s*<b>(?P<head>.*?)</b>(?P<body>.*?)(?=<p>|<h3>|</td>|$)", re.S | re.I)
PRICE = re.compile(r"Цена:\s*(?P<price>[\d\s]+)\s*руб")
BUY = re.compile(r"<a href=\"(?P<url>[^\"]+)\"><b>Купить</b>", re.I)
SELLER = re.compile(r"BS - [^<]*</a>,\s*(?P<city>[^.)]+)")


def clean(fragment: str) -> str:
    return " ".join(html.unescape(re.sub(r"<[^>]+>", " ", fragment)).split())


def query(book: Book) -> str:
    words = significant(book.author)[-1:] + significant(book.title)
    return " ".join(words)


def search_url(q: str) -> str:
    return f"{SITE}/find3.php4?" + urllib.parse.urlencode({"tfind": q}, encoding="cp1251")


def parse(page: str) -> List[Offer]:
    offers = []
    for m in ENTRY.finditer(page):
        body = m.group("body")
        price = PRICE.search(body)
        if not price:
            continue
        bibliographic = body.split("(До заказа")[0]
        buy = BUY.search(body)
        seller = SELLER.search(body)
        url = buy.group("url") if buy else ""
        offers.append(Offer(
            source=NAME,
            price=float(re.sub(r"\s", "", price.group("price"))),
            url=url,
            title=clean(m.group("head")),
            text=clean(bibliographic),
            ext_id=url.rsplit("_", 1)[-1].replace(".html", "") if url else "",
            place=seller.group("city").strip() if seller else "",
        ))
    return offers


def search(http: Http, book: Book) -> SourceResult:
    q = query(book)
    result = SourceResult(source=NAME, search_url=search_url(q))
    try:
        page = http.get(result.search_url).decode("cp1251", "replace")
    except Exception as e:
        result.error = f"{type(e).__name__}: {e}"
        return result
    result.offers = parse(page)
    return result
