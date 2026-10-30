from __future__ import annotations

from dataclasses import dataclass, field
from typing import List, Optional

from .model import Offer

# Relative to "excellent": that is how most Avito listings describe themselves,
# so comparables and past prices are taken as excellent-condition prices.
CONDITION_FACTOR = {
    "new": 1.1,
    "excellent": 1.0,
    "good": 0.85,
    "marked": 0.55,
}
CONDITION_LABEL = {
    "new": "как новая",
    "excellent": "отличное",
    "good": "хорошее",
    "marked": "с пометками или потёртостями",
}

NEW_PRICE_CAP = 0.6
UNDERCUT_COMPETITORS = 0.95
SCARCE_UNDERCUT = 0.93
FEW_LISTINGS = 3
HISTORY_START_FACTOR = 1.9
STEP_PERCENT = 10
STEP_DAYS = 7
MARKET_FLOOR_FACTOR = 0.8
LOT_THRESHOLD = 250


@dataclass
class Verdict:
    scenario: str
    start: Optional[int]
    floor: Optional[int]
    step_percent: int = STEP_PERCENT
    step_days: int = STEP_DAYS
    reasons: List[str] = field(default_factory=list)
    as_lot: bool = False

    def schedule(self) -> List[int]:
        if self.start is None or self.floor is None:
            return []
        prices = [self.start]
        while prices[-1] > self.floor:
            nxt = round_price(prices[-1] * (1 - self.step_percent / 100))
            if nxt >= prices[-1]:
                nxt = prices[-1] - price_unit(prices[-1])
            prices.append(max(nxt, self.floor))
        return prices


def percentile(values: List[float], q: float) -> float:
    if not values:
        raise ValueError("empty")
    s = sorted(values)
    pos = (len(s) - 1) * q
    lo = int(pos)
    hi = min(lo + 1, len(s) - 1)
    return s[lo] + (s[hi] - s[lo]) * (pos - lo)


def drop_outliers(prices: List[float]) -> List[float]:
    if len(prices) < 3:
        return list(prices)
    med = percentile(prices, 0.5)
    return [p for p in prices if med / 3 <= p <= med * 3]


def price_unit(value: float) -> int:
    if value < 500:
        return 10
    if value < 2000:
        return 50
    return 100


def round_price(value: float) -> int:
    unit = price_unit(value)
    return max(unit, int(value / unit + 0.5) * unit)


def suggest(
    shop_offers: List[Offer],
    used_offers: List[Offer],
    past_prices: List[float],
    condition: str = "excellent",
    used_label: str = "на Авито",
) -> Verdict:
    factor = CONDITION_FACTOR[condition]
    in_stock = [o.price for o in shop_offers if o.in_stock]
    used = drop_outliers([o.price for o in used_offers])
    history = list(past_prices) + [o.price for o in shop_offers if not o.in_stock]

    if in_stock:
        new_min = min(in_stock)
        cap = new_min * NEW_PRICE_CAP
        reasons = [f"новая в магазинах от {new_min:.0f} ₽ — б/у дороже {cap:.0f} ₽ обычно не берут"]
        target = cap
        if used:
            a = percentile(used, 0.25)
            reasons.append(f"{used_label} {len(used)} похожих, дешёвая четверть — до {a:.0f} ₽")
            target = min(a * UNDERCUT_COMPETITORS, cap)
        verdict = _market(target * factor, "new_in_shops", reasons)
    elif used:
        a = percentile(used, 0.25)
        reasons = [f"в магазинах нет; {used_label} {len(used)} похожих, дешёвая четверть — до {a:.0f} ₽"]
        if len(used) < FEW_LISTINGS:
            reasons.append("объявлений мало — если они висят месяцами, их цена не рыночная")
        verdict = _market(a * SCARCE_UNDERCUT * factor, "only_used", reasons)
    elif history:
        last = max(history)
        verdict = Verdict(
            scenario="history_only",
            start=round_price(last * HISTORY_START_FACTOR * factor),
            floor=round_price(last * factor),
            reasons=[
                f"сейчас нигде нет; последняя известная цена {last:.0f} ₽",
                f"начать почти с двойной и снижать на {STEP_PERCENT} % раз в {STEP_DAYS} дней",
            ],
        )
    else:
        return Verdict(scenario="unknown", start=None, floor=None,
                       reasons=["цен не нашлось — посмотрите ссылки на поиск вручную"])

    if factor != 1.0:
        verdict.reasons.append(f"состояние «{CONDITION_LABEL[condition]}»: ×{factor}")
    verdict.as_lot = verdict.start is not None and verdict.start < LOT_THRESHOLD
    if verdict.as_lot:
        verdict.reasons.append(f"дешевле {LOT_THRESHOLD} ₽ — выгоднее выставить лотом с другими книгами")
    return verdict


def _market(target: float, scenario: str, reasons: List[str]) -> Verdict:
    start = round_price(target)
    return Verdict(
        scenario=scenario,
        start=start,
        floor=round_price(start * MARKET_FLOOR_FACTOR),
        reasons=reasons,
    )
