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

# A used copy sells for up to ~80 % of a new one in shops (the owner's rule of thumb: new at 500, Avito at 400).
NEW_PRICE_CAP = 0.8
# Start a little under the middle of comparable listings and step down towards their cheap quarter:
# cheap listings sell and vanish, so the cheap quarter is where a listing ends up, not where it starts.
START_UNDERCUT = 0.95
FLOOR_MIN = 0.7
FLOOR_MAX = 0.9
FEW_LISTINGS = 3
HISTORY_START_FACTOR = 1.9
STEP_PERCENT = 10
STEP_DAYS = 7
MARKET_FLOOR_FACTOR = 0.8
LOT_THRESHOLD = 200


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

    sold_out = sorted(o.price for o in shop_offers if not o.in_stock)
    if used:
        middle, cheap = percentile(used, 0.5), percentile(used, 0.25)
        market = (f"{used_label} похожих объявлений: {len(used)}, середина — {middle:.0f} ₽, "
                  f"дешёвая четверть — {cheap:.0f} ₽")
        start = middle * START_UNDERCUT
        floor = min(max(cheap, start * FLOOR_MIN), start * FLOOR_MAX)
    if in_stock:
        new_min = min(in_stock)
        cap = new_min * NEW_PRICE_CAP
        reasons = [f"новая в магазинах от {new_min:.0f} ₽ — б/у дороже {cap:.0f} ₽ обычно не берут"]
        if used:
            reasons.append(market)
            start, floor = min(start, cap), min(floor, cap * MARKET_FLOOR_FACTOR)
        else:
            start, floor = cap, cap * MARKET_FLOOR_FACTOR
        verdict = _market(start * factor, floor * factor, "new_in_shops", reasons)
    elif used:
        was = ""
        if len(sold_out) == 1:
            was = f" (последняя цена новой — {sold_out[0]:.0f} ₽)"
        elif sold_out:
            was = f" (последние цены новой — {sold_out[0]:.0f}–{sold_out[-1]:.0f} ₽)"
        reasons = [f"в магазинах нет в продаже{was}", market]
        if len(used) < FEW_LISTINGS:
            reasons.append("объявлений мало — цена приблизительная; если они висят месяцами, она завышена")
        verdict = _market(start * factor, floor * factor, "only_used", reasons)
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


def _market(start: float, floor: float, scenario: str, reasons: List[str]) -> Verdict:
    start_price = round_price(start)
    return Verdict(scenario=scenario, start=start_price, floor=min(round_price(floor), start_price), reasons=reasons)
