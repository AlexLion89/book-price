"""Marks of the owner's own copy — the program cannot see them, only the owner can tick them.

Unlike rarity they describe this copy against the typical ones on the market, so they move both the starting
price and the floor, as the condition does.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import List

MIN_FACTOR, MAX_FACTOR = 0.6, 1.6


@dataclass(frozen=True)
class Mark:
    key: str
    label: str
    effect: float
    ad: str


MARKS = [
    Mark("autograph", "С автографом автора", 0.30, "с автографом автора"),
    Mark("first", "Первое издание", 0.15, "первое издание"),
    Mark("case", "В футляре или подарочной коробке", 0.10, "в футляре"),
    Mark("jacket", "Суперобложка на месте", 0.05, "с суперобложкой"),
    Mark("library", "Библиотечные штампы", -0.15, "есть библиотечные штампы"),
    Mark("inscription", "Дарственная надпись или чужие пометки", -0.10, "есть дарственная надпись или пометки"),
]
BY_KEY = {m.key: m for m in MARKS}


def chosen(keys: List[str]) -> List[Mark]:
    return [BY_KEY[k] for k in keys if k in BY_KEY]


def factor(keys: List[str]) -> float:
    return min(max(1 + sum(m.effect for m in chosen(keys)), MIN_FACTOR), MAX_FACTOR)


def describe(keys: List[str]) -> str:
    return ", ".join(f"{m.label.lower()} {'+' if m.effect > 0 else '−'}{abs(m.effect) * 100:.0f} %" for m in chosen(keys))


def ad_lines(keys: List[str]) -> List[str]:
    good = [m.ad for m in chosen(keys) if m.effect > 0]
    bad = [m.ad for m in chosen(keys) if m.effect < 0]
    lines = []
    if good:
        lines.append("Особенности: " + ", ".join(good) + ".")
    if bad:
        lines.append("Честно: " + ", ".join(bad) + ".")
    return lines
