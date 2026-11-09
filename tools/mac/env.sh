#!/bin/bash
# A build environment for the universal macOS program (Intel and Apple M in one Ценитель.app): bash tools/mac/env.sh
# Creates .venv-mac next to the repository and prints its python. Needs sudo once, for the python.org installer.
#
# Every binary in the bundle must carry both architectures. python.org's Python and the greenlet and PyInstaller
# wheels do; Playwright's "universal2" wheel does not — its node is Intel-only (on Apple M it would need Rosetta,
# which is not installed by default). So node is glued together from the Intel and the Apple M wheels with lipo.
set -euo pipefail

PY_VERSION=3.9.13
PLAYWRIGHT=1.60.0
GREENLET=3.2.4
PYINSTALLER=6.22.3
HOOKS=2026.9

here="$(cd "$(dirname "$0")/../.." && pwd)"
venv="$here/../.venv-mac"
work="$(mktemp -d)"
framework=/Library/Frameworks/Python.framework/Versions/3.9/bin/python3.9

if [ ! -x "$framework" ]; then
  curl -fsSL -o "$work/python.pkg" "https://www.python.org/ftp/python/$PY_VERSION/python-$PY_VERSION-macos11.pkg"
  sudo installer -pkg "$work/python.pkg" -target /
fi
lipo -info "$framework"

"$framework" -m venv "$venv"
py="$venv/bin/python"
"$py" -m pip install --quiet --upgrade pip

dl() { "$py" -m pip download --quiet --no-deps --only-binary=:all: --python-version 3.9 --implementation cp "$@"; }
dl --platform macosx_11_0_universal2 -d "$work/u2" "greenlet==$GREENLET"
dl --platform macosx_10_13_universal2 -d "$work/u2" "pyinstaller==$PYINSTALLER"
dl --platform macosx_11_0_arm64 -d "$work/arm64" "playwright==$PLAYWRIGHT"
dl --platform macosx_10_13_x86_64 -d "$work/x86_64" "playwright==$PLAYWRIGHT"

"$py" -m pip install --quiet "$work"/u2/*.whl
"$py" -m pip install --quiet "$work"/arm64/playwright-*.whl "pyinstaller-hooks-contrib==$HOOKS"

node="$("$py" -c 'import os, playwright; print(os.path.join(os.path.dirname(playwright.__file__), "driver", "node"))')"
(cd "$work" && unzip -q -o x86_64/playwright-*.whl playwright/driver/node -d x86_64/unpacked)
lipo -create "$node" "$work/x86_64/unpacked/playwright/driver/node" -output "$work/node"
chmod +x "$work/node"
mv "$work/node" "$node"
lipo -info "$node"
"$py" -c 'import greenlet, playwright; print("greenlet", greenlet.__version__)'
for so in $(find "$venv/lib/python3.9/site-packages/greenlet" -name '*.so'); do lipo -info "$so"; done
echo "$py"
