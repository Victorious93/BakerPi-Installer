#!/bin/bash
# Development tools, monitoring, SDR, infrastructure
set -euo pipefail
export DEBIAN_FRONTEND=noninteractive
TOOL_ID="${1:-}"
UPDATE_MODE="${2:-}"

install_python3_dev() {
  echo "[dev] Installing Python 3 dev stack..."
  apt-get install -y --no-install-recommends \
    python3 python3-pip python3-venv python3-dev build-essential
  echo "[dev] Python3 dev stack installed."
}

install_nodejs() {
  echo "[dev] Installing Node.js + npm..."
  apt-get install -y --no-install-recommends nodejs npm
  echo "[dev] Node.js $(node --version) installed."
}

install_git() {
  echo "[dev] Installing git..."
  apt-get install -y --no-install-recommends git
  echo "[dev] git installed."
}

install_docker() {
  echo "[dev] Installing Docker..."
  apt-get install -y --no-install-recommends docker.io
  systemctl enable docker
  systemctl start docker 2>/dev/null || true
  echo "[dev] Docker installed. Test: docker run hello-world"
}

install_vscode_server() {
  echo "[dev] Installing code-server (VS Code in browser)..."
  curl -fsSL https://code-server.dev/install.sh | sh - 2>/dev/null || \
    echo "[dev] code-server install failed — try: pip3 install code-server"
  systemctl enable code-server@root 2>/dev/null || true
  echo "[dev] code-server installed. Access: http://172.16.0.1:8080 (may conflict with installer)"
}

install_sqlite3() {
  echo "[dev] Installing SQLite3..."
  apt-get install -y --no-install-recommends sqlite3 python3-sqlite3
  echo "[dev] SQLite3 installed."
}

install_golang() {
  echo "[dev] Installing Go..."
  apt-get install -y --no-install-recommends golang
  echo "[dev] Go $(go version) installed."
}

install_gitea() {
  echo "[dev] Installing Gitea..."
  GITEA_VERSION="1.21.0"
  ARCH="linux-arm-6"
  wget -qO /usr/local/bin/gitea \
    "https://dl.gitea.com/gitea/${GITEA_VERSION}/gitea-${GITEA_VERSION}-${ARCH}" 2>/dev/null || true
  chmod +x /usr/local/bin/gitea
  useradd --system --shell /bin/bash --home /opt/gitea git 2>/dev/null || true
  mkdir -p /opt/gitea/{data,log,custom}
  chown -R git:git /opt/gitea
  cat > /etc/systemd/system/gitea.service << 'EOF'
[Unit]
Description=Gitea (Git with a cup of tea)
After=network.target

[Service]
User=git
WorkingDirectory=/opt/gitea
ExecStart=/usr/local/bin/gitea web --config /opt/gitea/custom/app.ini
Restart=always

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable gitea
  echo "[dev] Gitea installed. Access: http://172.16.0.1:3000 after: systemctl start gitea"
}

install_prometheus() {
  echo "[mon] Installing Prometheus + node exporter..."
  apt-get install -y --no-install-recommends prometheus prometheus-node-exporter 2>/dev/null || true
  systemctl enable prometheus prometheus-node-exporter 2>/dev/null || true
  echo "[mon] Prometheus installed. Metrics at http://172.16.0.1:9090"
}

install_grafana() {
  echo "[mon] Installing Grafana..."
  apt-get install -y --no-install-recommends apt-transport-https software-properties-common
  wget -q -O /usr/share/keyrings/grafana.key https://apt.grafana.com/gpg.key 2>/dev/null || true
  echo "deb [signed-by=/usr/share/keyrings/grafana.key] https://apt.grafana.com stable main" \
    > /etc/apt/sources.list.d/grafana.list
  apt-get update -qq 2>/dev/null || true
  apt-get install -y --no-install-recommends grafana 2>/dev/null || \
    echo "[mon] Grafana not available — try lightweight alternative: Netdata"
  systemctl enable grafana-server 2>/dev/null || true
  echo "[mon] Grafana installed. Access: http://172.16.0.1:3000"
}

install_influxdb() {
  echo "[mon] Installing InfluxDB..."
  wget -qO /tmp/influxdb.gpg https://repos.influxdata.com/influxdata-archive_compat.key 2>/dev/null || true
  cat /tmp/influxdb.gpg | gpg --dearmor > /etc/apt/keyrings/influxdb.gpg 2>/dev/null || true
  echo "deb [signed-by=/etc/apt/keyrings/influxdb.gpg] https://repos.influxdata.com/debian stable main" \
    > /etc/apt/sources.list.d/influxdb.list
  apt-get update -qq 2>/dev/null || true
  apt-get install -y --no-install-recommends influxdb2 2>/dev/null || \
    apt-get install -y --no-install-recommends influxdb 2>/dev/null || \
    echo "[mon] InfluxDB not available for this arch — try: pip3 install influxdb-client"
  echo "[mon] InfluxDB installed."
}

install_logwatch() {
  echo "[mon] Installing rsyslog + logwatch..."
  apt-get install -y --no-install-recommends rsyslog logwatch
  systemctl enable rsyslog
  echo "[mon] rsyslog + logwatch installed."
}

install_netdata() {
  echo "[mon] Installing netdata..."
  apt-get install -y --no-install-recommends netdata 2>/dev/null || \
    bash <(curl -Ss https://my-netdata.io/kickstart.sh) --dont-wait 2>/dev/null || true
  systemctl enable netdata 2>/dev/null || true
  echo "[mon] netdata installed. Dashboard: http://172.16.0.1:19999"
}

install_rtl_sdr() {
  echo "[sdr] Installing RTL-SDR tools..."
  apt-get install -y --no-install-recommends rtl-sdr librtlsdr-dev
  echo "[sdr] RTL-SDR installed. Test (plug in dongle): rtl_test -t"
}

install_dump1090() {
  echo "[sdr] Installing dump1090-fa (ADS-B)..."
  apt-get install -y --no-install-recommends dump1090-fa 2>/dev/null || \
    (git clone --depth=1 https://github.com/flightaware/dump1090.git /opt/dump1090 2>/dev/null && \
     make -C /opt/dump1090 2>/dev/null && \
     ln -sf /opt/dump1090/dump1090 /usr/local/bin/dump1090)
  echo "[sdr] dump1090 installed. Usage: dump1090 --interactive --net"
}

install_gqrx() {
  echo "[sdr] Installing gqrx..."
  apt-get install -y --no-install-recommends gqrx-sdr 2>/dev/null || \
    echo "[sdr] gqrx not available — requires display; use rtl_fm for headless use."
}

install_gnuradio() {
  echo "[sdr] Installing GNU Radio..."
  apt-get install -y --no-install-recommends gnuradio 2>/dev/null || \
    echo "[sdr] GNU Radio not available — large package (~500MB), may not fit on small SD."
}

install_k3s() {
  echo "[infra] Installing k3s (lightweight Kubernetes)..."
  curl -sfL https://get.k3s.io | sh - 2>/dev/null || \
    echo "[infra] k3s install failed — check internet connectivity."
  echo "[infra] k3s installed. Status: systemctl status k3s | Kubectl: k3s kubectl get nodes"
}

install_tailscale() {
  echo "[infra] Installing Tailscale..."
  curl -fsSL https://tailscale.com/install.sh | sh 2>/dev/null || \
    (apt-get install -y --no-install-recommends apt-transport-https && \
     curl -fsSL https://pkgs.tailscale.com/stable/raspbian/bookworm.noarmor.gpg | \
     tee /usr/share/keyrings/tailscale-archive-keyring.gpg >/dev/null && \
     echo "deb [signed-by=/usr/share/keyrings/tailscale-archive-keyring.gpg] https://pkgs.tailscale.com/stable/raspbian bookworm main" \
     | tee /etc/apt/sources.list.d/tailscale.list && \
     apt-get update -qq && apt-get install -y tailscale)
  echo "[infra] Tailscale installed. Run: tailscale up"
}

install_avahi() {
  echo "[infra] Installing avahi (mDNS)..."
  apt-get install -y --no-install-recommends avahi-daemon avahi-utils
  systemctl enable avahi-daemon
  echo "[infra] avahi installed. Pi Zero accessible at p4wnp1.local"
}

install_openssh() {
  echo "[infra] Installing OpenSSH server..."
  apt-get install -y --no-install-recommends openssh-server
  systemctl enable ssh
  echo "[infra] SSH server installed. Connect: ssh root@172.16.0.1"
}

install_homeassistant() {
  if [ "$UPDATE_MODE" = "update" ]; then
    echo "[ha] Updating Home Assistant..."
    pip3 install --upgrade homeassistant 2>/dev/null || true
    systemctl restart homeassistant 2>/dev/null || true
    echo "[ha] Home Assistant updated."
    return
  fi
  echo "[ha] Installing Home Assistant..."
  pip3 install --quiet homeassistant 2>/dev/null || true
  cat > /etc/systemd/system/homeassistant.service << 'EOF'
[Unit]
Description=Home Assistant
After=network.target

[Service]
Type=simple
ExecStart=/usr/local/bin/hass --config /etc/homeassistant
Restart=on-failure

[Install]
WantedBy=multi-user.target
EOF
  systemctl daemon-reload
  systemctl enable homeassistant
  echo "[ha] Home Assistant installed. Start: systemctl start homeassistant | Access: http://172.16.0.1:8123"
}

install_openhab() {
  echo "[ha] Installing openHAB..."
  apt-get install -y --no-install-recommends apt-transport-https openjdk-17-jdk
  wget -qO /usr/share/keyrings/openhab.gpg https://openhab.jfrog.io/artifactory/api/security/keypair/public/repositories/openhab 2>/dev/null || true
  echo "deb [signed-by=/usr/share/keyrings/openhab.gpg] https://openhab.jfrog.io/artifactory/openhab-linuxpkg stable main" \
    > /etc/apt/sources.list.d/openhab.list
  apt-get update -qq 2>/dev/null || true
  apt-get install -y --no-install-recommends openhab 2>/dev/null || \
    echo "[ha] openHAB not available — requires Java. Check https://www.openhab.org/docs/installation/linux.html"
}

case "$TOOL_ID" in
  "python3_dev")    install_python3_dev ;;
  "nodejs_npm")     install_nodejs ;;
  "git")            install_git ;;
  "docker")         install_docker ;;
  "vscode_server")  install_vscode_server ;;
  "sqlite3")        install_sqlite3 ;;
  "golang")         install_golang ;;
  "gitea")          install_gitea ;;
  "prometheus")     install_prometheus ;;
  "grafana")        install_grafana ;;
  "influxdb")       install_influxdb ;;
  "logwatch")       install_logwatch ;;
  "netdata")        install_netdata ;;
  "rtl_sdr")        install_rtl_sdr ;;
  "dump1090")       install_dump1090 ;;
  "gqrx")          install_gqrx ;;
  "gnuradio")       install_gnuradio ;;
  "k3s")            install_k3s ;;
  "tailscale")      install_tailscale ;;
  "avahi_mdns")     install_avahi ;;
  "openssh_server") install_openssh ;;
  "homeassistant")  install_homeassistant ;;
  "openhab")        install_openhab ;;
  *)
    echo "[dev] Unknown tool: $TOOL_ID"
    exit 1
    ;;
esac
