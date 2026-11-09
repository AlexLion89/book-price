"""Build the program for the system it runs on: python tools/build.py [output dir].

Windows: BookPrice-<version>.zip. macOS: BookPrice-<version>-mac.dmg with Ценитель.app — built on a Mac, see
tools/mac/env.sh for a universal (Intel + Apple M) build environment.
"""
import os
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
shutil.rmtree(out / "work", ignore_errors=True)

if sys.platform == "darwin":
    app = out / "Ценитель.app"
    dmg = out / f"BookPrice-{__version__}-mac.dmg"
    stage = out / "dmg"
    shutil.rmtree(stage, ignore_errors=True)
    stage.mkdir()
    # ditto keeps the bundle's symlinks and signatures as they are.
    subprocess.run(["ditto", str(app), str(stage / app.name)], check=True)
    os.symlink("/Applications", stage / "Applications")
    dmg.unlink(missing_ok=True)
    subprocess.run(["hdiutil", "create", "-volname", "Ценитель", "-srcfolder", str(stage), "-ov", "-format", "UDZO",
                    str(dmg)], check=True)
    shutil.rmtree(stage, ignore_errors=True)
    print(f"программа {app}; образ {dmg} — {dmg.stat().st_size / 2**20:.0f} МБ")
else:
    app = out / "BookPrice"
    zip_path = out / f"BookPrice-{__version__}.zip"
    zip_path.unlink(missing_ok=True)
    with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as z:
        for f in sorted(app.rglob("*")):
            if f.is_file():
                z.write(f, Path("BookPrice") / f.relative_to(app))
    size = sum(f.stat().st_size for f in app.rglob("*") if f.is_file()) / 2**20
    print(f"папка {app} — {size:.0f} МБ; архив {zip_path} — {zip_path.stat().st_size / 2**20:.0f} МБ")
