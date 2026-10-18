<p align="center">
  <img src="static/bakerpi-logo.png" alt="BakerPi logo" width="128">
</p>

# BakerPi Tool Installer

**Install security-research tools, OS environments and more onto a Raspberry Pi Zero — from a PC, an Android phone, or a native desktop app.**

[![Python](https://img.shields.io/badge/Python-3.x-3776AB?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/API-FastAPI-009688?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com/)
![Target](https://img.shields.io/badge/target-Pi%20Zero%201.3%20(USB%20OTG)-c51a4a)
![Catalog](https://img.shields.io/badge/catalog-81%20tools%20%C2%B7%2013%20categories-informational)
![License](https://img.shields.io/badge/license-none%20specified-lightgrey)

## Overview

BakerPi Tool Installer is a cross-platform installer UI for **BakerPi**, the [P4wnP1 A.L.O.A.](https://github.com/Victorious93/P4wnP1_aloa) fork adapted for the **Raspberry Pi Zero 1.3** (no built-in Wi-Fi/Bluetooth; USB OTG only). A single FastAPI backend (`server.py`) serves a responsive web UI that can run in a native window (`launcher.py`, via pywebview), in a browser over SSH, or on the Pi itself.

*Screenshots coming soon.*

## Key features

- **13 categories, 81 tools** (`tools/catalog.json` v1.0): HID/USB, network, security research, Wi-Fi/wireless, GPIO/sensors, IoT, media, dev tools, monitoring, SDR, home automation, infrastructure, OS environments
- **Kali Linux and Parrot OS overlays**: headless, or XFCE/MATE desktop via VNC
- **Live install output**: SSE-streamed job logs (`/api/jobs/{id}/stream`)
- **Batch install / update / uninstall** with multi-select
- **System info bar**: hostname, CPU temperature, RAM, disk (`/api/system`)
- **Responsive, installable PWA**: phone portrait through desktop
- **Two modes, one codebase**: SSH from a PC, or run directly on the Pi
- **VNC control**: start/stop Kali/Parrot desktop sessions from the UI
- **Device inventory & targeting** *(new, untested on real hardware — see [Multiple devices](#multiple-devices-device-inventory--targeting))*: keep a list of Pi targets, pick the active one, or run installs on several in parallel
- **Fleet install profiles** *(new, untested on real hardware — see [Fleet install profiles](#fleet-install-profiles))*: save a named set of tools once and apply it to one or many devices in a single action

> **Security note:** Tools such as nmap, aircrack-ng and Metasploit are for authorized pentesting, red-team work and research only. DoS flood tools and medical/critical-infrastructure attack tools are excluded from the catalog.

## Install

### Pre-built binaries

The release workflow (`.github/workflows/release.yml`) publishes these assets on `v*` tags. No GitHub release has been published yet, so build from source for now.

| Platform | Asset |
|---|---|
| Linux x86-64 | `BakerPi_Installer-<tag>-x86_64.AppImage` |
| Windows | `BakerPi_Installer-<tag>-windows.exe` (standalone) |
| Windows | `BakerPi_Installer_Setup-<tag>.exe` (installer) |

### From source

```bash
git clone https://github.com/Victorious93/BakerPi-Installer
cd BakerPi-Installer
pip3 install -r requirements.txt
```

**Requirements**

- Python 3 and the packages in `requirements.txt` (FastAPI, uvicorn, paramiko, aiofiles, python-multipart, pywebview)
- Linux native window: `libwebkit2gtk-4.0-dev` and `libgtk-3-dev` (or distro equivalents)

**Target hardware**

- Raspberry Pi Zero 1.3 (ARM1176, USB OTG data port) with a USB OTG cable; Pi reachable at `172.16.0.1` over USB RNDIS/CDC-ECM
- Raspberry Pi OS Lite (Bookworm recommended)
- MicroSD >= 8 GB (>= 32 GB recommended for OS environment installs)
- Optional USB Wi-Fi adapter for wireless work (e.g. Alfa AWUS036NHA / AR9271 for monitor/injection/AP)

## Usage

### Native desktop app (recommended on PC)

```bash
./run_app.sh          # Linux / macOS
run_app.bat           # Windows

# or directly
python3 launcher.py --mode ssh --host 172.16.0.1 --user root   # SSH to Pi over USB
sudo python3 launcher.py --mode local                          # on the Pi
```

### Web server mode (headless / SSH)

```bash
./run_pc.sh           # PC: SSH to Pi over USB RNDIS (browser at http://localhost:8080)
run_pc.bat            # Windows

sudo ./run_ondevice.sh   # on the Pi Zero; browse from a phone at http://172.16.0.1:8080
```

Or run the server directly:

```bash
python3 server.py --mode ssh --host 172.16.0.1 --user root     # PC, opens browser
sudo python3 server.py --mode local --no-browser               # on-device
```

Use `--server-port` to change the web UI port (default `8080`).

### Multiple devices (device inventory & targeting)

> **Status: UNTESTED on real hardware.** This feature was developed and checked with unit/API tests (fake command execution) and a UI walkthrough against a fake backend only. It has **not** been run against a real Raspberry Pi Zero (or any real SSH target). Expect rough edges and please report them.

The app still starts with a single target taken from the command line, exactly as before. On top of that you can keep an inventory of Pi targets and choose where actions run.

**Concepts**

| Term | Meaning |
|---|---|
| **Default device** | Built-in entry (`id: default`) built from `--mode/--host/--user/--port/--key-file`. Always present, never saved to disk, cannot be edited or removed. With no config, this is the only device, so existing usage is unchanged. |
| **Registry** | Extra devices you add: `id`, `label`, connection `type` (`ssh`, `usb-rndis`, `local`), `host`, `user`, SSH `port` (plus an optional key-file *path*). `usb-rndis` is SSH over the USB gadget link and defaults the host to `172.16.0.1`. |
| **Target** | Devices that Install / Update / Remove / Update All run on. Several targets run **in parallel**, one job task per device. |
| **Viewing** | The first selected device. The tool grid's installed-status, the system-info bar and VNC status follow it. |

**In the UI:** click the device chip in the top bar to open the **Devices** panel. Add / edit / remove devices, tick **T** (target) for one or more devices, and pick **V** (viewing) with the radio. Each row has a **Connect** button for SSH devices (optional password, kept in memory only; key/agent auth also works). Multi-device jobs show one log tab per device with a status dot, and the system-info bar and job title name the device they belong to.

**Where it is stored:** `devices.json` in a per-user config directory (never in the repo):

| OS | Path |
|---|---|
| Linux | `$XDG_CONFIG_HOME/BakerPi-Installer/devices.json` (default `~/.config/...`) |
| macOS | `~/Library/Application Support/BakerPi-Installer/devices.json` |
| Windows | `%APPDATA%\BakerPi-Installer\devices.json` |

Override with `--devices-file PATH` (`server.py` and `launcher.py`) or `BAKERPI_DEVICES_FILE`. The file is written with mode `0600`, holds no passwords, and `devices.json` is in `.gitignore`. An unreadable file is moved to `devices.json.bad` and ignored.

**API** (all optional-target parameters fall back to the current selection, which falls back to the default device):

| Endpoint | Notes |
|---|---|
| `GET/POST /api/devices` | list / add |
| `GET/PUT/DELETE /api/devices/{id}` | read / partial update / remove (`default` is read-only) |
| `GET/PUT /api/devices/selected` | read / set `{"device_ids": [...]}` (first = viewing) |
| `POST /api/devices/{id}/connect` | open SSH for a device; body `{"password"?, "key_file"?}` |
| `POST /api/install`, `/api/update`, `/api/uninstall` | body accepts `device_id` or `device_ids` |
| `POST /api/update-all` | optional body `{device_ids}`; per-device installed list, devices with nothing installed are reported as `skipped_devices` |
| `GET /api/tools`, `/api/tools/{id}/status`, `/api/system`, `/api/services/vnc/*` | optional `?device_id=` (VNC start: `device_id` in body) |
| `GET /api/jobs/{id}`, `/api/jobs/{id}/stream` | per-device `devices[]` status/logs; SSE events carry `device`, `line`, `device_status`, and a final `done` with a per-device summary |

The legacy `POST /api/ssh/connect` (the **⚙ SSH** panel) still works and re-points the default device.

**Known limits / TODO**

- Status views (tool installed-state, system info, VNC) are single-device (the *viewing* device); there is no side-by-side fleet status table yet.
- No per-device concurrency limit, retry, or cancel for running jobs; a failed device does not stop the others.
- No saved passwords, SSH host-key pinning (host keys are auto-accepted, as before), device discovery, or groups/tags yet.
- Jobs and logs are in memory only (lost on restart).
- Tests (`tests/`) cover the registry logic and API targeting with faked commands only — no real SSH or hardware.

### Fleet install profiles

> **Status: UNTESTED on real hardware.** Like the device targeting it builds on, this was developed and checked with unit/API tests (fake command execution) and a UI walkthrough against a fake backend only. It has **not** been run against a real Raspberry Pi Zero (or any real SSH target).

A **profile** is a named, reusable, ordered set of tools (a selection from `tools/catalog.json`) that you can apply to one or many devices in one action, for example a "recon kit" or a "wifi kit".

| Field | Notes |
|---|---|
| `id` | Generated 8-character id |
| `name` | Required, up to 64 characters, unique (case-insensitive) |
| `description` | Optional, up to 500 characters |
| `tool_ids` | Ordered, de-duplicated, at least one. Each id must exist in the catalog; unknown ids are rejected |

**In the UI:** click **📦 Profiles** in the top bar. **+ New profile** opens a form with a filterable, category-grouped tool picker (or **Use grid selection** to start from the tools currently ticked in the grid). Each saved profile has **⬇ Apply to selected device(s)**, **Edit** and **✕**. Apply asks for confirmation, then installs the profile's tools in order on the current *target* devices from the [Devices panel](#multiple-devices-device-inventory--targeting), in parallel with one log tab per device. With nothing explicitly selected it falls back to the default device, exactly like Install.

**How apply works:** it is an ordinary *install* job (the same code path as `POST /api/install`) for each tool in the profile on each selected device. A failed tool is logged and the remaining tools still run; a failed or unreachable device is marked failed without stopping the others. Apply itself never uninstalls or updates anything. Tools that are already installed are simply run through their install step again, as with Install today.

**Where it is stored:** `profiles.json` next to `devices.json` in the per-user config directory (never in the repo):

| OS | Path |
|---|---|
| Linux | `$XDG_CONFIG_HOME/BakerPi-Installer/profiles.json` (default `~/.config/...`) |
| macOS | `~/Library/Application Support/BakerPi-Installer/profiles.json` |
| Windows | `%APPDATA%\BakerPi-Installer\profiles.json` |

Override with `--profiles-file PATH` (`server.py` and `launcher.py`) or `BAKERPI_PROFILES_FILE`. The file is written with mode `0600`, contains only profile names, descriptions and tool ids (no hosts, passwords or keys), and `profiles.json` is in `.gitignore`. An unreadable file is moved to `profiles.json.bad` and ignored. Tool ids are checked against the catalog when a profile is saved; if a later catalog no longer has one of them, the profile is still listed but cannot be applied until you edit it.

**API** (target parameters behave as for the install endpoints: `device_ids` > `device_id` > current selection > default device):

| Endpoint | Notes |
|---|---|
| `GET/POST /api/profiles` | list / create `{"name", "description"?, "tool_ids"}` |
| `GET/PUT/DELETE /api/profiles/{id}` | read / partial update / delete |
| `POST /api/profiles/{id}/apply` | optional body `{device_id}` or `{device_ids}`; returns `job_id`, `devices`, `profile`, `tool_ids`; follow it with the existing `/api/jobs/{id}` and `/api/jobs/{id}/stream` |

**Known limits / TODO**

- Profiles only *install*; there is no drift detection, re-sync, or "apply as update".
- Profiles are not tied to individual devices, and cannot be exported, imported or shared yet.
- Everything noted under [Multiple devices](#multiple-devices-device-inventory--targeting) (no retry/cancel, in-memory job logs, auto-accepted SSH host keys) applies here too.
- Tests (`tests/`) cover profile storage, catalog validation and apply-to-devices targeting with faked commands only — no real SSH or hardware.

### Android (PWA)

1. With the Pi running `run_ondevice.sh`, open Chrome at `http://172.16.0.1:8080`.
2. Menu -> **Add to Home Screen** (manifest: `static/manifest.json`).

## Tool categories

| Category | Example tools |
|---|---|
| HID & USB | BakerPi core, DuckyScript samples, USB image tools |
| Network | dnsmasq, wireguard, openvpn, responder, nginx, tcpdump |
| Security research | nmap, masscan, nikto, sqlmap, hydra, hashcat, metasploit, impacket |
| Wi-Fi & wireless | aircrack-ng, bettercap, kismet, hcxdumptool |
| GPIO & sensors | RPi.GPIO, pigpio, i2c-tools, CircuitPython |
| IoT protocols | mosquitto, node-red, zigbee2mqtt, pymodbus |
| Media | mpd, ffmpeg, icecast2, jellyfin |
| Development | python3, nodejs, git, docker, golang, gitea, code-server |
| Monitoring | prometheus, grafana, influxdb, netdata |
| SDR & radio | rtl-sdr, dump1090, gqrx, gnuradio |
| Home automation | Home Assistant, openHAB |
| Infrastructure | k3s, tailscale, avahi, openssh |
| OS environments | Kali (headless/XFCE), Parrot (headless/MATE) |

Exact package lists and install scripts live in `tools/catalog.json` and `install_scripts/`.

### OS environments (Kali + Parrot)

These overlay the Kali or Parrot repositories on Raspberry Pi OS; Pi OS packages keep higher priority.

| Option | Approx. disk | Notes |
|---|---|---|
| Kali Linux Core (headless) | ~2 GB | CLI security tools |
| Kali Linux + XFCE | ~3.5 GB | GUI via VNC (port 5901) |
| Parrot OS Core (headless) | ~1.8 GB | Pentest + privacy CLI |
| Parrot OS + MATE | ~3 GB | GUI via VNC (port 5901) |

The install script sets a default VNC password of `bakerpi`. Change it with `vncpasswd` after install.

## Build from source

Builds a standalone executable with PyInstaller (`bakerpi_installer.spec`):

```bash
./build_app.sh        # Linux / macOS -> dist/BakerPi_Installer
build_app.bat         # Windows
```

`build_app.sh` installs `requirements.txt` and `pyinstaller`, and builds an AppImage if `appimagetool` is available. On Linux, install the WebKit/GTK dev headers first:

```bash
sudo apt-get install libwebkit2gtk-4.0-dev libgtk-3-dev libglib2.0-dev
```

Windows installers use Inno Setup (`installer.iss`). CI builds are defined in `.github/workflows/build-installers.yml` and `release.yml`.

## Project structure

```text
server.py              FastAPI app (catalog, install jobs, SSH, VNC, system info, device + profile API)
device_registry.py     Device inventory: persisted Pi targets + selection (stdlib only)
profile_registry.py    Fleet install profiles: persisted named toolsets (stdlib only)
tests/                 pytest suite (no hardware needed)
launcher.py            pywebview native shell around the same UI
static/                Web UI (index.html), PWA manifest, logo, favicon
tools/catalog.json     Tool definitions (81 tools, 13 categories)
install_scripts/       Shell helpers per category (HID, network, security, ...)
run_*.sh|.bat          Launch helpers (app / PC / on-device)
build_app.*            PyInstaller packaging
bakerpi-installer.desktop
```

## Tests

```bash
pip3 install -r requirements-dev.txt
python3 -m pytest
```

Tests need no Pi, SSH server or network. CI (`build-installers.yml`) runs them in a `pytest` job in addition to the installer builds.

## Contributing

- Keep catalog entries accurate (`check_cmd` / packages / scripts).
- Prefer additive tools that fit authorized research; do not add excluded DoS/critical-infrastructure attack tooling.
- Test both SSH mode and local mode when changing `server.py` job streaming.
- Commits must carry a DCO sign-off (`git commit -s`).

## Roadmap

Planned directions (**not yet implemented or tested**) include multi-Pi fleet management (multi-device targeting, install profiles, inventory, drift detection, unattended provisioning, batch update/rollback) and a native Android app with built-in Pi Imager SD-card flashing that could flash and provision BakerPi onto a Pi over USB-OTG directly from the phone and then fully control the connected Pi from the phone, plus the Raspberry Pi Zero 2 W as an additional planned (untested) target alongside the current Pi Zero 1.3. See [ROADMAP.md](ROADMAP.md) for details.

## License

**No `LICENSE` file is present in this repository.** Add an SPDX license before treating the project as redistributable open source. Until then, default copyright remains with the author; clarify terms before accepting external contributions.

## Credits

Built for the [BakerPi fork of P4wnP1 A.L.O.A.](https://github.com/Victorious93/P4wnP1_aloa), adapted for the Raspberry Pi Zero 1.3. The installer also works with any Raspberry Pi OS system reachable over SSH or USB RNDIS.
