"""Site check: runs every source on sample books, keeps page snapshots, packs everything into one zip."""
from __future__ import annotations

import json
import logging
import sys
import zipfile
from datetime import datetime
from pathlib import Path
from typing import List

from . import catalog, paths
from .browser import Browser
from .model import Book
from .net import Http
from .search import BY_NAME, classify, run

SAMPLES = [
    "9785389016866",
    Book(title="Незнайка на Луне", author="Николай Носов", year=1986),
]


def main(argv: List[str]) -> Path:
    only = [a.split("=", 1)[1].split(",") for a in argv if a.startswith("--only=")]
    argv = [a for a in argv if not a.startswith("--")]
    work = paths.data_dir() / "check" / f"{datetime.now():%Y%m%d-%H%M%S}"
    work.mkdir(parents=True, exist_ok=True)
    handler = logging.FileHandler(work / "check.log", encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler, logging.StreamHandler(sys.stdout)],
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    http = Http()
    browser = Browser(work, on_captcha=lambda s: print(f"\n>>> {s}: решите проверку в окне Edge, я подожду\n"),
                      keep_snapshots=True)
    report = []
    try:
        for sample in [*argv, *SAMPLES] if argv else SAMPLES:
            book = catalog.identify(http, sample) if isinstance(sample, str) else sample
            if not book:
                print(f"{sample}: книга не найдена в справочниках")
                continue
            print(f"\n=== {book.author} — {book.title} ({book.year or 'год ?'}) {book.isbn}")
            results = run(book, http, browser, only=only[0] if only else None)
            found = classify(book, results, {})
            for r in results:
                mine = [f for f in found if f.offer.source == r.source]
                counted = sum(f.counted for f in mine)
                state = f"ОШИБКА {r.error}" if r.error else f"найдено {len(r.offers)}, подходят {counted}"
                print(f"  {BY_NAME[r.source].label:<18} {state}")
            report.append({"book": book.to_dict(), "results": [r.to_dict() for r in results],
                           "found": [f.to_dict() for f in found]})
    finally:
        browser.close()
        (work / "results.json").write_text(json.dumps(report, ensure_ascii=False, indent=1), encoding="utf-8")
        handler.close()
    target = paths.desktop() / f"проверка-площадок-{work.name}.zip"
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as z:
        for f in work.rglob("*"):
            if f.is_file() and "edge-profile" not in f.parts:
                z.write(f, f.relative_to(work))
    print(f"\nГотово. Пришлите этот файл: {target}")
    return target


if __name__ == "__main__":
    main(sys.argv[1:])
