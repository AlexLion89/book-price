# PyInstaller spec: python tools/build.py
from pathlib import Path

root = Path(SPECPATH)

a = Analysis(
    [str(root / "run.py")],
    pathex=[str(root)],
    datas=[(str(root / "bookprice"), "bookprice")],
    excludes=["tkinter"],
)
# bookprice ships as plain files next to the exe, not inside the archive: then a downloaded update
# placed earlier on sys.path really replaces it. Its dependencies stay bundled.
a.pure = [m for m in a.pure if not m[0].startswith("bookprice")]
a.datas = [d for d in a.datas if "__pycache__" not in d[0]]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name="BookPrice", console=False)
coll = COLLECT(exe, a.binaries, a.datas, name="BookPrice")
