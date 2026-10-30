"""Build the Windows program: python tools/build.py [output dir]. Result: BookPrice-<version>.zip."""
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

root = Path(__file__).resolve().parent.parent
out = Path(sys.argv[1]).resolve() if len(sys.argv) > 1 else root.parent / "dist"
sys.path.insert(0, str(root))
from bookprice import __version__  # noqa: E402

subprocess.run([sys.executable, "-m", "PyInstaller", "--noconfirm", "--clean",
                "--distpath", str(out), "--workpath", str(out / "work"), str(root / "bookprice.spec")], check=True)
app = out / "BookPrice"
zip_path = out / f"BookPrice-{__version__}.zip"
zip_path.unlink(missing_ok=True)
with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
    for f in sorted(app.rglob("*")):
        if f.is_file():
            z.write(f, Path("BookPrice") / f.relative_to(app))
shutil.rmtree(out / "work", ignore_errors=True)
size = sum(f.stat().st_size for f in app.rglob("*") if f.is_file()) / 2**20
print(f"папка {app} — {size:.0f} МБ; архив {zip_path} — {zip_path.stat().st_size / 2**20:.0f} МБ")
