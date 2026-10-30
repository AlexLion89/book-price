"""Updates of the pure-Python part: new tags of the public repository are unpacked next to the user data.

The launcher (run.py) puts the newest compatible unpacked version first on sys.path.
"""
from __future__ import annotations

import io
import logging
import re
import zipfile
from pathlib import Path
from typing import Optional, Tuple

from . import __version__
from .net import Http

log = logging.getLogger(__name__)

REPO = "AlexLion89/book-price"
TAGS = f"https://api.github.com/repos/{REPO}/tags"
ZIP = "https://codeload.github.com/" + REPO + "/zip/refs/tags/{tag}"


def parse(version: str) -> Optional[Tuple[int, ...]]:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", version.strip())
    return tuple(int(x) for x in m.groups()) if m else None


def updates_dir(data_dir: Path) -> Path:
    return data_dir / "updates"


def latest_tag(http: Http) -> Optional[str]:
    tags = [t["name"] for t in http.json(TAGS) if parse(t["name"])]
    return max(tags, key=parse) if tags else None


def check_and_download(http: Http, data_dir: Path) -> dict:
    try:
        tag = latest_tag(http)
    except Exception as e:
        log.exception("проверка обновлений")
        return {"updated": False, "error": f"не удалось проверить: {e}"}
    if not tag or parse(tag) <= parse(__version__):
        return {"updated": False, "version": __version__}
    version = ".".join(map(str, parse(tag)))
    target = updates_dir(data_dir) / version
    if not (target / "bookprice" / "__init__.py").exists():
        raw = http.get(ZIP.format(tag=tag))
        with zipfile.ZipFile(io.BytesIO(raw)) as z:
            for name in z.namelist():
                parts = name.split("/", 1)
                if len(parts) == 2 and parts[1].startswith("bookprice/") and not name.endswith("/"):
                    out = target / parts[1]
                    out.parent.mkdir(parents=True, exist_ok=True)
                    out.write_bytes(z.read(name))
        log.info("скачано обновление %s", version)
    return {"updated": True, "version": version, "restart": True}
