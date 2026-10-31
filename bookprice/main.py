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
from .window import OwnedWindow, close_window, find_browser, open_window

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


def close_leftover_window(profile: Path, log: logging.Logger) -> None:
    """Called once the port is ours, so no other copy is alive: a window with our profile was left by an older
    version after an update."""
    try:
        pid = find_browser(profile)
    except Exception:
        log.exception("поиск оставшегося окна")
        return
    if pid:
        log.info("закрываю окно, оставшееся от прошлого запуска")
        OwnedWindow(pid).close()


def main() -> None:
    data_dir = paths.data_dir()
    setup_logging(data_dir)
    log = logging.getLogger("bookprice")
    url = f"http://127.0.0.1:{PORT}/"
    profile = data_dir / "ui-profile"
    if not first_run():
        return
    if already_running(url):
        open_window(url, profile, own=False)
        return
    log.info("запуск %s из %s", __version__, Path(__file__).parent)
    app = App(data_dir)
    try:
        server = serve(app, PORT)
    except OSError:
        if not already_running(url):
            raise
        log.info("другая копия запустилась одновременно с этой и сама откроет окно")
        return
    close_leftover_window(profile, log)
    if "--no-window" not in sys.argv:
        app.ui = open_window(url, profile)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.searcher.stop()
        app.searcher.join(timeout=20)
        close_window(app.ui)
        log.info("выключено")
        if app.restart:
            own = [] if getattr(sys, "frozen", False) else ["-m", "bookprice.main"]
            subprocess.Popen([sys.executable, *own])


if __name__ == "__main__":
    main()
