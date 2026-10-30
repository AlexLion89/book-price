from __future__ import annotations

from datetime import datetime
from typing import Optional

from .model import Book
from .pricing import CONDITION_LABEL, STEP_DAYS, round_price

STEP = 0.9
BINDING = {
    "твёрдая": "твёрдый переплёт",
    "твердая": "твёрдый переплёт",
    "мягкая": "мягкая обложка",
    "интегральная": "интегральный переплёт",
}


def binding_text(raw: str) -> str:
    raw = (raw or "").strip().lower()
    return BINDING.get(raw, raw)


def ad_text(book: Book, condition: str) -> str:
    title = f"{book.author} — {book.title}" if book.author else book.title
    details = [book.publisher, f"{book.year} г." if book.year else "", binding_text(book.binding),
               f"{book.pages} стр." if book.pages else ""]
    lines = [title, ", ".join(d for d in details if d)]
    if book.isbn:
        lines.append(f"ISBN {book.isbn}")
    lines += [
        "",
        f"Состояние: {CONDITION_LABEL[condition]}.",
        "Самовывоз в Санкт-Петербурге или отправлю Авито Доставкой.",
    ]
    return "\n".join(lines)


def next_step(listed_price: Optional[int], changed_at: Optional[str], floor: Optional[int],
              today: Optional[datetime] = None) -> Optional[dict]:
    """When the book has hung for a week at the same price, suggest the next, lower one — never below the floor."""
    if not listed_price or not changed_at:
        return None
    days = ((today or datetime.now()).date() - datetime.fromisoformat(changed_at).date()).days
    lower = max(round_price(listed_price * STEP), floor or 0)
    if days < STEP_DAYS or lower >= listed_price:
        return None
    return {"days": days, "price": lower}
