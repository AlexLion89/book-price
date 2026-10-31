"""In-page extractors. They run inside Edge, so they see the page after its own scripts have rendered it."""
from __future__ import annotations

import json
from typing import List

from ..model import Offer

# A shop tile: the nearest block around a product link that has a price and no other product inside.
# Survives renamed CSS classes — only the link format has to stay. Blocks marked data-bp-skip are ignored.
# The price is the first one not crossed out (old prices sit in s/del or in classes like "old-price",
# "line-through") and not a signed amount ("+76" bonus points, "−2 664 ₽" discount). An empty currency means
# the shop draws the ruble sign with CSS, so bare numbers count.
TILES = r"""
({linkPattern, max, currency}) => {
  const linkRe = new RegExp(linkPattern);
  const number = '(\\d{1,3}(?:\\s\\d{3})+|\\d+)';
  const priceRe = new RegExp(currency ? number + '\\s*(?:' + currency + ')' : number + '(?![\\d%.,])', 'g');
  // Per class token: old-price, price__old, price-val-old, strikePrice, line-through — but not Meshok's
  // withStrikePrice, the block holding both prices.
  const OLD_TOKEN = /^(old|strike|crossed|line-through)([-_A-Z]|price|$)|[-_](old|strike|crossed)([-_]|$)/i;
  const OLD = {test: cls => cls.split(/\s+/).some(t => OLD_TOKEN.test(t))};
  const NAME = /(^|[-_\s])(name|title)([-_\s]|$)/i;
  const keyOf = href => href.split('?')[0].split('#')[0];
  const isOld = (el, tile) => {
    for (; el && el !== tile.parentElement; el = el.parentElement) {
      if (el.matches('s, del, strike, script, style') || OLD.test(el.getAttribute('class') || '')) return true;
    }
    return false;
  };
  // The rendered text without crossed-out prices. Numbers on different lines never merge: a title ending
  // in "…, 1996" above "700 ₽" must not read as 996 700.
  const textOf = tile => {
    let text = tile.innerText || '';
    for (const el of tile.querySelectorAll('s, del, strike, [class]')) {
      if (!isOld(el, tile) || isOld(el.parentElement, tile) || !el.getClientRects().length) continue;
      const old = (el.innerText || '').trim();
      if (old) text = text.replace(old, '\n');
    }
    return text.split(/\n+/).map(s => s.replace(/\s+/g, ' ').trim()).filter(Boolean)
      .reduce((acc, part) => acc ? acc + (/\d$/.test(acc) && /^\d/.test(part) ? ' · ' : ' ') + part : part, '');
  };
  const priceOf = text => {
    for (const m of text.matchAll(priceRe)) {
      const before = text.slice(0, m.index).trimEnd().slice(-1);
      if (before && '+-−–'.includes(before)) continue;
      const value = parseInt(m[1].replace(/\D/g, ''), 10);
      if (value > 0) return value;
    }
    return 0;
  };
  const tiles = new Map();
  for (const a of document.querySelectorAll('a[href]')) {
    if (!linkRe.test(a.href) || a.closest('[data-bp-skip]')) continue;
    const key = keyOf(a.href);
    let el = a.parentElement, tile = null, price = 0;
    for (let i = 0; i < 8 && el; i++, el = el.parentElement) {
      const links = new Set([...el.querySelectorAll('a[href]')].map(x => x.href).filter(h => linkRe.test(h)).map(keyOf));
      if (links.size > 1) break;
      price = priceOf(textOf(el));
      if (price) { tile = el; break; }
    }
    if (!tile) continue;
    // A "name"/"title" block names the product only if it links nowhere else: a seller's name links to the seller.
    const ownLink = e => { const link = e.closest('a[href]'); return !link || keyOf(link.href) === key; };
    const named = [...tile.querySelectorAll('[class]')].find(e => NAME.test(e.getAttribute('class'))
      && !/price/i.test(e.getAttribute('class')) && (e.innerText || '').trim().length > 2
      && ownLink(e) && [...e.querySelectorAll('a[href]')].every(x => keyOf(x.href) === key));
    const title = ((named && named.innerText) || a.innerText || a.getAttribute('title') || a.getAttribute('aria-label') || '')
      .replace(/\s+/g, ' ').trim();
    const prev = tiles.get(key);
    if (!prev || title.length > prev.title.length) {
      tiles.set(key, {url: key, title: title || (prev && prev.title) || '', text: textOf(tile).slice(0, 400), price});
    }
  }
  return [...tiles.values()].slice(0, max);
}
"""

NOTHING_RE = r"/ничего не на(шлось|йдено)|товаров сейчас нет|по вашему запросу товары не найдены|по запросу .{0,60} не найдено|не нашли/i"
NOTHING_FOUND = f"() => {NOTHING_RE}.test(((document.body && document.body.innerText) || '').slice(0, 5000))"


def link_or_nothing(link_css: str) -> str:
    """A page-ready check: a product link is on the page, or the shop says it found nothing."""
    return (f"() => !!document.querySelector({json.dumps(link_css)}) || "
            f"{NOTHING_RE}.test(((document.body && document.body.innerText) || '').slice(0, 5000))")


def tiles(browser, link_pattern: str, source: str, limit: int = 40, currency: str = "₽") -> List[Offer]:
    raw = browser.evaluate(TILES, {"linkPattern": link_pattern, "max": limit, "currency": currency})
    return [Offer(source=source, price=float(t["price"]), url=t["url"], title=t["title"], text=t["text"],
                  ext_id=t["url"]) for t in raw]


def nothing_found(browser) -> bool:
    return bool(browser.evaluate(NOTHING_FOUND))
