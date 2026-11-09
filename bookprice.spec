# PyInstaller spec: python tools/build.py. Windows — a folder with BookPrice.exe; macOS — Ценитель.app.
import os
import re
import sys
from pathlib import Path

root = Path(SPECPATH)
mac = sys.platform == "darwin"
version = re.search(r'__version__ = "([^"]+)"', (root / "bookprice" / "__init__.py").read_text(encoding="utf-8")).group(1)

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    datas=[(str(root / "bookprice"), "bookprice")],
    # Updates bring only code and run on the modules of the build the user once installed: a few standard modules
    # that later versions may want are packed in advance (ctypes.wintypes was missing from early Windows builds).
    hiddenimports=["ctypes.wintypes", "ctypes.util", "plistlib", "uuid", "csv", "html.parser", "xml.etree.ElementTree"],
    excludes=["tkinter"],
)
# bookprice ships as plain files next to the program, not inside the archive: then a downloaded update
# placed earlier on sys.path really replaces it. Its dependencies stay bundled.
a.pure = [m for m in a.pure if not m[0].startswith("bookprice")]
a.datas = [d for d in a.datas if "__pycache__" not in d[0]]

pyz = PYZ(a.pure)
if mac:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BookPrice", console=False,
              target_arch=os.environ.get("BP_TARGET_ARCH") or None, codesign_identity=None, argv_emulation=False)
    coll = COLLECT(exe, a.binaries, a.datas, name="BookPrice")
    app = BUNDLE(
        coll, name="Ценитель.app", icon=str(root / "tools" / "mac" / "fox.icns"),
        bundle_identifier="io.github.alexlion89.bookprice", version=version,
        info_plist={
            "CFBundleDisplayName": "Ценитель",
            "CFBundleName": "Ценитель",
            "CFBundleShortVersionString": version,
            "CFBundleVersion": version,
            # The program's window is a browser window: no Dock icon or menu of its own, which would only hang there
            # unanswered — the program speaks no Apple events.
            "LSUIElement": True,
            "LSMinimumSystemVersion": "11.0",
            "NSHighResolutionCapable": True,
        },
    )
else:
    exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BookPrice", console=False,
              icon=str(root / "bookprice" / "ui" / "img" / "fox.ico"))
    coll = COLLECT(exe, a.binaries, a.datas, name="BookPrice")
