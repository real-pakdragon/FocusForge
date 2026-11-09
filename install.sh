#!/usr/bin/env bash
#
# Install the built FocusForge binary/app for the current user.
# Run ./build.sh first.
set -euo pipefail
cd "$(dirname "$0")"

if [ "$(uname -s)" = "Darwin" ]; then
    if [ ! -d "dist/FocusForge.app" ]; then
        echo "dist/FocusForge.app not found. Run ./build.sh first." >&2
        exit 1
    fi
    dest="${HOME}/Applications"
    mkdir -p "$dest"
    rm -rf "$dest/FocusForge.app"
    cp -R "dist/FocusForge.app" "$dest/"
    echo "Installed to $dest/FocusForge.app"
    exit 0
fi

if [ ! -f "dist/FocusForge" ]; then
    echo "dist/FocusForge not found. Run ./build.sh first." >&2
    exit 1
fi

bin="${HOME}/.local/bin"
data="${XDG_DATA_HOME:-${HOME}/.local/share}"
apps="${data}/applications"
icons="${data}/icons/hicolor/256x256/apps"

mkdir -p "$bin" "$apps" "$icons"
install -m 755 "dist/FocusForge" "$bin/focusforge"
install -m 644 "assets/logo.png" "$icons/focusforge.png"

cat >"${apps}/focusforge.desktop" <<EOF
[Desktop Entry]
Type=Application
Name=FocusForge
Comment=Deep work challenge timer
Exec=${bin}/focusforge
Icon=focusforge
Terminal=false
Categories=Utility;Office;
EOF

if command -v update-desktop-database >/dev/null 2>&1; then
    update-desktop-database "$apps" >/dev/null 2>&1 || true
fi

echo "Installed to $bin/focusforge"
echo "If '$bin' is not on your PATH, add it to your shell profile."
