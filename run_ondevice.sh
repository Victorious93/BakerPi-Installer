#!/bin/bash
# Launch BakerPi Tool Installer in on-device (local) mode.
# Run this ON the Pi Zero itself. Access the UI from a connected PC or
# Android phone at http://172.16.0.1:8080.
#
# Usage:
#   ./run_ondevice.sh                    # port 8080
#   ./run_ondevice.sh --server-port 9090 # custom port

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

if [[ $EUID -ne 0 ]]; then
    echo "[!] On-device mode requires root (for apt-get installs)."
    echo "    Run: sudo ./run_ondevice.sh"
    exit 1
fi

# Install Python deps if needed
if ! python3 -c "import fastapi, uvicorn" 2>/dev/null; then
    echo "[*] Installing Python dependencies..."
    pip3 install -r requirements.txt --quiet
fi

echo "[*] Starting BakerPi Tool Installer (on-device mode)..."
echo "[*] Access from your PC or phone at: http://172.16.0.1:8080"
echo "[*] Press Ctrl+C to stop."
echo ""

python3 server.py --mode local --no-browser "$@"
