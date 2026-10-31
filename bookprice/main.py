from __future__ import annotations

import json
import logging
import logging.handlers
import subprocess
import sys
import urllib.request
from pathlib import Path

from . import __version__, paths
from .app import App, serve
from .install import first_run
from .window import close_window, open_window

PORT = 8769


def setup_logging(data_dir: Path) -> None:
    logs = data_dir / "logs"
    logs.mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(logs / "app.log", maxBytes=1_000_000, backupCount=3,
                                                   encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s")


def already_running(url: str) -> bool:
    try:
        with urllib.request.urlopen(url + "api/ping", timeout=2) as r:
            return json.load(r).get("ok", False)
    except Exception:
        return False


def main() -> None:
    data_dir = paths.data_dir()
    setup_logging(data_dir)
    log = logging.getLogger("bookprice")
    url = f"http://127.0.0.1:{PORT}/"
    profile = data_dir / "ui-profile"
    if not first_run():
        return
    if already_running(url):
        open_window(url, profile)
        return
    log.info("запуск %s из %s", __version__, Path(__file__).parent)
    app = App(data_dir)
    server = serve(app, PORT)
    if "--no-window" not in sys.argv:
        app.ui = open_window(url, profile)
    try:
        server.serve_forever()
    finally:
        app.searcher.stop()
        app.searcher.join(timeout=20)
        close_window(app.ui)
        log.info("выключено")
        if app.restart:
            own = [] if getattr(sys, "frozen", False) else ["-m", "bookprice.main"]
            subprocess.Popen([sys.executable, *own])


if __name__ == "__main__":
    main()
