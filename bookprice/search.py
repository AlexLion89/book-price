from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Callable, Dict, List, Optional, Tuple

from .matching import MatchResult, match
from .model import Book, Offer, SourceResult
from .net import Http
from .pricing import Verdict, suggest
from .sources import alib, avito, chitai_gorod, meshok
from .sources.shops import SHOPS

log = logging.getLogger(__name__)

DEALER_DISCOUNT = 0.8
EXACT_ISBN = {chitai_gorod.NAME}
USED_NOTE = "б/у"


@dataclass
class Source:
    name: str
    label: str
    kind: str  # shop — new books, used — Avito, dealer — second-hand booksellers
    needs_browser: bool
    run: Callable


SOURCES: List[Source] = [
    Source(chitai_gorod.NAME, chitai_gorod.LABEL, "shop", False, chitai_gorod.search),
    *[Source(s.name, s.label, "shop", True, s.search) for s in SHOPS],
    Source(avito.NAME, avito.LABEL, "used", True, avito.search),
    Source(alib.NAME, alib.LABEL, "dealer", False, alib.search),
    Source(meshok.NAME, meshok.LABEL, "dealer", True, meshok.search),
]
BY_NAME = {s.name: s for s in SOURCES}


def run(book: Book, http: Http, browser, progress: Callable[[str, str], None] = lambda name, state: None,
        only: Optional[List[str]] = None) -> List[SourceResult]:
    results = []
    for source in SOURCES:
        if only and source.name not in only:
            continue
        progress(source.name, "running")
        try:
            result = source.run(browser if source.needs_browser else http, book)
        except Exception as e:
            log.exception("%s: сбой", source.name)
            result = SourceResult(source=source.name, error=f"{type(e).__name__}: {e}")
        if result.error:
            log.warning("%s: %s", source.name, result.error)
        progress(source.name, "error" if result.error else "done")
        results.append(result)
    return results


@dataclass
class Found:
    offer: Offer
    kind: str
    verdict: str
    reason: str
    counted: bool
    marked: bool

    def to_dict(self) -> dict:
        d = asdict(self)
        d["offer"] = self.offer.to_dict()
        return d


def classify(book: Book, results: List[SourceResult], marks: Dict[Tuple[str, str], bool]) -> List[Found]:
    found = []
    for r in results:
        source_kind = BY_NAME[r.source].kind if r.source in BY_NAME else "shop"
        for o in r.offers:
            kind = "dealer" if source_kind == "shop" and o.note == USED_NOTE else source_kind
            exact = kind == "shop" and bool(book.isbn) and r.source in EXACT_ISBN
            m: MatchResult = match(book, o.title, o.text, o.desc, exact_isbn=exact,
                                   need_author=not (kind == "shop" and book.isbn))
            # Marketplaces answer an ISBN query with every edition of the title, booksellers list every old
            # printing: a cheap pocket edition must not cap the price of a gift one. Only "same edition"
            # counts there by default; Avito listings rarely name the edition, so "same book" is enough.
            auto = m.counted if kind == "used" else m.verdict == "yes"
            key = (o.source, o.ext_id or o.url)
            marked = key in marks
            found.append(Found(o, kind, m.verdict, m.reason, marks[key] if marked else auto, marked))
    return found


def evaluate(book: Book, found: List[Found], manual: List[Offer], condition: str,
             own_sales: Optional[List[dict]] = None) -> Verdict:
    counted = [f for f in found if f.counted]
    shops = [f.offer for f in counted if f.kind == "shop"] + [o for o in manual if BY_NAME[o.source].kind == "shop"]
    used = [f.offer for f in counted if f.kind == "used"] + [o for o in manual if BY_NAME[o.source].kind == "used"]
    past = [float(s["sold_price"]) for s in own_sales or []]
    dealers = [f.offer for f in counted if f.kind == "dealer"]
    if used or not dealers:
        verdict = suggest(shops, used, past, condition)
    else:
        discounted = [Offer(source=o.source, price=o.price * DEALER_DISCOUNT) for o in dealers]
        verdict = suggest(shops, discounted, past, condition, used_label="у букинистов (минус 20 %)")
        verdict.reasons.insert(0, "на Авито похожих нет — ориентир по букинистам: на Авито обычно процентов на 20 дешевле")
    if own_sales:
        last = own_sales[0]
        verdict.reasons.append(f"вы уже продавали такую: за {last['sold_price']} ₽ "
                               f"{(last['sold_at'] or '')[:10]}" + (f" (всего продаж: {len(own_sales)})" if len(own_sales) > 1 else ""))
    return verdict
