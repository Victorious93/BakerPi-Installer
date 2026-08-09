

# BakerPi Tool Installer

Cross-platform tool installer for **BakerPi** — the [P4wnP1 A.L.O.A.](https://github.com/Victorious93/P4wnP1_aloa) fork adapted for the Raspberry Pi Zero 1.3 (no built-in WiFi/Bluetooth, USB OTG only).

Install security research tools, OS environments, IoT services, development utilities, and more onto your Pi Zero — from a PC, directly from an Android phone over USB OTG, or as a full native desktop application.

---

## Quick Start

### Native desktop app (recommended for PC)

Run the pre-built binary — no Python needed:

```bash
# Linux
chmod +x BakerPi_Installer && ./BakerPi_Installer

# Windows: double-click BakerPi_Installer.exe or BakerPi_Installer_Setup.exe
```

Or launch from source (opens a native app window, no browser required):

```bash
# Linux / macOS
./run_app.sh

# Windows
run_app.bat
```

### Web server mode (headless / SSH)

Serves the UI in your browser instead of a native window:

```bash
# PC mode — connect to Pi via SSH over USB
./run_pc.sh                           # Linux / macOS
run_pc.bat                            # Windows

# On-device mode — run on the Pi Zero itself
# Access from phone/browser at http://172.16.0.1:8080
sudo ./run_ondevice.sh
```

### Android

1. With the Pi Zero running `run_ondevice.sh`, open Chrome on your Android phone.
2. Browse to `http://172.16.0.1:8080`.
3. Tap the browser menu → **Add to Home Screen** — the installer installs as a PWA app icon.

Or use the native Android APK from the [android/](https://github.com/Victorious93/P4wnP1_aloa/tree/claude/pi-zero-tool-installer-zh92ov/android) folder in the BakerPi fork.

---

## Features

- **13 tool categories, 85+ tools** — HID/USB, network, security research, WiFi/wireless, GPIO/sensors, IoT protocols, media, dev tools, monitoring, SDR, home automation, infrastructure, OS environments
- **Kali Linux + Parrot OS** — add full security OS environments (headless CLI or XFCE/MATE desktop via VNC)
- **Native desktop app** — pywebview embeds the full UI inside a native window; no browser needed
- **Real-time install output** — SSE-streamed terminal output during installs
- **Batch install, update & uninstall** — select multiple tools, install/update/remove in one click
- **System info bar** — hostname, CPU temp, RAM, disk at a glance
- **Responsive PWA** — works on 320px Android portrait and 1080p desktop; installable as a home-screen app
- **PC SSH mode + on-device mode** — single codebase for both use cases
- **VNC desktop control** — start/stop Kali or Parrot desktop sessions directly from the UI

---

## Installation from Source

```bash
git clone https://github.com/Victorious93/BakerPi-Installer
cd BakerPi-Installer
pip3 install -r requirements.txt

# Native desktop app (SSH to Pi over USB)
python3 launcher.py --mode ssh --host 172.16.0.1 --user root

# Native desktop app (on-device, run on Pi Zero)
sudo python3 launcher.py --mode local

# Headless web server (PC mode — opens browser)
python3 server.py --mode ssh --host 172.16.0.1 --user root

# Headless web server (on-device)
sudo python3 server.py --mode local --no-browser
```

**Linux system dependency** (for the native app window):

```bash
sudo apt-get install libwebkit2gtk-4.0-dev libgtk-3-dev
```

---

## Building Standalone Binaries

```bash
# Linux / macOS
./build_app.sh

# Windows
build_app.bat
```

Requires `pyinstaller` (`pip3 install pyinstaller`). Output goes to `dist/`. See `.github/workflows/` for CI build and release automation.

---

## Tool Categories

| Category | Example Tools |
|---|---|
| HID & USB | BakerPi core, DuckyScript samples, USB image tools |
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
| **OS Environments** | **Kali Linux (headless/XFCE), Parrot OS (headless/MATE)** |

> **Security note:** Security research tools (nmap, aircrack-ng, Metasploit, etc.) are included for authorized pentesting, red team engagements, and security research only. DoS flood tools and medical/critical-infrastructure attack tools are excluded from the catalog.

---

## Hardware Requirements

- Raspberry Pi Zero 1.3 (ARM1176, USB OTG only — no built-in WiFi)
- USB OTG cable connected to the Pi's data port
- Pi Zero accessible at `172.16.0.1` over USB RNDIS/CDC-ECM
- Raspberry Pi OS Lite (Bookworm recommended)
- MicroSD card with ≥8 GB (≥32 GB recommended for OS environment installs)

For WiFi capability, attach a USB WiFi adapter — the Alfa AWUS036NHA (Atheros AR9271) supports monitor mode, packet injection, and AP mode.

---

## OS Environments (Kali + Parrot)

The **OS Environments** category overlays Kali Linux or Parrot OS repositories on top of Raspberry Pi OS. Your existing system is preserved — Pi OS packages are pinned at higher priority.

| Option | Disk | Notes |
|---|---|---|
| Kali Linux Core (headless) | ~2 GB | 100+ CLI security tools |
| Kali Linux + XFCE Desktop | ~3.5 GB | Full GUI via VNC (port 5901) |
| Parrot OS Core (headless) | ~1.8 GB | Pentest + privacy CLI tools |
| Parrot OS + MATE Desktop | ~3 GB | Full GUI via VNC (port 5901) |

After installing a desktop variant, use the **VNC Control** panel in the app to start/stop the desktop session. Default VNC password: `bakerpi` — change with `vncpasswd`.

---

## Part of BakerPi

This installer is designed for the [BakerPi fork of P4wnP1 A.L.O.A.](https://github.com/Victorious93/P4wnP1_aloa) but works with any Raspberry Pi OS system accessible over SSH or USB RNDIS.
