from __future__ import annotations

import json
import sqlite3
import threading
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

from .model import Book, Offer, SourceResult

SCHEMA = """
create table if not exists books(
  id integer primary key, created_at text, isbn text, title text, author text, year integer,
  publisher text, cover_url text, binding text, pages integer, reprint_years text, source_url text,
  condition text default 'excellent', status text default 'draft',
  listed_price integer, price_changed_at text, sold_price integer, sold_at text, searched_at text);
create table if not exists offers(
  book_id integer, source text, ext_id text, price real, url text, title text, text text,
  in_stock integer, place text, age text, note text, description text);
create index if not exists offers_book on offers(book_id);
create table if not exists source_runs(
  book_id integer, source text, search_url text, error text, snapshot text, at text,
  primary key(book_id, source));
create table if not exists marks(
  book_id integer, source text, ext_id text, counted integer, primary key(book_id, source, ext_id));
create table if not exists manual(book_id integer, source text, price real, primary key(book_id, source));
create table if not exists price_log(book_id integer, at text, price integer, event text);
"""
BOOK_FIELDS = ["isbn", "title", "author", "year", "publisher", "cover_url", "binding", "pages", "source_url"]
EDITABLE = {"condition", "status", "listed_price", "price_changed_at", "sold_price", "sold_at",
            "title", "author", "year"}


def now() -> str:
    return datetime.now().isoformat(timespec="seconds")


class Store:
    def __init__(self, path: Path) -> None:
        self.lock = threading.Lock()
        self.db = sqlite3.connect(str(path), check_same_thread=False)
        self.db.row_factory = sqlite3.Row
        with self.lock:
            self.db.executescript(SCHEMA)
            columns = {r[1] for r in self.db.execute("pragma table_info(offers)")}
            if "description" not in columns:
                self.db.execute("alter table offers add column description text")

    def _q(self, sql: str, args=()) -> List[sqlite3.Row]:
        with self.lock, self.db:
            return self.db.execute(sql, args).fetchall()

    def add_book(self, book: Book, condition: str = "excellent") -> int:
        with self.lock, self.db:
            cur = self.db.execute(
                f"insert into books(created_at, condition, reprint_years, {', '.join(BOOK_FIELDS)}) "
                f"values (?, ?, ?, {', '.join('?' * len(BOOK_FIELDS))})",
                [now(), condition, json.dumps(book.reprint_years)] + [getattr(book, f) for f in BOOK_FIELDS])
            return cur.lastrowid

    def book(self, book_id: int) -> Tuple[Book, dict]:
        rows = self._q("select * from books where id = ?", (book_id,))
        if not rows:
            raise KeyError(book_id)
        row = dict(rows[0])
        book = Book(**{f: row[f] or ("" if f not in ("year", "pages") else None) for f in BOOK_FIELDS},
                    reprint_years=json.loads(row["reprint_years"] or "[]"))
        return book, row

    def books(self) -> List[dict]:
        return [dict(r) for r in self._q("select * from books order by id desc")]

    def update(self, book_id: int, **fields) -> None:
        fields = {k: v for k, v in fields.items() if k in EDITABLE}
        if fields:
            sets = ", ".join(f"{k} = ?" for k in fields)
            self._q(f"update books set {sets} where id = ?", [*fields.values(), book_id])

    def delete(self, book_id: int) -> None:
        for table in ("offers", "source_runs", "marks", "manual", "price_log"):
            self._q(f"delete from {table} where book_id = ?", (book_id,))
        self._q("delete from books where id = ?", (book_id,))

    def save_results(self, book_id: int, results: List[SourceResult]) -> None:
        with self.lock, self.db:
            for r in results:
                self.db.execute("delete from offers where book_id = ? and source = ?", (book_id, r.source))
                self.db.executemany(
                    "insert into offers(book_id, source, ext_id, price, url, title, text, in_stock, place, age, note,"
                    " description) values (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    [(book_id, o.source, o.ext_id or o.url, o.price, o.url, o.title, o.text, int(o.in_stock),
                      o.place, o.age, o.note, o.desc) for o in r.offers])
                self.db.execute("insert or replace into source_runs values (?, ?, ?, ?, ?, ?)",
                                (book_id, r.source, r.search_url, r.error, r.snapshot, now()))
            self.db.execute("update books set searched_at = ? where id = ?", (now(), book_id))

    def results(self, book_id: int) -> List[SourceResult]:
        runs = {r["source"]: SourceResult(source=r["source"], search_url=r["search_url"], error=r["error"] or "",
                                          snapshot=r["snapshot"] or "")
                for r in self._q("select * from source_runs where book_id = ?", (book_id,))}
        for r in self._q("select * from offers where book_id = ?", (book_id,)):
            if r["source"] in runs:
                runs[r["source"]].offers.append(Offer(
                    source=r["source"], price=r["price"], url=r["url"], title=r["title"], text=r["text"],
                    in_stock=bool(r["in_stock"]), ext_id=r["ext_id"], place=r["place"], age=r["age"], note=r["note"],
                    desc=r["description"] or ""))
        return list(runs.values())

    def marks(self, book_id: int) -> Dict[Tuple[str, str], bool]:
        return {(r["source"], r["ext_id"]): bool(r["counted"])
                for r in self._q("select * from marks where book_id = ?", (book_id,))}

    def set_mark(self, book_id: int, source: str, ext_id: str, counted: Optional[bool]) -> None:
        if counted is None:
            self._q("delete from marks where book_id = ? and source = ? and ext_id = ?", (book_id, source, ext_id))
        else:
            self._q("insert or replace into marks values (?, ?, ?, ?)", (book_id, source, ext_id, int(counted)))

    def manual(self, book_id: int) -> List[Offer]:
        return [Offer(source=r["source"], price=r["price"], note="вписано вручную")
                for r in self._q("select * from manual where book_id = ?", (book_id,))]

    def set_manual(self, book_id: int, source: str, price: Optional[float]) -> None:
        if price:
            self._q("insert or replace into manual values (?, ?, ?)", (book_id, source, price))
        else:
            self._q("delete from manual where book_id = ? and source = ?", (book_id, source))

    def log_price(self, book_id: int, price: Optional[int], event: str) -> None:
        self._q("insert into price_log values (?, ?, ?, ?)", (book_id, now(), price, event))

    def price_log(self, book_id: int) -> List[dict]:
        return [dict(r) for r in self._q("select at, price, event from price_log where book_id = ? order by at", (book_id,))]
