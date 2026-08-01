#!/bin/bash
# Build P4wnP1 Tool Installer as a standalone executable (Linux / macOS).
# Output: dist/P4wnP1_Installer
#
# Requirements: pip3 install pyinstaller (plus the app's own requirements)
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[*] Installing dependencies..."
pip3 install -r requirements.txt --quiet
pip3 install pyinstaller --quiet

echo "[*] Building executable..."
pyinstaller p4wnp1_installer.spec --clean --noconfirm

echo ""
echo "[✓] Build complete: dist/P4wnP1_Installer"
echo "    Run:  ./dist/P4wnP1_Installer"
echo ""

# Optional: build AppImage on Linux
if command -v appimagetool &>/dev/null && [[ "$(uname)" == "Linux" ]]; then
    echo "[*] Packaging AppImage..."
    APPDIR="dist/P4wnP1_Installer.AppDir"
    mkdir -p "$APPDIR/usr/bin"
    cp dist/P4wnP1_Installer "$APPDIR/usr/bin/"

    cat > "$APPDIR/P4wnP1_Installer.desktop" << 'DESKTOP'
[Desktop Entry]
Name=P4wnP1 Tool Installer
Exec=P4wnP1_Installer
Icon=p4wnp1
Type=Application
Categories=Network;Security;
DESKTOP

    cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
exec "$(dirname "$0")/usr/bin/P4wnP1_Installer" "$@"
APPRUN
    chmod +x "$APPDIR/AppRun"

    ARCH=x86_64 appimagetool "$APPDIR" dist/P4wnP1_Installer-x86_64.AppImage
    echo "[✓] AppImage: dist/P4wnP1_Installer-x86_64.AppImage"
fi
