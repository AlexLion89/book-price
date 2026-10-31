from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from datetime import date
from typing import Callable, Dict, List, Optional, Tuple

from . import copymarks
from .matching import SERIES_REASON, YEAR, MatchResult, match
from .model import Book, Offer, SourceResult
from .net import Http
from .pricing import LOT_THRESHOLD, Verdict, round_price, suggest
from .value import Dossier, assess
from .sources import alib, avito, chitai_gorod, meshok
from .sources.shops import SHOPS

log = logging.getLogger(__name__)

DEALER_DISCOUNT = 0.8
EXACT_ISBN = {chitai_gorod.NAME}
MARKETPLACES = {s.name for s in SHOPS if not s.bookshop}
USED_NOTE = "б/у"
# A marketplace title naming a print year this old is an old copy on resale, not a new book.
OLD_STOCK_YEARS = 3


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


def exact_offer(o: Offer) -> bool:
    return o.source in EXACT_ISBN or o.by_isbn


def out_of_print(results: List[SourceResult]) -> bool:
    """Shops know this very ISBN but cannot sell it: then marketplace sellers are resellers of old stock."""
    exact = [o for r in results for o in r.offers if exact_offer(o)]
    return bool(exact) and not any(o.in_stock for o in exact)


def resold(o: Offer, sold_out: bool) -> bool:
    if o.note == USED_NOTE or sold_out:
        return True
    years = [int(y) for y in YEAR.findall(o.title)]
    return bool(years) and max(years) <= date.today().year - OLD_STOCK_YEARS


def classify(book: Book, results: List[SourceResult], marks: Dict[Tuple[str, str], bool]) -> List[Found]:
    found = []
    sold_out = bool(book.isbn) and out_of_print(results)
    for r in results:
        source_kind = BY_NAME[r.source].kind if r.source in BY_NAME else "shop"
        for o in r.offers:
            kind = source_kind
            if r.source in MARKETPLACES and resold(o, sold_out):
                kind = "dealer"
            exact = kind == "shop" and bool(book.isbn) and exact_offer(o)
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
             own_sales: Optional[List[dict]] = None, copy_marks: Optional[List[str]] = None) -> Verdict:
    return evaluate_with_dossier(book, found, manual, condition, own_sales, copy_marks)[0]


def evaluate_with_dossier(book: Book, found: List[Found], manual: List[Offer], condition: str,
                          own_sales: Optional[List[dict]] = None,
                          copy_marks: Optional[List[str]] = None) -> Tuple[Verdict, Dossier]:
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
    if not any(o.in_stock for o in shops):
        # "Нет в продаже" is about this edition; a reprint sold new is worth knowing, though it does not set the price.
        reprints = [f.offer for f in found if f.kind == "shop" and not f.counted and f.offer.in_stock
                    and (f.verdict == "maybe" or (f.verdict == "other" and not f.reason.startswith(SERIES_REASON)))]
        if reprints:
            cheapest = min(reprints, key=lambda o: o.price)
            label = BY_NAME[cheapest.source].label if cheapest.source in BY_NAME else cheapest.source
            verdict.reasons.append(f"в магазинах есть другие издания — от {cheapest.price:.0f} ₽ ({label}); в цену они "
                                   f"не идут, а если это ваше издание — отметьте его галочкой в списке ниже")
    exact = [f.offer for f in found if exact_offer(f.offer)]
    sold_out = bool(exact) and not any(o.in_stock for o in exact)
    dossier = assess(book, len(used), any(o.in_stock for o in shops), sold_out)
    if verdict.scenario == "only_used" and dossier.premium:
        verdict.start = round_price(verdict.start * (1 + dossier.premium))
        reasons = "; ".join(x.label.lower() for x in dossier.factors if x.premium)
        verdict.reasons.append(f"надбавка +{dossier.premium * 100:.0f} % к начальной цене ({reasons}) — "
                               f"если не продаётся, график снижения вернёт цену к рынку")
    copy = copymarks.factor(copy_marks or [])
    if verdict.start is not None and copy != 1:
        verdict.start = round_price(verdict.start * copy)
        verdict.floor = min(round_price(verdict.floor * copy), verdict.start)
        verdict.reasons.append(f"особенности экземпляра: {copymarks.describe(copy_marks)} — к начальной цене и пределу")
    if verdict.as_lot and verdict.start is not None and verdict.start >= LOT_THRESHOLD:
        verdict.as_lot = False
        verdict.reasons = [r for r in verdict.reasons if not r.startswith("дешевле")]
    if own_sales:
        last = own_sales[0]
        verdict.reasons.append(f"вы уже продавали такую: за {last['sold_price']} ₽ "
                               f"{(last['sold_at'] or '')[:10]}" + (f" (всего продаж: {len(own_sales)})" if len(own_sales) > 1 else ""))
    return verdict, dossier
