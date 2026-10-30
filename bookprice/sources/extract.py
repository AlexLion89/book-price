"""In-page extractors. They run inside Edge, so they see the page after its own scripts have rendered it."""
from __future__ import annotations

from typing import List

from ..model import Offer

# A shop tile: the nearest block around a product link that has a price and no other product inside.
# Survives renamed CSS classes — only the link format has to stay. Blocks marked data-bp-skip are ignored.
TILES = r"""
({linkPattern, max}) => {
  const linkRe = new RegExp(linkPattern);
  const priceRe = /(\d[\d\s]*)\s*₽/;
  const keyOf = href => href.split('?')[0].split('#')[0];
  const tiles = new Map();
  for (const a of document.querySelectorAll('a[href]')) {
    if (!linkRe.test(a.href) || a.closest('[data-bp-skip]')) continue;
    const key = keyOf(a.href);
    let el = a.parentElement, tile = null;
    for (let i = 0; i < 8 && el; i++, el = el.parentElement) {
      const links = new Set([...el.querySelectorAll('a[href]')].map(x => x.href).filter(h => linkRe.test(h)).map(keyOf));
      if (links.size > 1) break;
      if (priceRe.test(el.innerText || '')) { tile = el; break; }
    }
    if (!tile) continue;
    const text = (tile.innerText || '').replace(/\s+/g, ' ').trim();
    const m = text.match(priceRe);
    const title = (a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '').replace(/\s+/g, ' ').trim();
    const prev = tiles.get(key);
    if (!prev || title.length > prev.title.length) {
      tiles.set(key, {url: key, title: title || (prev && prev.title) || '', text: text.slice(0, 400),
                      price: parseInt(m[1].replace(/\D/g, ''), 10)});
    }
  }
  return [...tiles.values()].filter(t => t.price > 0).slice(0, max);
}
"""

NOTHING_FOUND = r"""
() => /ничего не на(шлось|йдено)|товаров сейчас нет|по запросу .{0,60} не найдено|не нашли/i
      .test((document.body.innerText || '').slice(0, 5000))
"""


def tiles(browser, link_pattern: str, source: str, limit: int = 40) -> List[Offer]:
    raw = browser.evaluate(TILES, {"linkPattern": link_pattern, "max": limit})
    return [Offer(source=source, price=float(t["price"]), url=t["url"], title=t["title"], text=t["text"],
                  ext_id=t["url"]) for t in raw]


def nothing_found(browser) -> bool:
    return bool(browser.evaluate(NOTHING_FOUND))
