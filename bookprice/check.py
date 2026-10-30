"""Site check: runs every source on sample books, keeps page snapshots, packs everything into one zip."""
from __future__ import annotations

import json
import logging
import os
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import Callable, List, Optional

from . import catalog, paths
from .browser import Browser
from .model import Book
from .net import Http
from .search import BY_NAME, classify, run
from .sources import chitai_gorod

log = logging.getLogger(__name__)

SAMPLES = [
    "9785389016866",
    Book(title="Незнайка на Луне", author="Николай Носов", year=1986),
]


def run_check(data_dir: Path, say: Callable[[str], None], extra_isbn: Optional[str] = None,
              only: Optional[List[str]] = None) -> Path:
    work = data_dir / "check" / f"{datetime.now():%Y%m%d-%H%M%S}"
    work.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(work / "check.log", encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s"))
    logging.getLogger().addHandler(handler)
    http = Http()
    def captcha(source: str) -> None:
        label = BY_NAME[source].label if source in BY_NAME else source
        say(f"{label}: решите проверку в окне Edge, я подожду")

    browser = Browser(work, on_captcha=captcha, keep_snapshots=True)
    report = []
    only = only or [s for s in os.environ.get("BOOKPRICE_ONLY", "").split(",") if s] or None
    try:
        say("Проверка браузера: открываю Читай-город в Edge…")
        browser.open(chitai_gorod.search_url("9785389016866"), "selftest")
        say(f"  Edge работает, страница: {browser.page.title()[:70]}")
        browser.snapshot("selftest")
        for sample in ([extra_isbn] if extra_isbn else []) + SAMPLES:
            book = catalog.identify(http, sample) if isinstance(sample, str) else sample
            if not book:
                say(f"{sample}: книга не найдена в справочниках")
                continue
            say(f"{book.author} — {book.title} ({book.year or 'год ?'})")
            results = run(book, http, browser, lambda name, state: state == "running" and say(f"  {BY_NAME[name].label}…"),
                          only)
            found = classify(book, results, {})
            for r in results:
                counted = sum(f.counted for f in found if f.offer.source == r.source)
                state = f"ошибка: {r.error}" if r.error else f"найдено {len(r.offers)}, подходят {counted}"
                say(f"  {BY_NAME[r.source].label}: {state}")
            report.append({"book": book.to_dict(), "results": [r.to_dict() for r in results],
                           "found": [f.to_dict() for f in found]})
    finally:
        browser.close()
        (work / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        logging.getLogger().removeHandler(handler)
        handler.close()
    target = paths.desktop() / f"проверка-площадок-{work.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in work.rglob("*"):
            if f.is_file() and "edge-profile" not in f.parts:
                z.write(f, f.relative_to(work))
    say(f"Готово. Файл на рабочем столе: {target.name}")
    return target


def main(argv: List[str]) -> Path:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    only = [a.split("=", 1)[1].split(",") for a in argv if a.startswith("--only=")]
    isbns = [a for a in argv if not a.startswith("--")]
    return run_check(paths.data_dir(), print, isbns[0] if isbns else None, only[0] if only else None)


if __name__ == "__main__":
    main(sys.argv[1:])
