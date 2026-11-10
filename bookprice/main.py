from __future__ import annotations

import json
import logging
import logging.handlers
import subprocess
import sys
import threading
import urllib.request
from pathlib import Path

from . import __version__, paths
from .app import App, serve
from .system import current as system
from .window import close_window, leftover_windows, open_window

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


def close_leftover_window(data_dir: Path, log: logging.Logger) -> None:
    """Called once the port is ours, so no other copy is alive: a window with our profile was left by an older
    version after an update."""
    try:
        for window in leftover_windows(data_dir):
            log.info("закрываю окно, оставшееся от прошлого запуска")
            window.close()
    except Exception:
        log.exception("окно от прошлого запуска не закрылось")


def main() -> None:
    data_dir = paths.data_dir()
    setup_logging(data_dir)
    log = logging.getLogger("bookprice")
    url = f"http://127.0.0.1:{PORT}/"
    if not system.first_run():
        return
    if already_running(url):
        open_window(url, data_dir, own=False)
        return
    log.info("запуск %s (%s) из %s", __version__, system.LABEL, Path(__file__).parent)
    app = App(data_dir)
    try:
        server = serve(app, PORT)
    except OSError:
        if not already_running(url):
            raise
        log.info("другая копия запустилась одновременно с этой и сама откроет окно")
        return
    close_leftover_window(data_dir, log)
    if "--no-window" not in sys.argv:
        # A slow machine takes a while to start the browser; the page must be served meanwhile, so the window is
        # looked for alongside.
        def attach() -> None:
            app.ui = open_window(url, data_dir)

        threading.Thread(target=attach, daemon=True, name="window").start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        app.searcher.stop()
        app.searcher.join(timeout=20)
        if app.ui is not None:
            close_window(app.ui)
        else:
            # Quit before the window was found: any window on our profile is this copy's — only one copy runs.
            close_leftover_window(data_dir, log)
        log.info("выключено")
        if app.restart:
            own = [] if getattr(sys, "frozen", False) else ["-m", "bookprice.main"]
            subprocess.Popen([sys.executable, *own])


if __name__ == "__main__":
    main()
