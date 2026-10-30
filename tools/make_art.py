"""Prepare UI pictures from the originals: python tools/make_art.py <folder with fox-*.jpg|png>

Writes bookprice/ui/img/: hero.jpg, fox-64.png, fox-192.png, fox.ico and, when present, search.png.
Resizing runs in Edge's canvas — no imaging library is bundled with the program.
"""
import base64
import struct
import sys
from pathlib import Path

root = Path(__file__).resolve().parent.parent
OUT = root / "bookprice" / "ui" / "img"
BG = "#1E2736"
# The icon original has a noisy, not transparent background and coloured streaks at its sides:
# a square around the face and the book avoids the streaks.
ICON_CROP = (95, 40, 1070)
ICO_SIZES = [256, 128, 64, 48, 32, 24, 16]

RENDER = r"""
async ({src, crop, size, bg, round, type, quality}) => {
  const img = new Image(); img.src = src; await img.decode();
  const [x, y, w, h] = crop || [0, 0, img.width, img.height];
  const W = size ? size : w, H = size ? Math.round(size * h / w) : h;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d'); g.imageSmoothingQuality = 'high';
  if (round) { g.beginPath(); g.roundRect(0, 0, W, H, W * round); g.clip(); }
  if (bg) { g.fillStyle = bg; g.fillRect(0, 0, W, H); }
  g.drawImage(img, x, y, w, h, 0, 0, W, H);
  return c.toDataURL(type || 'image/png', quality || 0.9);
}
"""


def data_url(path: Path) -> str:
    kind = "png" if path.suffix.lower() == ".png" else "jpeg"
    return f"data:image/{kind};base64," + base64.b64encode(path.read_bytes()).decode()


def decode(url: str) -> bytes:
    return base64.b64decode(url.split(",", 1)[1])


def ico(pngs: dict) -> bytes:
    """ICO with PNG-compressed entries (Windows Vista+ reads them)."""
    sizes = sorted(pngs, reverse=True)
    head = struct.pack("<HHH", 0, 1, len(sizes))
    offset = 6 + 16 * len(sizes)
    entries, blobs = b"", b""
    for s in sizes:
        blob = pngs[s]
        entries += struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(blob), offset + len(blobs))
        blobs += blob
    return head + entries + blobs


def find(folder: Path, stem: str):
    return next((p for p in (folder / f"{stem}.png", folder / f"{stem}.jpg") if p.exists()), None)


def main(folder: Path) -> None:
    from playwright.sync_api import sync_playwright
    OUT.mkdir(parents=True, exist_ok=True)
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="msedge", headless=True)
        page = browser.new_page()
        render = lambda path, **kw: decode(page.evaluate(RENDER, {"src": data_url(path), **kw}))

        hero = find(folder, "fox-hero")
        (OUT / "hero.jpg").write_bytes(render(hero, size=1280, type="image/jpeg", quality=0.86))

        icon = find(folder, "fox-icon")
        crop = [ICON_CROP[0], ICON_CROP[1], ICON_CROP[2], ICON_CROP[2]]
        pngs = {s: render(icon, crop=crop, size=s, bg=BG, round=0.18) for s in ICO_SIZES}
        (OUT / "fox.ico").write_bytes(ico(pngs))
        (OUT / "fox-64.png").write_bytes(pngs[64])
        (OUT / "fox-192.png").write_bytes(render(icon, crop=crop, size=192, bg=BG, round=0.18))

        search = find(folder, "fox-search-solid")
        if search:
            (OUT / "search.png").write_bytes(render(search, size=480))
        browser.close()
    for f in sorted(OUT.iterdir()):
        print(f"{f.name}: {f.stat().st_size // 1024} КБ")


if __name__ == "__main__":
    main(Path(sys.argv[1]))
