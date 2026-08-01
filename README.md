# BakerPi Installer

Cross-platform tool installer for **BakerPi** — the [P4wnP1 A.L.O.A.](https://github.com/Victorious93/P4wnP1_aloa) fork adapted for the Raspberry Pi Zero 1.3 (no built-in WiFi/Bluetooth).

Install security research tools, IoT services, development utilities, and more onto your Pi Zero — from a PC browser or directly from an Android phone over USB OTG.

---

## Quick Start

### PC mode (SSH over USB)

Run the installer on your laptop. It connects to the Pi Zero at `172.16.0.1` via SSH and opens the web UI in your browser.

```bash
# Linux / macOS
./run_pc.sh

# Windows
run_pc.bat
```

Or download a pre-built binary from [Releases](../../releases) — no Python needed.

### On-device mode (Android / any browser)

Run the installer **on the Pi Zero itself**. Access the UI from a connected PC or Android phone at `http://172.16.0.1:8080`.

```bash
sudo ./run_ondevice.sh
```

---

## Features

- **12 tool categories, ~80 tools** — HID/USB, network, security research, WiFi/wireless, GPIO/sensors, IoT protocols, media, dev tools, monitoring, SDR, home automation, infrastructure
- **Real-time install output** — SSE-streamed terminal output in the browser
- **Batch install, update & uninstall** — select multiple tools, install, update, or remove in one click
- **System info bar** — hostname, CPU temp, RAM, disk at a glance
- **Responsive** — works on 320px Android portrait and 1080p desktop
- **PC SSH mode + on-device mode** — single codebase for both use cases

---

## Installation from Source

```bash
git clone https://github.com/Victorious93/BakerPi-Installer
cd BakerPi-Installer
pip3 install -r requirements.txt

# PC mode
python3 server.py --mode ssh --host 172.16.0.1 --user root

# On-device mode (run on Pi Zero)
sudo python3 server.py --mode local --no-browser
```

## Building Standalone Binaries

```bash
# Linux / macOS
./build_app.sh

# Windows
build_app.bat
```

Requires `pyinstaller` (`pip3 install pyinstaller`). Output goes to `dist/`.

---

## Tool Categories

| Category | Example Tools |
|---|---|
| HID & USB | P4wnP1 core, DuckyScript samples, USB image tools |
| Network | dnsmasq, wireguard, openvpn, responder, nginx, tcpdump |
| Security Research | nmap, masscan, nikto, sqlmap, hydra, hashcat, metasploit, impacket |
| WiFi & Wireless | aircrack-ng, bettercap, kismet, hcxdumptool |
| GPIO & Sensors | RPi.GPIO, pigpio, i2c-tools, Adafruit CircuitPython |
| IoT Protocols | mosquitto, node-red, zigbee2mqtt, pymodbus |
| Media | mpd, ffmpeg, icecast2, jellyfin |
| Development | python3, nodejs, git, docker, golang, gitea, code-server |
| Monitoring | prometheus, grafana, influxdb, netdata |
| SDR & Radio | rtl-sdr, dump1090, gqrx, gnuradio |
| Home Automation | Home Assistant, openHAB |
| Infrastructure | k3s, tailscale, avahi, openssh |

> **Note:** Security research tools (nmap, aircrack-ng, etc.) are for authorized pentesting, red team engagements, and research. DoS flood tools and medical/critical-infrastructure attack tools are excluded from the catalog.

---

## Hardware Requirements

- Raspberry Pi Zero 1.3 (ARM1176, USB OTG only — no built-in WiFi)
- USB OTG cable connected to the Pi's data port
- Pi Zero accessible at `172.16.0.1` over USB RNDIS/CDC-ECM
- Raspberry Pi OS Lite (Bookworm recommended)

For WiFi capability, attach a USB WiFi adapter — the Alfa AWUS036NHA (Atheros AR9271) supports monitor mode.

---

## Part of BakerPi

This installer is designed for the [BakerPi fork of P4wnP1 A.L.O.A.](https://github.com/Victorious93/P4wnP1_aloa) but works with any Raspberry Pi OS system accessible over SSH.
