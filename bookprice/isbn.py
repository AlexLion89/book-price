from __future__ import annotations

import re
from typing import Optional


def digits(raw: str) -> str:
    return re.sub(r"[^0-9Xx]", "", raw or "").upper()


def valid13(code: str) -> bool:
    if len(code) != 13 or not code.isdigit():
        return False
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(code[:12]))
    return (10 - total % 10) % 10 == int(code[12])


def valid10(code: str) -> bool:
    if len(code) != 10 or not code[:9].isdigit() or not (code[9].isdigit() or code[9] == "X"):
        return False
    total = sum((10 - i) * (10 if c == "X" else int(c)) for i, c in enumerate(code))
    return total % 11 == 0


def to13(code: str) -> str:
    core = "978" + code[:9]
    total = sum(int(c) * (1 if i % 2 == 0 else 3) for i, c in enumerate(core))
    return core + str((10 - total % 10) % 10)


def normalize(raw: str) -> Optional[str]:
    code = digits(raw)
    if valid13(code) and code.startswith(("978", "979")):
        return code
    if valid10(code):
        return to13(code)
    return None


def hyphenless(raw: str) -> str:
    return digits(raw)
