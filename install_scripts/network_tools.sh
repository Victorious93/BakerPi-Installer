#!/bin/bash
# Network services and wireless tools
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
TOOL_ID="${1:-}"
UPDATE_MODE="${2:-}"

install_dnsmasq() {
  echo "[net] Installing dnsmasq..."
  apt-get install -y --no-install-recommends dnsmasq
  systemctl disable dnsmasq 2>/dev/null || true  # BakerPi core manages it
  echo "[net] dnsmasq installed (managed by BakerPi core)."
}

install_hostapd() {
  echo "[net] Installing hostapd..."
  apt-get install -y --no-install-recommends hostapd
  systemctl disable hostapd 2>/dev/null || true  # BakerPi core manages it
  echo "[net] hostapd installed (managed by BakerPi core)."
}

install_iodine() {
  echo "[net] Installing iodine (DNS tunneling)..."
  apt-get install -y --no-install-recommends iodine
  echo "[net] iodine installed. Usage: iodine -f -P <password> <dns_server> <domain>"
}

install_iw() {
  echo "[net] Installing iw + wireless-tools..."
  apt-get install -y --no-install-recommends iw wireless-tools
  echo "[net] Wireless tools installed."
}

install_openvpn() {
  echo "[net] Installing OpenVPN..."
  apt-get install -y --no-install-recommends openvpn
  echo "[net] OpenVPN installed. Place .ovpn config in /etc/openvpn/client/"
}

install_wireguard() {
  echo "[net] Installing WireGuard..."
  apt-get install -y --no-install-recommends wireguard wireguard-tools
  modprobe wireguard 2>/dev/null || true
  echo "[net] WireGuard installed. Config: /etc/wireguard/wg0.conf"
}

install_tcpdump() {
  echo "[net] Installing tcpdump..."
  apt-get install -y --no-install-recommends tcpdump
  echo "[net] tcpdump installed."
}

install_tshark() {
  echo "[net] Installing tshark..."
  echo "wireshark-common wireshark-common/install-setuid boolean true" | debconf-set-selections
  apt-get install -y --no-install-recommends tshark
  echo "[net] tshark installed."
}

install_nginx() {
  echo "[net] Installing nginx..."
  apt-get install -y --no-install-recommends nginx
  systemctl enable nginx
  echo "[net] nginx installed. Config: /etc/nginx/sites-available/"
}

install_sslsplit() {
  echo "[net] Installing sslsplit..."
  apt-get install -y --no-install-recommends sslsplit
  echo "[net] sslsplit installed. Usage: sslsplit -D -l /var/log/sslsplit.log ssl 0.0.0.0 8443"
}

install_responder() {
  if [ "$UPDATE_MODE" = "update" ] && [ -d /opt/Responder ]; then
    echo "[net] Updating Responder..."
    git -C /opt/Responder pull 2>/dev/null || true
    pip3 install --upgrade --quiet ldap3 cryptography
    echo "[net] Responder updated."
    return
  fi
  echo "[net] Installing Responder..."
  apt-get install -y --no-install-recommends python3 python3-pip git
  pip3 install --quiet ldap3 cryptography
  cd /opt
  git clone --depth=1 https://github.com/lgandx/Responder.git 2>/dev/null || true
  ln -sf /opt/Responder/Responder.py /usr/local/bin/responder
  chmod +x /usr/local/bin/responder
  echo "[net] Responder installed at /opt/Responder/"
}

install_iptables() {
  echo "[net] Installing nftables + iptables..."
  apt-get install -y --no-install-recommends nftables iptables
  echo "[net] nftables/iptables installed."
}

install_autossh() {
  echo "[net] Installing autossh..."
  apt-get install -y --no-install-recommends autossh
  echo "[net] autossh installed. Usage: autossh -M 0 -N -R 2222:localhost:22 user@server"
}

install_aircrack() {
  echo "[wifi] Installing aircrack-ng suite..."
  apt-get install -y --no-install-recommends aircrack-ng
  echo "[wifi] aircrack-ng installed. Note: requires USB WiFi adapter with monitor mode."
}

install_bettercap() {
  echo "[wifi] Installing bettercap..."
  apt-get install -y --no-install-recommends bettercap 2>/dev/null || \
    pip3 install bettercap 2>/dev/null || \
    (cd /opt && git clone --depth=1 https://github.com/bettercap/bettercap.git 2>/dev/null && echo "Build bettercap from source: cd /opt/bettercap && go build")
  echo "[wifi] bettercap installed."
}

install_kismet() {
  echo "[wifi] Installing Kismet..."
  apt-get install -y --no-install-recommends kismet
  echo "[wifi] Kismet installed. Web UI at port 2501."
}

install_mdk4() {
  echo "[wifi] Installing mdk4..."
  apt-get install -y --no-install-recommends mdk4
  echo "[wifi] mdk4 installed. WARNING: for authorized testing only."
}

install_hcxdumptool() {
  echo "[wifi] Installing hcxdumptool + hcxtools..."
  apt-get install -y --no-install-recommends hcxdumptool hcxtools
  echo "[wifi] hcxdumptool installed."
}

install_wpa_supplicant() {
  echo "[wifi] Installing wpa_supplicant..."
  apt-get install -y --no-install-recommends wpasupplicant
  echo "[wifi] wpa_supplicant installed."
}

case "$TOOL_ID" in
  "dnsmasq")          install_dnsmasq ;;
  "hostapd")          install_hostapd ;;
  "iodine")           install_iodine ;;
  "iw_wireless")      install_iw ;;
  "openvpn")          install_openvpn ;;
  "wireguard")        install_wireguard ;;
  "tcpdump")          install_tcpdump ;;
  "wireshark_cli")    install_tshark ;;
  "nginx")            install_nginx ;;
  "sslsplit")         install_sslsplit ;;
  "responder")        install_responder ;;
  "iptables_nftables") install_iptables ;;
  "autossh")          install_autossh ;;
  "aircrack")         install_aircrack ;;
  "bettercap")        install_bettercap ;;
  "kismet")           install_kismet ;;
  "mdk4")             install_mdk4 ;;
  "hcxdumptool")      install_hcxdumptool ;;
  "wpa_supplicant")   install_wpa_supplicant ;;
  *)
    echo "[net] Unknown tool: $TOOL_ID"
    exit 1
    ;;
esac
