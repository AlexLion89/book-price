from __future__ import annotations

import logging
import re
from typing import List, Optional

from ..net import Http
from ..model import Book

log = logging.getLogger(__name__)
API = "https://api.fantlab.ru"
SITE = "https://fantlab.ru"
MARKUP = re.compile(r"\[/?[a-z]+(=[^\]]*)?\]")
REPRINT = re.compile(r"\b(1[89]\d\d|20\d\d)\s*г\.\s*[-–—]\s*[\d\s]+\s*экз")


def strip_markup(text: str) -> str:
    return MARKUP.sub("", text or "").strip()


def reprint_years(notes: str) -> List[int]:
    return sorted({int(y) for y in REPRINT.findall(notes or "")})


def first_year(value) -> Optional[int]:
    try:
        year = int(value)
    except (TypeError, ValueError):
        return None
    return year or None


WORK_LINK = re.compile(r"/work(\d+)")
PAPER_BLOCK, PLANNED_BLOCK = "10", "1"


def edition_facts(d: dict) -> dict:
    """What tells a reader's copy from a collector's one: print run, series, cover, format, notes."""
    works = WORK_LINK.findall(" ".join(str(c) for c in d.get("content") or []))
    copies = d.get("copies")
    return {
        "copies": int(copies) if str(copies or "").isdigit() and int(copies) > 0 else None,
        "series": [s["name"] for s in d.get("series") or [] if s.get("name")],
        "cover": d.get("cover_type") or "",
        "format": d.get("format") or "",
        "description": strip_markup(d.get("description") or "")[:500],
        "work_id": int(works[0]) if len(set(works)) == 1 else None,
    }


def work_facts(http: Http, work_id: int) -> dict:
    """Rating and the reprint history of the text itself, across all publishers."""
    w = http.json(f"{API}/work/{work_id}", {"extended": 1})
    rating = w.get("rating") or {}
    blocks = w.get("editions_blocks") or {}
    paper = [e.get("year") for e in (blocks.get(PAPER_BLOCK) or {}).get("list") or []]
    years = sorted({int(y) for y in paper if str(y or "").isdigit() and int(y) > 0})
    return {
        "work_rating": float(rating.get("rating") or 0) or None,
        "work_voters": int(rating.get("voters") or 0),
        "work_editions": len(paper),
        "work_last_year": years[-1] if years else None,
        "work_planned": bool((blocks.get(PLANNED_BLOCK) or {}).get("list")),
        "work_url": f"{SITE}/work{work_id}",
    }


def edition(http: Http, edition_id: int, isbn: str = "") -> Book:
    d = http.json(f"{API}/edition/{edition_id}", {"content": 1})
    facts = edition_facts(d)
    if facts["work_id"]:
        try:
            facts.update(work_facts(http, facts["work_id"]))
        except Exception:
            log.exception("FantLab: произведение %s", facts["work_id"])
    creators = d.get("creators") or {}
    authors = ", ".join(a["name"] for a in creators.get("authors") or [])
    publishers = ", ".join(p["name"] for p in creators.get("publishers") or [])
    image = d.get("image") or ""
    pages = d.get("pages")
    return Book(
        title=d.get("edition_name") or "",
        author=authors,
        year=first_year(d.get("year")),
        isbn=isbn or ((d.get("isbns") or [""])[0]),
        publisher=publishers,
        cover_url=SITE + image if image else "",
        binding=d.get("cover_type") or "",
        pages=int(pages) if str(pages or "").isdigit() else None,
        reprint_years=reprint_years(d.get("notes") or ""),
        source="fantlab",
        source_url=f"{SITE}/edition{edition_id}",
        facts=facts,
    )


def by_isbn(http: Http, isbn: str) -> Optional[Book]:
    d = http.json(f"{API}/search-editions", {"q": isbn})
    matches = d.get("matches") or []
    if not matches:
        return None
    return edition(http, int(matches[0]["edition_id"]), isbn)


PAGE = 25


def by_title(http: Http, query: str, limit: int = 150) -> List[Book]:
    """Popular titles have 80+ editions and the API returns 25 per page in no useful order."""
    matches = []
    for page in range(1, limit // PAGE + 1):
        d = http.json(f"{API}/search-editions", {"q": query, "page": page})
        batch = d.get("matches") or []
        matches += batch
        if len(batch) < PAGE or len(matches) >= int(d.get("total_found") or 0):
            break
    books = []
    for m in matches[:limit]:
        isbns = [s.strip() for s in (m.get("isbn") or "").split(",") if s.strip()]
        books.append(Book(
            title=m.get("name") or "",
            author=strip_markup(m.get("autors") or ""),
            year=first_year(m.get("year")),
            isbn=isbns[0] if isbns else "",
            publisher=m.get("publisher") or "",
            source="fantlab",
            source_url=f"{SITE}/edition{m['edition_id']}",
        ))
    return books
