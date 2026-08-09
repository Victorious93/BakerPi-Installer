#!/bin/bash
# Build BakerPi Tool Installer as a standalone executable (Linux / macOS).
# Output: dist/BakerPi_Installer
#
# Requirements: pip3 install pyinstaller (plus the app's own requirements)
# Linux also needs the WebKit/GTK dev headers:
#   sudo apt-get install libwebkit2gtk-4.0-dev libgtk-3-dev libglib2.0-dev
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "[*] Installing dependencies..."
pip3 install -r requirements.txt --quiet
pip3 install pyinstaller --quiet

echo "[*] Building executable..."
pyinstaller bakerpi_installer.spec --clean --noconfirm

echo ""
echo "[✓] Build complete: dist/BakerPi_Installer"
echo "    Run:  ./dist/BakerPi_Installer"
echo ""

# Optional: build AppImage on Linux
if command -v appimagetool &>/dev/null && [[ "$(uname)" == "Linux" ]]; then
    echo "[*] Packaging AppImage..."
    APPDIR="dist/BakerPi_Installer.AppDir"
    mkdir -p "$APPDIR/usr/bin"
    cp dist/BakerPi_Installer "$APPDIR/usr/bin/"

    cat > "$APPDIR/BakerPi_Installer.desktop" << 'DESKTOP'
[Desktop Entry]
Name=BakerPi Tool Installer
Exec=BakerPi_Installer
Icon=bakerpi-installer
Type=Application
Categories=Network;Security;
DESKTOP

    cat > "$APPDIR/AppRun" << 'APPRUN'
#!/bin/bash
exec "$(dirname "$0")/usr/bin/BakerPi_Installer" "$@"
APPRUN
    chmod +x "$APPDIR/AppRun"

    ARCH=x86_64 appimagetool "$APPDIR" dist/BakerPi_Installer-x86_64.AppImage
    echo "[✓] AppImage: dist/BakerPi_Installer-x86_64.AppImage"
fi
