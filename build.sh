#!/usr/bin/env bash
#
# Build FocusForge on Linux or macOS.
#
#   ./build.sh
#
# Produces a self-contained executable in dist/ (Linux) or a .app bundle
# (macOS). Requires Python 3.10+ with tkinter and Pillow; PyInstaller is
# installed automatically if it is missing.
set -euo pipefail
cd "$(dirname "$0")"

PYTHON="${PYTHON:-python3}"

if ! "$PYTHON" -c "import tkinter" >/dev/null 2>&1; then
    echo "tkinter is required. Debian/Ubuntu: sudo apt install python3-tk; Fedora: sudo dnf install python3-tkinter" >&2
    exit 1
fi

if ! "$PYTHON" -c "import PIL" >/dev/null 2>&1; then
    echo "Pillow is required. Install it with: $PYTHON -m pip install pillow" >&2
    exit 1
fi

if ! "$PYTHON" -c "import PyInstaller" >/dev/null 2>&1; then
    echo "==> Installing PyInstaller"
    "$PYTHON" -m pip install --upgrade pyinstaller
fi

echo "==> Generating icon"
"$PYTHON" tools/make_icon.py

echo "==> Running smoke test"
if [ -z "${DISPLAY:-}" ] && [ "$(uname -s)" = "Linux" ] && command -v xvfb-run >/dev/null 2>&1; then
    xvfb-run -a "$PYTHON" tests/smoke_test.py
else
    "$PYTHON" tests/smoke_test.py
fi

echo "==> Building executable"
"$PYTHON" -m PyInstaller \
    --noconfirm \
    --clean \
    --onefile \
    --windowed \
    --name FocusForge \
    --add-data "assets/icon.ico:assets" \
    --add-data "assets/logo.png:assets" \
    src/app.py

if [ "$(uname -s)" = "Darwin" ]; then
    echo "==> Built dist/FocusForge.app"
else
    echo "==> Built dist/FocusForge"
fi
