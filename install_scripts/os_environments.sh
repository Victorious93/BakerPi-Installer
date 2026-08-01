#!/bin/bash
# Kali Linux and Parrot OS environment setup for Raspberry Pi Zero 1.3
# Adds the OS repository alongside Raspberry Pi OS and installs the chosen metapackage.
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
TOOL_ID="${1:-}"
UPDATE_MODE="${2:-}"

# ── Kali Linux ────────────────────────────────────────────────────────────────

add_kali_repo() {
  echo "[os] Adding Kali Linux rolling repository..."
  apt-get install -y --no-install-recommends curl gnupg ca-certificates
  curl -fsSL https://archive.kali.org/archive-key.asc | \
    gpg --dearmor -o /usr/share/keyrings/kali-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/kali-archive-keyring.gpg] https://http.kali.org/kali kali-rolling main contrib non-free" \
    > /etc/apt/sources.list.d/kali.list
  # Pin below Raspberry Pi OS so Kali packages won't override base system packages
  cat > /etc/apt/preferences.d/kali-pinning << 'EOF'
Package: *
Pin: release a=kali-rolling
Pin-Priority: 100
EOF
  apt-get update -qq
  echo "[os] Kali repository added."
}

install_kali_headless() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[os] Updating Kali Linux headless tools..."
    apt-get update -qq
    apt-get upgrade -y --no-install-recommends kali-linux-headless 2>/dev/null || true
    echo "[os] Kali tools updated."
    return
  fi
  echo "[os] Installing Kali Linux Core (headless, ~2GB)..."
  [ -f /etc/apt/sources.list.d/kali.list ] || add_kali_repo
  apt-get install -y --no-install-recommends kali-linux-headless
  echo "[os] Kali Linux Core installed — 100+ security tools available."
}

install_kali_desktop() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[os] Updating Kali XFCE desktop..."
    apt-get update -qq
    apt-get upgrade -y --no-install-recommends kali-desktop-xfce 2>/dev/null || true
    echo "[os] Kali desktop updated."
    return
  fi
  echo "[os] Installing Kali Linux + XFCE4 minimal desktop (~3.5GB)..."
  [ -f /etc/apt/sources.list.d/kali.list ] || add_kali_repo
  apt-get install -y --no-install-recommends kali-desktop-xfce
  apt-get install -y --no-install-recommends tigervnc-standalone-server dbus-x11
  # Create VNC startup for XFCE
  mkdir -p /root/.vnc
  cat > /root/.vnc/xstartup << 'EOF'
#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export XDG_SESSION_TYPE=x11
exec startxfce4
EOF
  chmod +x /root/.vnc/xstartup
  # Default VNC password — user should change with: vncpasswd
  printf 'bakerpi\nbakerpi\n\n' | vncpasswd 2>/dev/null || \
    echo "bakerpi" | vncpasswd -f > /root/.vnc/passwd
  chmod 600 /root/.vnc/passwd 2>/dev/null || true
  echo ""
  echo "[os] Kali XFCE desktop installed."
  echo "[os] Default VNC password: 'bakerpi'  — change with: vncpasswd"
  echo "[os] Start desktop: vncserver :1 -geometry 1280x800"
  echo "[os] Then connect your VNC client to port 5901"
}

# ── Parrot OS ─────────────────────────────────────────────────────────────────

add_parrot_repo() {
  echo "[os] Adding Parrot OS repository..."
  apt-get install -y --no-install-recommends curl gnupg ca-certificates
  curl -fsSL https://archive.parrotsec.org/parrot/misc/parrot-archive-keyring.gpg \
    -o /usr/share/keyrings/parrot-archive-keyring.gpg
  echo "deb [signed-by=/usr/share/keyrings/parrot-archive-keyring.gpg] https://deb.parrotsec.org/parrot rolling main contrib non-free" \
    > /etc/apt/sources.list.d/parrot.list
  cat > /etc/apt/preferences.d/parrot-pinning << 'EOF'
Package: *
Pin: release o=Parrot
Pin-Priority: 100
EOF
  apt-get update -qq
  echo "[os] Parrot OS repository added."
}

install_parrot_core() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[os] Updating Parrot OS core tools..."
    apt-get update -qq
    apt-get upgrade -y --no-install-recommends parrot-tools-core 2>/dev/null || true
    echo "[os] Parrot tools updated."
    return
  fi
  echo "[os] Installing Parrot OS Core tools (headless, ~1.8GB)..."
  [ -f /etc/apt/sources.list.d/parrot.list ] || add_parrot_repo
  apt-get install -y --no-install-recommends parrot-tools-core
  echo "[os] Parrot OS Core installed — curated pentesting + privacy tools available."
}

install_parrot_desktop() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[os] Updating Parrot OS MATE desktop..."
    apt-get update -qq
    apt-get upgrade -y --no-install-recommends parrot-desktop-mate 2>/dev/null || true
    echo "[os] Parrot desktop updated."
    return
  fi
  echo "[os] Installing Parrot OS + MATE minimal desktop (~3GB)..."
  [ -f /etc/apt/sources.list.d/parrot.list ] || add_parrot_repo
  apt-get install -y --no-install-recommends parrot-desktop-mate
  apt-get install -y --no-install-recommends tigervnc-standalone-server dbus-x11
  mkdir -p /root/.vnc
  cat > /root/.vnc/xstartup << 'EOF'
#!/bin/bash
unset SESSION_MANAGER
unset DBUS_SESSION_BUS_ADDRESS
export XDG_SESSION_TYPE=x11
exec mate-session
EOF
  chmod +x /root/.vnc/xstartup
  printf 'bakerpi\nbakerpi\n\n' | vncpasswd 2>/dev/null || \
    echo "bakerpi" | vncpasswd -f > /root/.vnc/passwd
  chmod 600 /root/.vnc/passwd 2>/dev/null || true
  echo ""
  echo "[os] Parrot MATE desktop installed."
  echo "[os] Default VNC password: 'bakerpi'  — change with: vncpasswd"
  echo "[os] Start desktop: vncserver :1 -geometry 1280x800"
  echo "[os] Then connect your VNC client to port 5901"
}

# ── Dispatch ──────────────────────────────────────────────────────────────────

case "$TOOL_ID" in
  "kali_headless")  install_kali_headless ;;
  "kali_desktop")   install_kali_desktop ;;
  "parrot_core")    install_parrot_core ;;
  "parrot_desktop") install_parrot_desktop ;;
  *)
    echo "[os] Unknown tool: $TOOL_ID"
    exit 1
    ;;
esac
