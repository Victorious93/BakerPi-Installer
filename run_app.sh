#!/bin/bash
# Launch BakerPi Tool Installer as a native desktop application.
# Opens the full tool UI inside a native OS window — no browser needed.
#
# Usage:
#   ./run_app.sh                          # PC mode: SSH to 172.16.0.1
#   ./run_app.sh --mode local             # on-device mode (run on the Pi Zero)
#   ./run_app.sh --host 192.168.7.1       # custom Pi IP
#   ./run_app.sh --password raspberry     # SSH password
#   ./run_app.sh --key-file ~/.ssh/id_rsa # SSH key auth
#
# Linux requirements (one-time):
#   sudo apt-get install libwebkit2gtk-4.0-dev libgtk-3-dev

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if ! python3 -c "import fastapi, uvicorn, paramiko, webview" 2>/dev/null; then
    echo "[*] Installing Python dependencies..."
    pip3 install -r requirements.txt --quiet
fi

echo "[*] Starting BakerPi Tool Installer (native desktop app)..."
python3 launcher.py "$@"
