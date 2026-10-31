"""Reader ratings from LiveLib and LitRes, read in the search window once per book.

Book pages carry schema.org markup for search engines (aggregateRating: value and count); it survives redesigns
better than CSS classes. Search results only give the link to the right book.
"""
from __future__ import annotations

import logging
import urllib.parse
from dataclasses import dataclass
from typing import Callable, Dict, List, Optional

from ..matching import match, significant
from ..model import Book

log = logging.getLogger(__name__)

CANDIDATES = r"""
({linkPattern, max}) => {
  const linkRe = new RegExp(linkPattern);
  const seen = new Set(), out = [];
  for (const a of document.querySelectorAll('a[href]')) {
    const href = a.href.split('?')[0].split('#')[0];
    if (!linkRe.test(href) || seen.has(href)) continue;
    let box = a;
    for (let i = 0; i < 4 && box.parentElement && (box.innerText || '').length < 200; i++) box = box.parentElement;
    const title = (a.innerText || a.getAttribute('title') || '').replace(/\s+/g, ' ').trim();
    if (!title) continue;
    seen.add(href);
    out.push({href, title, text: (box.innerText || '').replace(/\s+/g, ' ').trim().slice(0, 300)});
    if (out.length >= max) break;
  }
  return out;
}
"""

RATING = r"""
() => {
  const found = [];
  const walk = o => {
    if (!o || typeof o !== 'object') return;
    if (Array.isArray(o)) return o.forEach(walk);
    if (o.aggregateRating) found.push(o.aggregateRating);
    Object.values(o).forEach(walk);
  };
  for (const s of document.querySelectorAll('script[type="application/ld+json"]')) {
    try { walk(JSON.parse(s.textContent)); } catch (e) {}
  }
  const prop = p => { const el = document.querySelector(`[itemprop="${p}"]`);
                      return el ? (el.getAttribute('content') || el.textContent || '').trim() : null; };
  if (!found.length && prop('ratingValue')) {
    found.push({ratingValue: prop('ratingValue'), ratingCount: prop('ratingCount') || prop('reviewCount'),
                bestRating: prop('bestRating')});
  }
  const num = v => v == null ? null : parseFloat(String(v).replace(',', '.').replace(/[^0-9.]/g, '')) || null;
  const r = found[0];
  return r ? {value: num(r.ratingValue), count: num(r.ratingCount || r.reviewCount), best: num(r.bestRating) || 5} : null;
}
"""


@dataclass
class Site:
    key: str
    label: str
    search: Callable[[str], str]
    link_pattern: str


SITES = [
    Site("livelib", "LiveLib", lambda q: "https://www.livelib.ru/find/books/" + urllib.parse.quote(q),
         r"livelib\.ru/book/\d+"),
    Site("litres", "ЛитРес", lambda q: "https://www.litres.ru/search/?" + urllib.parse.urlencode({"q": q}),
         r"litres\.ru/(book|audiobook)/[^/]+/[^/]+-\d+/?$"),
]


def query(book: Book) -> str:
    surname = significant(book.author)[-1:] if book.author else []
    return " ".join([book.title, *surname])


def pick(book: Book, candidates: List[dict]) -> Optional[dict]:
    """The same edition first, then the same book; another volume of a series or a set never counts."""
    verdicts = [(c, match(book, c["title"], c["text"]).verdict) for c in candidates]
    for wanted in ("yes", "maybe"):
        for c, verdict in verdicts:
            if verdict == wanted:
                return c
    return None


def collect(browser, book: Book, say: Callable[[str], None] = lambda s: None) -> Dict[str, object]:
    facts: Dict[str, object] = {}
    for site in SITES:
        try:
            browser.open(site.search(query(book)), site.key, ready='a[href*="/book/"]')
            browser.snapshot(f"{site.key}-search")
            chosen = pick(book, browser.evaluate(CANDIDATES, {"linkPattern": site.link_pattern, "max": 20}) or [])
            if not chosen:
                say(f"  {site.label}: книга не нашлась")
                browser.snapshot(f"{site.key}-search", force=True)
                continue
            browser.open(chosen["href"], site.key)
            browser.snapshot(f"{site.key}-book")
            rating = browser.evaluate(RATING)
            if not rating or not rating.get("value"):
                say(f"  {site.label}: рейтинг на странице не нашёлся")
                browser.snapshot(f"{site.key}-book", force=True)
                continue
            value = rating["value"] * 5 / (rating.get("best") or 5)
            facts.update({f"{site.key}_rating": round(value, 2), f"{site.key}_votes": int(rating.get("count") or 0),
                          f"{site.key}_url": chosen["href"]})
            say(f"  {site.label}: {value:.1f} из 5, оценок {int(rating.get('count') or 0)}")
        except Exception as e:
            log.warning("%s: рейтинг не прочитан: %s", site.key, e)
            say(f"  {site.label}: не получилось — {type(e).__name__}")
            browser.snapshot(site.key, force=True)
    return facts
