#!/bin/bash
# Launch BakerPi Tool Installer in PC/SSH mode.
# Connects to the Pi Zero via SSH over USB RNDIS (172.16.0.1) and opens
# the web UI in your browser at http://localhost:8080.
#
# Usage:
#   ./run_pc.sh                          # defaults: root@172.16.0.1
#   ./run_pc.sh --host 192.168.7.1       # CDC-ECM hosts
#   ./run_pc.sh --password raspberry
#   ./run_pc.sh --key-file ~/.ssh/id_rsa
#   ./run_pc.sh --server-port 9090       # change web UI port

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# Install Python deps if needed
if ! python3 -c "import fastapi, uvicorn, paramiko" 2>/dev/null; then
    echo "[*] Installing Python dependencies..."
    pip3 install -r requirements.txt --quiet
fi

echo "[*] Starting BakerPi Tool Installer (SSH/PC mode)..."
echo "[*] Will open browser at http://localhost:8080"
echo "[*] Press Ctrl+C to stop."
echo ""

python3 server.py --mode ssh "$@"
