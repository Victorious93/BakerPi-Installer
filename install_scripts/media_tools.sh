#!/bin/bash
# Media services: audio, video, streaming, emulation
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
TOOL_ID="${1:-}"
UPDATE_MODE="${2:-}"

install_mpd() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[media] Updating MPD..."
    apt-get update -qq && apt-get install -y --only-upgrade --no-install-recommends mpd ncmpc mpc 2>/dev/null || true
    systemctl restart mpd 2>/dev/null || true
    echo "[media] MPD updated."
    return
  fi
  echo "[media] Installing MPD + ncmpc + mpc..."
  apt-get install -y --no-install-recommends mpd ncmpc mpc
  systemctl enable mpd
  echo "[media] MPD installed. Config: /etc/mpd.conf | Control: mpc or ncmpc"
}

install_ffmpeg() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[media] Updating ffmpeg..."
    apt-get update -qq && apt-get install -y --only-upgrade --no-install-recommends ffmpeg 2>/dev/null || true
    echo "[media] ffmpeg updated."
    return
  fi
  echo "[media] Installing ffmpeg..."
  apt-get install -y --no-install-recommends ffmpeg
  echo "[media] ffmpeg installed."
}

install_icecast2() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[media] Updating Icecast2..."
    apt-get update -qq && apt-get install -y --only-upgrade --no-install-recommends icecast2 2>/dev/null || true
    systemctl restart icecast2 2>/dev/null || true
    echo "[media] Icecast2 updated."
    return
  fi
  echo "[media] Installing Icecast2..."
  echo "icecast2 icecast2/icecast-setup boolean false" | debconf-set-selections
  apt-get install -y --no-install-recommends icecast2
  echo "[media] Icecast2 installed. Config: /etc/icecast2/icecast.xml | Port: 8000"
}

install_retroarch() {
  echo "[media] Installing RetroArch..."
  apt-get install -y --no-install-recommends retroarch 2>/dev/null || \
    echo "[media] RetroArch package not available — download from https://www.retroarch.com/index.php?page=linux-instructions"
}

install_jellyfin() {
  if [ "$UPDATE_MODE" = "update" ] && dpkg -l jellyfin &>/dev/null; then
    echo "[media] Updating Jellyfin..."
    apt-get update -qq 2>/dev/null || true
    apt-get install -y --only-upgrade --no-install-recommends jellyfin 2>/dev/null || true
    systemctl restart jellyfin 2>/dev/null || true
    echo "[media] Jellyfin updated."
    return
  fi
  echo "[media] Installing Jellyfin..."
  apt-get install -y --no-install-recommends apt-transport-https gnupg
  curl -fsSL https://repo.jellyfin.org/packages/jellyfin_team.gpg.key | gpg --dearmor -o /etc/apt/keyrings/jellyfin.gpg 2>/dev/null || true
  echo "deb [signed-by=/etc/apt/keyrings/jellyfin.gpg] https://repo.jellyfin.org/debian bookworm main" \
    > /etc/apt/sources.list.d/jellyfin.list
  apt-get update -qq 2>/dev/null || true
  apt-get install -y --no-install-recommends jellyfin 2>/dev/null || \
    echo "[media] Jellyfin not available — try Docker: docker run -d -p 8096:8096 jellyfin/jellyfin"
}

case "$TOOL_ID" in
  "mpd_ncmpc")  install_mpd ;;
  "ffmpeg")     install_ffmpeg ;;
  "icecast2")   install_icecast2 ;;
  "retroarch")  install_retroarch ;;
  "jellyfin")   install_jellyfin ;;
  *)
    echo "[media] Unknown tool: $TOOL_ID"
    exit 1
    ;;
esac
