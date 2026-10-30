"""Publish a GitHub release for the current version: python tools/release.py [--prerelease].

Needs the tag vX.Y.Z already pushed, ../dist/BookPrice-X.Y.Z.zip built and docs/releases/X.Y.Z.md written.
The token (fine-grained, Contents: write on this repository only) is read from ~/.github/book-price.token.
"""
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

root = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(root))
from bookprice import __version__  # noqa: E402
from bookprice.updater import REPO  # noqa: E402

API = f"https://api.github.com/repos/{REPO}"
TOKEN_FILE = Path(os.environ.get("BOOKPRICE_GH_TOKEN_FILE", Path.home() / ".github" / "book-price.token"))


def call(method, url, body=None, data=None, ctype="application/json"):
    token = TOKEN_FILE.read_text(encoding="utf-8-sig").strip()
    payload = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else data
    req = urllib.request.Request(url, data=payload, method=method, headers={
        "Authorization": "Bearer " + token, "Accept": "application/vnd.github+json", "Content-Type": ctype})
    with urllib.request.urlopen(req, timeout=600) as r:
        raw = r.read()
        return json.loads(raw) if raw else None


def main():
    tag = f"v{__version__}"
    notes = (root / "docs" / "releases" / f"{__version__}.md").read_text(encoding="utf-8")
    assert "\r" not in notes, "в описании релиза не должно быть CR"
    fields = {"tag_name": tag, "name": f"Цена книги {__version__}", "body": notes,
              "prerelease": "--prerelease" in sys.argv}
    try:
        release = call("GET", f"{API}/releases/tags/{tag}")
        release = call("PATCH", f"{API}/releases/{release['id']}", fields)
    except urllib.error.HTTPError as e:
        if e.code != 404:
            raise
        release = call("POST", f"{API}/releases", fields)

    assets = [(root.parent / "dist" / f"BookPrice-{__version__}.zip", "application/zip"),
              (root / "docs" / "instruction.pdf", "application/pdf")]
    existing = {a["name"]: a["id"] for a in release.get("assets", [])}
    upload = release["upload_url"].split("{")[0]
    for path, ctype in assets:
        name = "BookPrice-instruction.pdf" if path.suffix == ".pdf" else path.name
        if name in existing:
            call("DELETE", f"{API}/releases/assets/{existing[name]}")
        print(f"загружаю {name} ({path.stat().st_size / 2**20:.1f} МБ)…")
        call("POST", f"{upload}?{urllib.parse.urlencode({'name': name})}", data=path.read_bytes(), ctype=ctype)
    print("готово:", release["html_url"])


if __name__ == "__main__":
    main()
