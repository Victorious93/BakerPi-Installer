#!/bin/bash
# Base setup: ensure apt is ready and common deps are installed
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive

echo "[base] Updating package lists..."
apt-get update -qq

echo "[base] Upgrading installed packages..."
apt-get upgrade -y -qq

echo "[base] Installing base utilities..."
apt-get install -y --no-install-recommends \
  curl wget ca-certificates \
  gnupg2 lsb-release \
  apt-transport-https \
  software-properties-common \
  unzip tar gzip bzip2 \
  screen tmux \
  net-tools iproute2 \
  procps psmisc \
  sudo less nano

echo "[base] Done."
