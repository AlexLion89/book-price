"""How rare and wanted the book is: a premium on the starting price. The floor stays at the market, so if the
book does not sell at the premium price, the step-down schedule brings it back to the market."""
from __future__ import annotations

import re
from dataclasses import asdict, dataclass, field
from datetime import date
from typing import List, Optional, Tuple

from .model import Book

MAX_PREMIUM = 0.5
OUT_OF_PRINT = [(20, 0.15), (10, 0.10), (5, 0.05)]
FRESH_REPRINT = 3
FEW_LISTINGS = [(2, 0.10), (5, 0.05)]
SMALL_RUN = 3000
COLLECTIBLE = [0.0, 0.10, 0.20, 0.30]
# "Внутренние иллюстрации" are ordinary chapter drawings in mass fantasy series — only explicit wording counts.
COLLECTIBLE_WORDS = [
    ("подарочн", "подарочное издание"),
    ("коллекц", "коллекционное издание"),
    ("иллюстрированн", "иллюстрированное издание"),
    ("цветные иллюстрац", "цветные иллюстрации"),
    ("цветными иллюстрац", "цветные иллюстрации"),
    ("полноцветн", "полноцветная печать"),
    ("нумерован", "нумерованный экземпляр"),
    ("кожан", "кожаный переплёт"),
    ("лимит", "ограниченный тираж"),
    ("обрез", "окрашенный или золотой обрез"),
    ("литературные памятники", "серия «Литературные памятники»"),
]
LARGE_FORMAT = re.compile(r"/(8|16)\b")


@dataclass
class Factor:
    label: str
    detail: str
    premium: float = 0.0


@dataclass
class Dossier:
    facts: List[Tuple[str, str]] = field(default_factory=list)
    factors: List[Factor] = field(default_factory=list)
    collectible: List[str] = field(default_factory=list)
    popularity: str = ""
    premium: float = 0.0

    def to_dict(self) -> dict:
        return asdict(self)


def years_word(n: int) -> str:
    if n % 10 == 1 and n % 100 != 11:
        return "год"
    if 2 <= n % 10 <= 4 and not 12 <= n % 100 <= 14:
        return "года"
    return "лет"


def popularity(f: dict) -> Tuple[str, float]:
    """FantLab rates 1–10 with many voters for fiction; the shop's 1–5 rating covers the rest."""
    r, v = f.get("work_rating"), f.get("work_voters") or 0
    if r:
        label = ("очень известная" if v >= 3000 else "известная" if v >= 300 else
                 "нишевая" if v >= 30 else "мало оценок")
        premium = 0.10 if r >= 8 and v >= 2000 else 0.05 if r >= 7.5 and v >= 300 else 0.0
        return f"{label}: FantLab {r:.2f} из 10, оценок {v}", premium
    r, v = f.get("cg_rating"), f.get("cg_votes") or 0
    if r:
        return f"Читай-город {r:.1f} из 5, оценок {v}", 0.05 if r >= 4.6 and v >= 100 else 0.0
    return "", 0.0


def collectible_signs(book: Book) -> List[str]:
    f = book.facts
    signs = []
    if f.get("copies") and f["copies"] <= SMALL_RUN:
        signs.append(f"малый тираж — {f['copies']} экз.")
    if "суперобложк" in (f.get("cover") or book.binding or "").lower():
        signs.append("суперобложка")
    if LARGE_FORMAT.search(f.get("format") or ""):
        signs.append("увеличенный формат")
    if book.year and book.year <= 1917:
        signs.append("дореволюционное издание")
    elif book.year and book.year <= 1960:
        signs.append("издание до 1960 года")
    text = " ".join([f.get("description") or "", " ".join(f.get("series") or []), book.title]).lower()
    signs += [label for word, label in COLLECTIBLE_WORDS if word in text]
    return list(dict.fromkeys(signs))


def assess(book: Book, used_count: int, new_in_stock: bool, sold_out: bool = False,
           today: Optional[date] = None) -> Dossier:
    """sold_out: the exact-ISBN shop says «нет в продаже». Without FantLab's reprint history of the text, only then
    does the edition's own last print year count as «out of print»."""
    f = book.facts or {}
    year = (today or date.today()).year
    d = Dossier()

    if f.get("copies"):
        d.facts.append(("Тираж", f"{f['copies']:,} экз.".replace(",", " ")))
    if f.get("series"):
        d.facts.append(("Серия", ", ".join(f["series"])))
    last = f.get("work_last_year") or (max(book.years()) if sold_out and book.years() else None)
    if last:
        editions = f.get("work_editions")
        d.facts.append(("Последнее бумажное издание", f"{last} г." + (f" (всего изданий: {editions})" if editions else "")))
    d.popularity, demand = popularity(f)
    if d.popularity:
        d.facts.append(("Известность", d.popularity))
    d.facts.append(("Похожих объявлений на Авито", str(used_count)))
    d.collectible = collectible_signs(book)

    if new_in_stock:
        d.factors.append(Factor("Новая есть в магазине", "надбавок нет: покупатель возьмёт новую"))
        return d
    if f.get("work_planned"):
        d.factors.append(Factor("Скоро переиздадут", "книга в планах издательств — надбавки за редкость нет"))
    elif last and year - last <= FRESH_REPRINT:
        d.factors.append(Factor("Текст переиздают", f"последнее издание — {last} г.: купить новым можно"))
    elif last:
        gap = year - last
        bonus = next((p for limit, p in OUT_OF_PRINT if gap >= limit), 0.0)
        if bonus:
            d.factors.append(Factor("Давно не переиздавалась", f"последнее издание — {last} г., {gap} {years_word(gap)} назад", bonus))
    if used_count:
        bonus = next((p for limit, p in FEW_LISTINGS if used_count <= limit), 0.0)
        if bonus:
            d.factors.append(Factor("Мало предложений", f"на Авито похожих — {used_count}", bonus))
    if demand:
        d.factors.append(Factor("Спрос", d.popularity, demand))
    if d.collectible:
        bonus = COLLECTIBLE[min(len(d.collectible), len(COLLECTIBLE) - 1)]
        d.factors.append(Factor("Коллекционные признаки", ", ".join(d.collectible), bonus))
    d.premium = min(sum(x.premium for x in d.factors), MAX_PREMIUM)
    return d
