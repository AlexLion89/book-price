from __future__ import annotations

import json
import logging
import logging.handlers
import os
import subprocess
import sys
import urllib.request
import webbrowser
from pathlib import Path

from . import __version__, paths
from .app import App, serve
from .install import first_run

PORT = 8769
EDGE = [
    Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")) / "Microsoft/Edge/Application/msedge.exe",
    Path(os.environ.get("ProgramFiles", r"C:\Program Files")) / "Microsoft/Edge/Application/msedge.exe",
]


def setup_logging(data_dir: Path) -> None:
    logs = data_dir / "logs"
    logs.mkdir(exist_ok=True)
    handler = logging.handlers.RotatingFileHandler(logs / "app.log", maxBytes=1_000_000, backupCount=3,
                                                   encoding="utf-8")
    logging.basicConfig(level=logging.INFO, handlers=[handler],
                        format="%(asctime)s %(levelname)s %(threadName)s %(name)s: %(message)s")


def open_window(url: str) -> None:
    """Edge in app mode looks like a program window: no tabs, no address bar."""
    edge = next((p for p in EDGE if p.is_file()), None)
    if edge:
        subprocess.Popen([str(edge), f"--app={url}", "--window-size=1150,900"])
    else:
        webbrowser.open(url)


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
    if not first_run():
        return
    if already_running(url):
        open_window(url)
        return
    log.info("запуск %s из %s", __version__, Path(__file__).parent)
    app = App(data_dir)
    server = serve(app, PORT)
    if "--no-window" not in sys.argv:
        open_window(url)
    try:
        server.serve_forever()
    finally:
        app.searcher.stop()
        app.searcher.join(timeout=20)
        log.info("выключено")
        if app.restart:
            # The old window reloads itself; the new process must not open a second one.
            own = [] if getattr(sys, "frozen", False) else ["-m", "bookprice.main"]
            subprocess.Popen([sys.executable, *own, "--no-window"])


if __name__ == "__main__":
    main()
