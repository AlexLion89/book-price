"""Updates of the pure-Python part: the newest published release for this system is unpacked next to the user data.
Only published releases count, not bare tags: a tag is pushed before the version is checked.

Windows and macOS share one code and one line of versions. A release notes line «Система: …» says whom a release
is for: a fix that only matters on one system is not offered on the other, and the next common release brings it along
(on the other system that code simply never runs). No such line — the release is for everyone.

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
from .system import current as system

log = logging.getLogger(__name__)

REPO = "AlexLion89/book-price"
RELEASES = f"https://api.github.com/repos/{REPO}/releases?per_page=30"
ZIP = "https://codeload.github.com/" + REPO + "/zip/refs/tags/{tag}"
MARKUP = re.compile(r"[*_`#>|]")
TARGET = re.compile(r"^[\s*_]*Система:[\s*_]*(.+)$", re.M | re.I)
SYSTEM_WORDS = {"windows": "windows", "mac": "macos"}


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


def meant_for(notes: str, system_name: str) -> bool:
    found = TARGET.search(notes or "")
    return not found or SYSTEM_WORDS[system_name] in found.group(1).lower()


def newest(releases: list, system_name: str, current: str) -> Optional[dict]:
    fit = [r for r in releases if not r.get("draft") and not r.get("prerelease") and parse(r.get("tag_name") or "")
           and meant_for(r.get("body") or "", system_name)]
    best = max(fit, key=lambda r: parse(r["tag_name"]), default=None)
    if not best or parse(best["tag_name"]) <= parse(current):
        return None
    return {"tag": best["tag_name"], "version": ".".join(map(str, parse(best["tag_name"]))),
            "summary": summary(best.get("body") or ""), "url": best.get("html_url") or ""}


def available(http: Http) -> Optional[dict]:
    return newest(http.json(RELEASES), system.NAME, __version__)


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
