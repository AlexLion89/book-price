"""Updates of the pure-Python part: the latest published release of the public repository is unpacked next to
the user data. Only published releases count, not bare tags: a tag is pushed before the version is checked.

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
LATEST = f"https://api.github.com/repos/{REPO}/releases/latest"
ZIP = "https://codeload.github.com/" + REPO + "/zip/refs/tags/{tag}"
MARKUP = re.compile(r"[*_`#>|]")


def parse(version: str) -> Optional[Tuple[int, ...]]:
    m = re.fullmatch(r"v?(\d+)\.(\d+)\.(\d+)", (version or "").strip())
    return tuple(int(x) for x in m.groups()) if m else None


def updates_dir(data_dir: Path) -> Path:
    return data_dir / "updates"


def summary(notes: str, limit: int = 160) -> str:
    """The first paragraph of the release notes, without markdown — for a one-line banner."""
    first = next((p for p in re.split(r"\n\s*\n", notes or "") if p.strip()), "")
    text = " ".join(MARKUP.sub("", first).split())
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + "…"


def available(http: Http) -> Optional[dict]:
    d = http.json(LATEST)
    tag = d.get("tag_name") or ""
    if not parse(tag) or parse(tag) <= parse(__version__):
        return None
    return {"tag": tag, "version": ".".join(map(str, parse(tag))), "summary": summary(d.get("body") or ""),
            "url": d.get("html_url") or ""}


def download(http: Http, data_dir: Path, tag: str) -> str:
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
    return version


def check_and_download(http: Http, data_dir: Path) -> dict:
    try:
        release = available(http)
    except Exception as e:
        log.exception("проверка обновлений")
        return {"updated": False, "error": f"не удалось проверить: {e}"}
    if not release:
        return {"updated": False, "version": __version__}
    return {"updated": True, "version": download(http, data_dir, release["tag"]), "restart": True}
