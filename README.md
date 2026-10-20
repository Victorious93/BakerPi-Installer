<!-- victorious-fleet-readme-refresh:start -->
<p align="center">
  <img src="assets/logo.png" alt="BakerPi-Installer logo" width="200">
</p>

# BakerPi-Installer

Cross-platform host tool to install/manage tools on a Raspberry Pi Zero (BakerPi).

**Package id:** `n/a (host tool)`

> **Package note:** Not an Android APK.

**Status:** CI green *(from [fleet-manifest ROADMAP](https://github.com/Victorious93/fleet-manifest/blob/main/ROADMAP.md))*

## Install / build

Python 3 + `requirements.txt`. Entry: `python3 launcher.py` / `python3 server.py` (see existing README). Tests: `python3 -m pytest`.

_Steps above are taken from this repo’s build files / existing docs; anything not exercised in this refresh is unlabeled as verified on a device._

## Victorious fleet

- Monorepo: [https://github.com/Victorious93/victorious-fleet](https://github.com/Victorious93/victorious-fleet)
- Fleet site: [https://victorious-framework.pages.dev](https://victorious-framework.pages.dev)

<!-- victorious-fleet-readme-refresh:end -->

Cross-platform tool installer for **BakerPi** — the [P4wnP1 A.L.O.A.](https://github.com/Victorious93/P4wnP1_aloa) fork adapted for the **Raspberry Pi Zero 1.3** (no built-in Wi‑Fi/Bluetooth; USB OTG only).

Install security-research tools, OS environments, IoT services, development utilities, and more onto your Pi Zero — from a PC, from an Android phone over USB OTG, or as a native desktop application.

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688)](https://fastapi.tiangolo.com/)
![Platform](https://img.shields.io/badge/target-Pi%20Zero%201.3%20(USB%20OTG)-c51a4a)
![Catalog](https://img.shields.io/badge/catalog-81%20tools%20·%2013%20categories-informational)

## Quick start

### Native desktop app (recommended on PC)

Pre-built binary (no Python needed), when distributed via releases:

```bash
# Linux
chmod +x BakerPi_Installer && ./BakerPi_Installer

# Windows: BakerPi_Installer.exe or BakerPi_Installer_Setup.exe
```

From source (native window via pywebview):

```bash
./run_app.sh          # Linux / macOS
run_app.bat           # Windows
```

### Web server mode (headless / SSH)

```bash
# PC — SSH to Pi over USB RNDIS
./run_pc.sh           # Linux / macOS
run_pc.bat            # Windows

# On-device — run on the Pi Zero; browse from phone at http://172.16.0.1:8080
sudo ./run_ondevice.sh
```

### Android (PWA)

1. With the Pi running `run_ondevice.sh`, open Chrome → `http://172.16.0.1:8080`.
2. Menu → **Add to Home Screen** (installable PWA; `static/manifest.json`).

A native Android APK path is documented against the BakerPi / P4wnP1_aloa fork’s `android/` tree when present.

## Features

- **13 categories, 81 tools** (catalog `tools/catalog.json` v1.0) — HID/USB, network, security research, Wi‑Fi/wireless, GPIO/sensors, IoT, media, dev tools, monitoring, SDR, home automation, infrastructure, OS environments
- **Kali Linux + Parrot OS** overlays (headless or XFCE/MATE desktop via VNC)
- **Native desktop app** — pywebview embeds the UI (no separate browser required)
- **Real-time install output** — SSE-streamed job logs (`/api/jobs/{id}/stream`)
- **Batch install / update / uninstall** — multi-select workflows
- **System info bar** — hostname, CPU temp, RAM, disk (`/api/system`)
- **Responsive PWA** — phone portrait through desktop; home-screen installable
- **PC SSH mode + on-device mode** — single FastAPI codebase (`server.py` + `launcher.py`)
- **VNC desktop control** — start/stop Kali/Parrot desktop sessions from the UI

> **Security note:** Tools such as nmap, aircrack-ng, Metasploit, etc. are for authorized pentesting, red-team work, and research only. DoS flood tools and medical/critical-infrastructure attack tools are excluded from the catalog.

## Screenshots

| Desktop app (tool grid) | Install job stream | System info | VNC control | Android PWA |
|---|---|---|---|---|
| *TODO* | *TODO* | *TODO* | *TODO* | *TODO* |

Suggested captures: category filter pills + search; multi-select install with live SSE log; Kali/Parrot OS environment cards; VNC start/stop; phone-width PWA on Android Chrome.

## Requirements

**Installer host (PC or Pi)**

- Python 3 with packages in `requirements.txt`: FastAPI, uvicorn, paramiko, aiofiles, python-multipart, pywebview
- Linux native window: `libwebkit2gtk-4.0-dev` and `libgtk-3-dev` (or distro equivalents)
- Optional for binaries: `pyinstaller`

**Target hardware**

- Raspberry Pi Zero 1.3 (ARM1176, USB OTG data port)
- USB OTG cable; Pi reachable at `172.16.0.1` over USB RNDIS/CDC-ECM
- Raspberry Pi OS Lite (Bookworm recommended)
- MicroSD ≥ 8 GB (≥ 32 GB recommended for OS environment installs)
- Optional USB Wi‑Fi adapter for wireless work (e.g. Alfa AWUS036NHA / AR9271 for monitor/injection/AP)

## Install from source

```bash
git clone https://github.com/Victorious93/BakerPi-Installer
cd BakerPi-Installer
pip3 install -r requirements.txt

# Native app — SSH to Pi over USB
python3 launcher.py --mode ssh --host 172.16.0.1 --user root

# Native app — on the Pi
sudo python3 launcher.py --mode local

# Headless web server — PC (opens browser)
python3 server.py --mode ssh --host 172.16.0.1 --user root

# Headless web server — on-device
sudo python3 server.py --mode local --no-browser
```

## Build standalone binaries

```bash
./build_app.sh        # Linux / macOS → dist/
build_app.bat         # Windows
```

Also: `bakerpi_installer.spec` (PyInstaller), `installer.iss` (Inno Setup), `.github/workflows/build-installers.yml` and `release.yml`.

## Tool categories

| Category | Example tools |
|---|---|
| HID & USB | BakerPi core, DuckyScript samples, USB image tools |
| Network | dnsmasq, wireguard, openvpn, responder, nginx, tcpdump |
| Security research | nmap, masscan, nikto, sqlmap, hydra, hashcat, metasploit, impacket |
| Wi‑Fi & wireless | aircrack-ng, bettercap, kismet, hcxdumptool |
| GPIO & sensors | RPi.GPIO, pigpio, i2c-tools, CircuitPython |
| IoT protocols | mosquitto, node-red, zigbee2mqtt, pymodbus |
| Media | mpd, ffmpeg, icecast2, jellyfin |
| Development | python3, nodejs, git, docker, golang, gitea, code-server |
| Monitoring | prometheus, grafana, influxdb, netdata |
| SDR & radio | rtl-sdr, dump1090, gqrx, gnuradio |
| Home automation | Home Assistant, openHAB |
| Infrastructure | k3s, tailscale, avahi, openssh |
| OS environments | Kali (headless/XFCE), Parrot (headless/MATE) |

Exact package lists and install scripts live under `tools/catalog.json` and `install_scripts/`.

## OS environments (Kali + Parrot)

Overlays Kali or Parrot repositories on Raspberry Pi OS; Pi OS packages stay higher priority.

| Option | Approx. disk | Notes |
|---|---|---|
| Kali Linux Core (headless) | ~2 GB | CLI security tools |
| Kali Linux + XFCE | ~3.5 GB | GUI via VNC (port 5901) |
| Parrot OS Core (headless) | ~1.8 GB | Pentest + privacy CLI |
| Parrot OS + MATE | ~3 GB | GUI via VNC (port 5901) |

Default VNC password documented historically as `bakerpi` — change with `vncpasswd` after install.

## Project structure

```text
server.py              FastAPI app (catalog, install jobs, SSH, VNC, system info)
launcher.py            pywebview native shell around the same UI
static/                Web UI (index.html), PWA manifest, favicon
tools/catalog.json     Tool definitions (81 tools, 13 categories)
install_scripts/       Shell helpers per category (HID, network, security, …)
run_*.sh|.bat          Launch helpers (app / PC / on-device)
build_app.*            PyInstaller packaging
bakerpi-installer.desktop
```

## Contributing

- Keep catalog entries accurate (`check_cmd` / packages / scripts).
- Prefer additive tools that fit authorized research; do not add excluded DoS/critical-infra attack tooling.
- Test SSH mode and local mode when changing `server.py` job streaming.

## License

**No `LICENSE` file is present in this repository.** Add an SPDX license before treating the project as redistributable open source. Until then, default copyright remains with the author; clarify terms before accepting external contributions.

## Part of BakerPi

Designed for the [BakerPi fork of P4wnP1 A.L.O.A.](https://github.com/Victorious93/P4wnP1_aloa), but usable with any Raspberry Pi OS system reachable over SSH or USB RNDIS.
