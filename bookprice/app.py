from __future__ import annotations

import json
import logging
import os
import platform
import queue
import re
import threading
import time
import traceback
from dataclasses import asdict
from datetime import date
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Callable, Dict, Optional

from . import __version__, browsers, catalog, check, copymarks, report, updater
from .browser import Browser
from .system import current as system
from .sources import ratings
from .listing import ad_text, next_step
from .model import Book
from .net import Http
from .pricing import CONDITION_LABEL
from .search import SOURCES, classify, evaluate_with_dossier, run
from .store import Store, now

log = logging.getLogger(__name__)
UI = Path(__file__).parent / "ui"
CONTENT_TYPES = {".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8",
                 ".css": "text/css; charset=utf-8", ".png": "image/png", ".svg": "image/svg+xml",
                 ".jpg": "image/jpeg", ".ico": "image/x-icon"}
IDLE_EXIT = 30 * 60
BIND_TRIES = 20
UPDATE_FIRST_CHECK = 1
UPDATE_EVERY = 6 * 3600
UPDATE_RETRY = 10 * 60
UI_GONE = 5
CHECK, WINDOW_TEST = -1, -2
WINDOW_TEST_HOLD = 6
LOCAL_ORIGIN = re.compile(r"^http://(127\.0\.0\.1|localhost):\d+$")


class Searcher(threading.Thread):
    """Owns the search window: Playwright must stay on one thread."""

    def __init__(self, app: "App") -> None:
        super().__init__(daemon=True, name="searcher")
        self.app = app
        self.jobs: "queue.Queue[Optional[int]]" = queue.Queue()
        self.state: Dict[int, dict] = {}
        self.browser: Optional[Browser] = None
        self.check: dict = {"status": "idle", "lines": [], "path": ""}
        self.window_test: dict = {"status": "idle"}

    def submit(self, book_id: int) -> dict:
        job = self.state.get(book_id)
        if job and job["status"] in ("queued", "running"):
            return job
        job = {"status": "queued", "sources": {s.name: "waiting" for s in SOURCES}, "captcha": None, "error": "",
               "stage": ""}
        self.state[book_id] = job
        self.jobs.put(book_id)
        return job

    def submit_check(self, isbn: str = "") -> dict:
        if self.check["status"] not in ("queued", "running"):
            self.check = {"status": "queued", "lines": [], "path": "", "isbn": isbn}
            self.jobs.put(CHECK)
        return self.check

    def submit_window_test(self) -> dict:
        if self.window_test["status"] not in ("queued", "running"):
            self.window_test = {"status": "queued"}
            self.jobs.put(WINDOW_TEST)
        return self.window_test

    def busy(self) -> bool:
        active = ("queued", "running")
        return (self.check["status"] in active or self.window_test["status"] in active
                or any(j["status"] in active for j in self.state.values()))

    def run(self) -> None:
        while True:
            book_id = self.jobs.get()
            if book_id is None:
                break
            if book_id == CHECK:
                self._check()
                continue
            if book_id == WINDOW_TEST:
                self._window_test()
                continue
            job = self.state[book_id]
            job["status"] = "running"
            try:
                self._search(book_id, job)
                job["status"] = "done"
            except Exception as e:
                log.exception("поиск книги %s", book_id)
                job["status"], job["error"] = "error", f"{type(e).__name__}: {e}"
            if self.jobs.empty() and self.browser:
                # The search window is needed only while searching; its profile keeps cookies for next time.
                self.browser.close()
        if self.browser:
            self.browser.close()

    def _search(self, book_id: int, job: dict) -> None:
        book, _ = self.app.store.book(book_id)

        def progress(name: str, state: str) -> None:
            job["sources"][name] = state
            job["captcha"] = None

        def captcha(name: str) -> None:
            job["captcha"] = name

        if self.browser is None:
            home = f"http://127.0.0.1:{self.app.port}/search-window.html" if self.app.port else ""
            self.browser = Browser(self.app.data_dir, on_captcha=captcha, home=home)
        self.browser.on_captcha = captcha
        only = [s for s in os.environ.get("BOOKPRICE_ONLY", "").split(",") if s] or None
        if not book.facts:
            job["stage"] = "Собираю досье: FantLab и Читай-город…"
            book.facts = catalog.facts(self.app.http, book)
            self.app.store.set_facts(book_id, book.facts)
        if "ratings_checked" not in book.facts and (not only or "ratings" in only):
            # Reader ratings change slowly and cost two page loads per site: once per book is enough.
            job["stage"] = "Собираю досье: оценки читателей на LiveLib и ЛитРес…"
            book.facts.update(ratings.collect(self.browser, book))
            book.facts["ratings_checked"] = date.today().isoformat()
            self.app.store.set_facts(book_id, book.facts)
        job["stage"] = ""
        results = run(book, self.app.http, self.browser, progress, only)
        if any("closed" in (r.error or "").lower() for r in results):
            log.warning("окно поиска закрыли — открываю заново и повторяю")
            self.browser.close()
            retry = [r.source for r in results if "closed" in (r.error or "").lower()]
            results = [r for r in results if r.source not in retry] + run(book, self.app.http, self.browser, progress, retry)
        self.app.store.save_results(book_id, results)

    def _check(self) -> None:
        state = self.check
        state["status"] = "running"
        try:
            path = check.run_check(self.app.data_dir, state["lines"].append, state.get("isbn") or None)
            state["path"], state["status"] = str(path), "done"
        except Exception as e:
            log.exception("проверка площадок")
            state["lines"].append(f"Сбой: {type(e).__name__}: {e}")
            state["status"] = "error"

    def _window_test(self) -> None:
        """The search window on our own page only — no site is visited: shows that the browser can be driven."""
        state = self.window_test
        state["status"] = "running"
        home = f"http://127.0.0.1:{self.app.port}/search-window.html"
        browser = Browser(self.app.data_dir, home=home)
        try:
            browser.start()
            state["title"] = browser.page.title()
            state["browser"] = browser.found.label
            time.sleep(WINDOW_TEST_HOLD)
            state["status"] = "done"
        except Exception as e:
            log.exception("проверка окна поиска")
            state["status"], state["error"] = "error", f"{type(e).__name__}: {e}"
        finally:
            browser.close()

    def stop(self) -> None:
        self.jobs.put(None)


class App:
    def __init__(self, data_dir: Path) -> None:
        self.data_dir = data_dir
        self.store = Store(data_dir / "books.sqlite")
        self.http = Http()
        self.searcher = Searcher(self)
        self.last_seen = time.monotonic()
        self.server: Optional[ThreadingHTTPServer] = None
        self.port = 0
        self.restart = False
        self.ui = None
        self.ui_closed_at: Optional[float] = None
        self.update_info: Optional[dict] = None
        self.update_checked = False

    def book_view(self, book_id: int) -> dict:
        book, row = self.store.book(book_id)
        results = self.store.results(book_id)
        found = classify(book, results, self.store.marks(book_id))
        manual = self.store.manual(book_id)
        marks = json.loads(row.get("copy_marks") or "[]")
        verdict, dossier = evaluate_with_dossier(book, found, manual, row["condition"], self.store.sold_like(book_id, book),
                                                 marks)
        return {
            "book": {**row, **book.to_dict()},
            "conditions": CONDITION_LABEL,
            "sources": [{"name": s.name, "label": s.label, "kind": s.kind} for s in SOURCES],
            "runs": {r.source: {"search_url": r.search_url, "error": r.error, "count": len(r.offers)} for r in results},
            "found": [f.to_dict() for f in sorted(found, key=lambda f: (not f.counted, f.offer.price))],
            "manual": {o.source: o.price for o in manual},
            "verdict": {**asdict(verdict), "schedule": verdict.schedule()},
            "dossier": dossier.to_dict(),
            "next_step": next_step(row["listed_price"], row["price_changed_at"], verdict.floor)
                         if row["status"] == "listed" else None,
            "ad_text": ad_text(book, row["condition"], marks),
            "copy_marks": marks,
            "copy_mark_options": [{"key": m.key, "label": m.label, "effect": m.effect} for m in copymarks.MARKS],
            "job": self.searcher.state.get(book_id),
            "price_log": self.store.price_log(book_id),
        }

    def books_view(self) -> list:
        items = []
        for row in self.store.books():
            item = {k: row[k] for k in ("id", "title", "author", "year", "cover_url", "status", "listed_price",
                                        "sold_price", "searched_at", "condition")}
            if row["status"] == "listed":
                try:
                    view = self.book_view(row["id"])
                    item["next_step"] = view["next_step"]
                except Exception:
                    log.exception("книга %s", row["id"])
            items.append(item)
        return items

    def list_price(self, book_id: int, price: int, event: str) -> None:
        self.store.update(book_id, status="listed", listed_price=price, price_changed_at=now())
        self.store.log_price(book_id, price, event)

    def quit(self) -> None:
        self.searcher.stop()
        if self.server:
            threading.Thread(target=self.server.shutdown, daemon=True).start()


def make_handler(app: App) -> Callable:
    routes = []

    def route(method: str, pattern: str):
        def deco(fn):
            routes.append((method, re.compile(f"^{pattern}$"), fn))
            return fn
        return deco

    @route("GET", "/api/ping")
    def ping(body):
        return {"ok": True, "version": __version__, "busy": app.searcher.busy()}

    @route("GET", "/api/system")
    def system_info(body):
        found = browsers.find()
        return {"os": system.NAME, "os_label": system.LABEL, "machine": platform.machine(), "outbox": system.OUTBOX_WHERE,
                "browser": found.label if found else None, "no_browser": browsers.NO_BROWSER,
                "downloads": browsers.DOWNLOADS}

    @route("GET", "/api/books")
    def books(body):
        return app.books_view()

    @route("POST", "/api/lookup")
    def lookup(body):
        book = catalog.identify(app.http, body.get("isbn", ""))
        return {"book": book.to_dict() if book else None}

    @route("POST", "/api/find")
    def find(body):
        return {"books": [b.to_dict() for b in catalog.find(app.http, body.get("title", ""), body.get("author", ""))]}

    @route("POST", "/api/books")
    def add(body):
        data = body.get("book") or {}
        book = Book(**{k: v for k, v in data.items() if k in Book.__dataclass_fields__})
        if not book.title:
            raise ValueError("нужно название книги")
        book = catalog.enrich(app.http, book)
        book_id = app.store.add_book(book, body.get("condition", "excellent"))
        app.searcher.submit(book_id)
        return {"id": book_id}

    @route("GET", r"/api/books/(\d+)")
    def get_book(body, book_id):
        return app.book_view(int(book_id))

    @route("POST", r"/api/books/(\d+)")
    def update(body, book_id):
        app.store.update(int(book_id), **body)
        return app.book_view(int(book_id))

    @route("DELETE", r"/api/books/(\d+)")
    def delete(body, book_id):
        app.store.delete(int(book_id))
        return {"ok": True}

    @route("POST", r"/api/books/(\d+)/search")
    def search(body, book_id):
        return app.searcher.submit(int(book_id))

    @route("POST", r"/api/books/(\d+)/mark")
    def mark(body, book_id):
        app.store.set_mark(int(book_id), body["source"], body["ext_id"], body.get("counted"))
        return app.book_view(int(book_id))

    @route("POST", r"/api/books/(\d+)/manual")
    def manual(body, book_id):
        price = body.get("price")
        app.store.set_manual(int(book_id), body["source"], float(price) if price else None)
        return app.book_view(int(book_id))

    @route("POST", r"/api/books/(\d+)/listed")
    def listed(body, book_id):
        app.list_price(int(book_id), int(body["price"]), body.get("event", "listed"))
        return app.book_view(int(book_id))

    @route("POST", r"/api/books/(\d+)/sold")
    def sold(body, book_id):
        price = int(body["price"]) if body.get("price") else None
        app.store.update(int(book_id), status="sold", sold_price=price, sold_at=now())
        app.store.log_price(int(book_id), price, "sold")
        return app.book_view(int(book_id))

    @route("POST", "/api/check")
    def start_check(body):
        return app.searcher.submit_check(body.get("isbn", ""))

    @route("GET", "/api/check")
    def check_state(body):
        return app.searcher.check

    @route("POST", "/api/window-test")
    def start_window_test(body):
        return app.searcher.submit_window_test()

    @route("GET", "/api/window-test")
    def window_test_state(body):
        return app.searcher.window_test

    @route("POST", "/api/report")
    def make_report(body):
        return {"path": str(report.build(app.data_dir)), "where": system.OUTBOX_WHERE}

    @route("POST", "/api/update")
    def update_app(body):
        return updater.check_and_download(app.http, app.data_dir)

    @route("GET", "/api/update-status")
    def update_status(body):
        return {"version": __version__, "available": app.update_info, "checked": app.update_checked,
                "busy": app.searcher.busy()}

    @route("POST", "/api/quit")
    def quit_app(body):
        app.quit()
        return {"ok": True}

    @route("POST", "/api/closed")
    def ui_closed(body):
        app.ui_closed_at = time.monotonic()
        return {"ok": True}

    @route("POST", "/api/restart")
    def restart_app(body):
        app.restart = True
        app.quit()
        return {"ok": True}

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, fmt, *args):
            log.debug("http: " + fmt, *args)

        def _send(self, code: int, payload: bytes, ctype: str) -> None:
            self.send_response(code)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-store")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)

        def _json(self, code: int, data) -> None:
            self._send(code, json.dumps(data, ensure_ascii=False).encode("utf-8"), "application/json; charset=utf-8")

        def _dispatch(self, method: str) -> None:
            app.last_seen = time.monotonic()
            path = self.path.split("?")[0]
            if method == "GET" and not path.startswith("/api/"):
                return self._static(path)
            for m, pattern, fn in routes:
                hit = pattern.match(path)
                if m == method and hit:
                    try:
                        length = int(self.headers.get("Content-Length") or 0)
                        body = json.loads(self.rfile.read(length) or b"{}") if length else {}
                        return self._json(200, fn(body, *hit.groups()))
                    except (ValueError, KeyError) as e:
                        return self._json(400, {"error": str(e)})
                    except ConnectionError:
                        # The window went away (closed, reloaded) before the answer was written — nothing to report.
                        return None
                    except Exception as e:
                        log.error("%s %s: %s", method, path, traceback.format_exc())
                        return self._json(500, {"error": f"{type(e).__name__}: {e}"})
            self._json(404, {"error": "нет такого адреса"})

        def _static(self, path: str) -> None:
            name = "index.html" if path in ("", "/") else path.lstrip("/")
            target = (UI / name).resolve()
            if UI.resolve() not in target.parents or not target.is_file():
                return self._send(404, b"not found", "text/plain")
            self._send(200, target.read_bytes(), CONTENT_TYPES.get(target.suffix, "application/octet-stream"))

        def _foreign(self) -> bool:
            # Only the page served by this app may change data: other sites open in the same browser must not.
            origin = self.headers.get("Origin") or ""
            return bool(origin) and not LOCAL_ORIGIN.match(origin)

        def do_GET(self):
            self._dispatch("GET")

        def do_POST(self):
            if self._foreign():
                return self._json(403, {"error": "чужой сайт"})
            self._dispatch("POST")

        def do_DELETE(self):
            if self._foreign():
                return self._json(403, {"error": "чужой сайт"})
            self._dispatch("DELETE")

    return Handler


class Server(ThreadingHTTPServer):
    allow_reuse_address = system.REUSE_ADDRESS


def serve(app: App, port: int) -> ThreadingHTTPServer:
    # After an update the old copy may still be letting go of the port for a moment.
    for attempt in range(BIND_TRIES):
        try:
            server = Server(("127.0.0.1", port), make_handler(app))
            break
        except OSError:
            if attempt == BIND_TRIES - 1:
                raise
            time.sleep(0.5)
    app.server = server
    app.port = port
    app.searcher.start()

    def watchdog() -> None:
        while True:
            time.sleep(2)
            if app.searcher.busy():
                continue
            now = time.monotonic()
            # Our window is our own browser process: it ends when the window is closed. The page's own goodbye is a
            # fallback — the browser often exits before sending it; a reload asks for the page again and cancels it.
            window_gone = app.ui is not None and not app.ui.alive()
            closed_at = app.ui_closed_at
            closed = closed_at is not None and app.last_seen <= closed_at + 0.5 and now - closed_at > UI_GONE
            if window_gone or closed or now - app.last_seen > IDLE_EXIT:
                log.info("окно программы закрыто — выключаюсь")
                app.quit()
                return

    threading.Thread(target=watchdog, daemon=True, name="watchdog").start()

    def look_for_updates() -> None:
        time.sleep(UPDATE_FIRST_CHECK)
        while True:
            try:
                app.update_info = updater.available(app.http)
                app.update_checked = True
                if app.update_info:
                    log.info("вышла версия %s", app.update_info["version"])
                pause = UPDATE_EVERY
            except Exception as e:
                log.info("обновления не проверены: %s", e)
                pause = UPDATE_RETRY
            time.sleep(pause)

    threading.Thread(target=look_for_updates, daemon=True, name="updates").start()
    return server
