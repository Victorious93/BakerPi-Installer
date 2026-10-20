# BakerPi Tool Installer: User Manual

This is a plain-language guide to what BakerPi Tool Installer does today and how to use it. It covers only features that exist in the code (`server.py`, `launcher.py`, `static/index.html`, `device_registry.py`, `profile_registry.py`). Planned features are listed as planned.

> **Hardware status:** The app targets a **Raspberry Pi Zero 1.3**. Anything in this manual about a real Pi Zero (USB-OTG networking, install scripts running on the Pi, VNC desktops, temperatures, multi-device runs) is **untested on hardware** for this manual. Device inventory and fleet profiles in particular have only been checked with faked commands in unit/API tests.

Screenshots are not included yet. Each spot marked `[SCREENSHOT PLACEHOLDER: …]` shows where one should go.

---

## 1. What BakerPi Tool Installer is

BakerPi Tool Installer is a small app with a web interface. It installs, updates and removes tools on a Raspberry Pi running **BakerPi**, the P4wnP1 A.L.O.A. fork adapted for the Pi Zero 1.3. You choose tools from a catalog (`tools/catalog.json`, 13 categories, including Kali and Parrot "OS environment" overlays). The app then runs the matching shell commands on the Pi.

It can run in three ways. All three use the same code:

| Way to run | What it is | Listens on |
|---|---|---|
| `server.py` (or `run_pc.*`, `run_ondevice.sh`) | A FastAPI web server; you use it from a browser | `0.0.0.0:8080` (all network interfaces) |
| `launcher.py` (or `run_app.*`, or the built binary) | The same server, shown in a native desktop window (pywebview) | `127.0.0.1` only, first free port from 8080 |
| On the Pi itself (`--mode local`) | The server runs commands directly on the Pi | `0.0.0.0:8080` |

### Fleet role: `HOST_PROCESS_TOOL`

In Don Victor's Victorious fleet, BakerPi Installer is classed as **`HOST_PROCESS_TOOL`**. It is a process on a host machine (PC or Pi) that serves localhost HTTP and has command-line entry points. Its only outbound link is to the Pi, over SSH (usually over USB RNDIS/OTG). It is **not** a service inside a Pi payload, and it is **not** a mobile app. No Android APK exists; the only Android option is the PWA (see §3.13).

---

## 2. Install and setup

### 2.1 Requirements

- Python 3 and `pip3 install -r requirements.txt` (FastAPI, uvicorn, paramiko, aiofiles, python-multipart, pywebview).
- For the native window on Linux: `libwebkit2gtk-4.0-dev`, `libgtk-3-dev` (and `libglib2.0-dev` when building).
- The target: a Raspberry Pi Zero 1.3 running Raspberry Pi OS Lite (Bookworm recommended), a microSD card of at least 8 GB (32 GB or more for OS environments), and a USB data cable to the Pi's OTG port. *(Untested on hardware.)*

### 2.2 Get the app

**From source:**

```bash
git clone https://github.com/Victorious93/BakerPi-Installer
cd BakerPi-Installer
pip3 install -r requirements.txt
```

**Pre-built binaries:** CI (`.github/workflows/release.yml`) is set up to publish a Linux AppImage and Windows EXE/installer on `v*` tags. **No release has been published yet**, so build from source for now.

**Build your own binary:** `./build_app.sh` (Linux/macOS) or `build_app.bat` (Windows). These run PyInstaller with `bakerpi_installer.spec` and output `dist/BakerPi_Installer`. `build_app.sh` also builds an AppImage if `appimagetool` is installed. Windows installers use Inno Setup (`installer.iss`).

### 2.3 Start the native window (recommended on a PC)

```bash
./run_app.sh --mode ssh            # Linux/macOS
run_app.bat --mode ssh             # Windows
python3 launcher.py --mode ssh --host 172.16.0.1 --user root
```

1. A window opens showing "Starting server — please wait…".
2. When the server is ready, the window loads the full UI.
3. If the server does not start within 30 seconds, the window shows "Server failed to start."

> **Important:** `launcher.py` defaults to `--mode local`, meaning it runs commands **on the computer it was started on**. The comments in `run_app.*` say otherwise, but the code is what counts. To control a Pi from a PC, always pass `--mode ssh`.

Launcher options: `--mode`, `--host` (default `172.16.0.1`), `--user` (default `root`), `--port` (SSH, default 22), `--password`, `--key-file`, `--devices-file`, `--profiles-file`, `--server-port` (0 = pick automatically).

`[SCREENSHOT PLACEHOLDER: native window loading splash]`

### 2.4 Start the browser (server) mode

```bash
./run_pc.sh                         # PC → Pi over SSH, opens http://localhost:8080
run_pc.bat                          # Windows
python3 server.py --mode ssh --host 172.16.0.1 --user root
```

`server.py` has the same options as the launcher, plus `--server-port` (default 8080) and `--no-browser`. In SSH mode it opens your browser after about 1.5 seconds unless you pass `--no-browser`.

### 2.5 Connecting to the Pi

**Over USB-OTG (USB RNDIS / CDC-ECM gadget networking).** *Untested on hardware.* Plug the Pi Zero's **USB data** port (not the power-only port) into the PC. With BakerPi's USB gadget networking, the Pi is expected at `172.16.0.1`, which is the app's default host. The app does not set up the USB link itself; it just opens SSH to that address.

**Over SSH (any network).** Pass `--host <ip> --user <user>` at startup, or use the **⚙ SSH** panel in the UI (§3.10). Authentication can use a password, a key file (`--key-file`), or your SSH agent/default keys.

**On the Pi itself.** Copy the app to the Pi and run `sudo ./run_ondevice.sh` (or `sudo python3 server.py --mode local --no-browser`). Then browse from a phone or PC to `http://172.16.0.1:8080`. *(Untested on hardware.)*

> **Install scripts in SSH mode:** For tools that use an install script, the app runs `bash /usr/local/BakerPi/tool_installer/install_scripts/<script>` **on the Pi**. It does **not** copy the scripts there. If that folder is missing on the Pi, those tools fail; apt-only tools still work. In local mode, the scripts run from the app's own `install_scripts/` folder.

---

## 3. Features, step by step

`[SCREENSHOT PLACEHOLDER: main window overview: top bar, sidebar, tool grid]`

### 3.1 Top bar and system info

The top bar shows a connection dot (**Local**, **SSH** or **Disconnected**), then the viewed device's label, hostname, memory used/total, disk used/total, and CPU temperature (read from `/sys/class/thermal/thermal_zone0/temp`). The server also reports uptime, CPU MHz, architecture and OS version (`GET /api/system`), but the top bar does not show those.

Buttons on the right: **📦 Profiles**, **🖧 Devices**, **⚙ SSH**, **❓ Help**, and **☀ Light / Dark** (theme toggle).

### 3.2 Browse the catalog

1. Click a category in the left sidebar, or **All Tools**. Each category shows a count of installed/total tools.
2. Type in **Search tools…** to filter. Press **/** anywhere to jump to the search box.
3. Use the pills **All / ✓ Installed / ○ Not installed** to filter by status.
4. Click **↻ Refresh** to re-check the install status of every tool on the viewed device. The app uses `dpkg -l` for packages, otherwise the tool's `check_cmd`.

On phones (screens 480 px wide or less), the sidebar is hidden.

`[SCREENSHOT PLACEHOLDER: category sidebar and status filter pills]`

### 3.3 Install one tool

1. Find the tool card and click **Install**.
2. A log window opens and streams the command output live (see §3.7).
3. When it finishes, the card's status updates.

Built-in tools (BakerPi core) only print a message, because the BakerPi core service already provides them.

### 3.4 Install, update or remove several tools at once (batch)

1. Tick the checkbox on each tool card you want.
2. A selection bar appears with the count.
3. Click **⬇ Install Selected**, **↑ Update Selected**, or **✕ Remove Selected**. Click **Clear** to deselect all.
4. One job runs the tools in order. If one tool fails, the job logs the error and moves on to the next.

### 3.5 Update tools

- **Single tool:** click **↑ Update** on an installed tool's card.
- **Everything installed:** click **↑ Update All** in the toolbar. On each target device, the server finds the installed (non-built-in) tools and updates them. Devices with nothing installed are skipped.

How a tool is updated: the catalog's `update_cmd` if it has one. Otherwise the install script is called with `update`. Otherwise `apt-get update` is run, then `apt-get install --only-upgrade` for the tool's packages.

### 3.6 Remove (uninstall) tools

Click **✕ Remove** on a card, or use **Remove Selected**. The app uses the catalog's `uninstall_cmd` if there is one. Otherwise it runs `apt-get remove` plus `autoremove` for apt packages, `pip3 uninstall` for Python modules, or disables the service and deletes `/opt/<dir>` for git-cloned tools. If it cannot work out how to remove a tool, it prints a hint instead. Built-in tools cannot be removed (the server refuses with an error).

> Removal can delete files under `/opt/` on the Pi. Check what you selected before confirming.

### 3.7 Live install logs

Every install, update or remove job opens a log window that streams output live (server-sent events from `/api/jobs/{id}/stream`).

- Each command is shown as `$ <command>` before its output.
- Each tool is framed with a `=====` header; the job ends with `[DONE] … complete.` or `… finished with errors.`
- With several target devices, there is **one tab per device**, each with a status dot.
- Press **Esc**, click **×** or **Close**, or click outside the window to close it. Closing the window does **not** stop the job.

Logs live in memory only and are lost when the app restarts. There is **no cancel button** and no log export.

`[SCREENSHOT PLACEHOLDER: live log window with per-device tabs]`

### 3.8 Desktop (VNC) control

This applies after you install a Kali + XFCE or Parrot + MATE OS environment. *(Untested on hardware.)*

1. In the **Desktop (VNC) Control** panel, choose a resolution (1280×800, 1024×768, 1920×1080, 800×600).
2. Click **▶ Start Desktop**. The app runs `vncserver :1 -geometry <size> -depth 24 -localhost no` on the viewed device.
3. The panel shows the address (`<pi-ip>:5901`). Connect with any VNC client.
4. The default VNC password set by the install script is **`bakerpi`**. Change it on the Pi with `vncpasswd`.
5. Click **■ Stop Desktop** to stop it, or **↻** to re-check its status.

The app does not include a VNC viewer; you need a separate VNC client. VNC follows the *viewed* device only.

`[SCREENSHOT PLACEHOLDER: VNC panel running with address]`

### 3.9 Manage several devices (device inventory and targeting)

*Untested on real hardware; checked only with faked commands in tests.*

1. Click **🖧 Devices** in the top bar.
2. Click **+ Add device**. Enter a **Label**, a **Type** (`ssh`, `usb-rndis` or `local`), and for remote types a **Host**, **User**, **SSH port** and optional **Key file** path. `usb-rndis` defaults the host to `172.16.0.1`. Click **Save**.
3. Tick **T** (Target) on every device that Install / Update / Remove / Update All should run on. Jobs run on all targets **in parallel**.
4. Pick **V** (Viewing) to choose which device's tool status, system info and VNC panel are shown.
5. Click **⚡ Connect** on an SSH device. Optionally enter a password (kept in memory only), then press Enter or **Connect**.
6. Use **Edit** or **✕** to change or remove a device.

The built-in **default** device comes from the command-line options. It is always present and cannot be edited or removed.

`[SCREENSHOT PLACEHOLDER: Devices panel with T/V columns]`

### 3.10 Legacy SSH panel

Click **⚙ SSH**, enter Host / User / Port / Password, then click **Connect**. This re-points the **default** device to that host. This panel has no key-file field; to use a key file, start the app with `--key-file` or add a registry device that has a key path.

### 3.11 Fleet install profiles

*Untested on real hardware; checked only with faked commands in tests.*

1. Click **📦 Profiles**, then **+ New profile**.
2. Enter a **Name** (required, up to 64 characters, must be unique) and an optional **Description** (up to 500 characters).
3. Pick tools in the filterable list, or click **Use grid selection** to copy the tools ticked in the grid. The order you pick them in is the install order. Click **Save**.
4. To use a profile, click **⬇ Apply to selected device(s)** and confirm. This installs the profile's tools, in order, on the current target devices.
5. Use **Edit** or **✕** to change or delete a profile.

Applying a profile only *installs*. It never updates or removes anything. If a profile contains a tool that is no longer in the catalog, its Apply button is disabled until you edit the profile.

`[SCREENSHOT PLACEHOLDER: Profiles panel and profile editor]`

### 3.12 Help / Manual view

Click **❓ Help** in the top bar to read this manual inside the app. The manual is served read-only from `GET /api/manual`. Click **Close** or press **Esc** to return.

### 3.13 Android (PWA)

*Untested on hardware.* With the Pi running `run_ondevice.sh`, open Chrome on the phone at `http://172.16.0.1:8080`, then choose **Menu → Add to Home Screen**. This is a web shortcut, not a native app.

### 3.14 Light/dark theme

Click **☀ Light** / **🌙 Dark** to switch themes. Your choice is saved in the browser's local storage.

### 3.15 HTTP API

Everything in the UI is also available as a JSON API (catalog, tools, install/update/uninstall/update-all, jobs, system, devices, profiles, VNC, SSH, manual, ESP32 flashing). FastAPI's auto-generated docs are at `/docs` on the running server. See the README for the endpoint tables.

### 3.16 ESP32 flashing (esptool)

> **Untested on hardware.** This feature is covered by automated tests with mocked serial ports and a mocked `esptool` process only. It has **not** been verified against a real ESP32 board yet. Treat it as experimental.

The **⚡ ESP32 Flashing** entry under **Flashing** in the sidebar writes a firmware image to an ESP32 using [esptool](https://github.com/espressif/esptool).

**Where the board goes:** plug the ESP32 into **the computer running BakerPi Installer** (your PC in native/launcher mode, or the Pi itself when using `run_ondevice.sh`). Flashing always runs locally on that machine; it does **not** go over SSH to a remote Pi.

**Before you start:** install esptool on that computer: `pip install esptool` (this also installs `pyserial`, which gives better port names). If esptool is missing, the panel says so and the Flash button returns an error instead of running anything. Pre-built binaries do not bundle esptool; it must be on your `PATH`.

**Steps:**

1. Click **⚡ ESP32 Flashing** in the sidebar.
2. Pick the **Serial port** (click **↻** to rescan after plugging the board in). Typical names: `/dev/ttyUSB0` or `/dev/ttyACM0` (Linux), `/dev/cu.usbserial-…` (macOS), `COM3` (Windows).
3. Pick the **Chip** (`auto` lets esptool detect it) and **Baud** (default 460800; drop to 115200 if flashing is unreliable).
4. Enter the **Flash address** in hex. Default `0x10000` is the usual application offset for ESP-IDF/Arduino builds; a merged/factory image usually goes at `0x0`. Addresses must be 4 KB aligned and below 16 MB.
5. Choose the **Firmware** `.bin` file (max 16 MB) and click **⚡ Flash**. esptool's output streams into the panel; the run ends with `[EXIT 0]` on success.

Some boards need you to hold **BOOT** while flashing starts. Writing the wrong image or address can leave the board unbootable until you flash a correct image.

**Safety and validation:** port, chip, baud and address are checked against strict allowlists/patterns, and esptool is run as an argument list (never through a shell). The uploaded firmware is written to a temporary file and deleted after the run.

**API:** `GET /api/esp32/status`, `GET /api/esp32/ports`, `POST /api/esp32/flash` (multipart form: `port`, `chip`, `baud`, `address`, `firmware`; streams plain-text output).

This is ESP32 feature 1 of 4; more ESP32 features are planned.

### 3.18 ESP32 dev toolchain (ESP-IDF, Arduino-CLI)

> **Untested on hardware.** Covered by automated tests with a mocked `subprocess` only. These installs change the host system and have **not** been verified end-to-end on a real Pi Zero. Treat as experimental.

The **Dev Toolchain** area at the bottom of the **⚡ ESP32 Flashing** panel installs an ESP32 development toolchain onto **the computer running BakerPi Installer** (the Pi itself with `run_ondevice.sh`, or your PC). It never runs over SSH on a remote Pi.

**What it installs**

- **ESP-IDF**: `git clone --depth 1 --branch <version> --recursive` of `espressif/esp-idf` into `~/esp/esp-idf` (override the parent folder with `BAKERPI_ESP_DIR`), then runs its `install.sh <targets>`, which downloads compilers into `~/.espressif`. If `~/esp/esp-idf/install.sh` already exists the clone is skipped. Pick a release tag (default `v5.3.1`) and a chip target (`esp32`, `esp32s3`, …, or `all`). Afterwards, in a terminal, run `. ~/esp/esp-idf/export.sh` before using `idf.py`.
- **Arduino-CLI**: downloads the official `install.sh` with `curl` to a temp file, runs it with `BINDIR=~/.local/bin`, and (if **+ esp32 core** is ticked) runs `arduino-cli core update-index` and `core install esp32:esp32` with Espressif's board index URL. Add `~/.local/bin` to your `PATH`.

**Host requirements and permissions:** Linux or macOS (Windows is refused: use the official Espressif / Arduino installers). ESP-IDF needs `git`, `python3` and `bash`; Arduino-CLI needs `curl` and `sh`. If any is missing, the panel lists it and the install returns HTTP 424 without running anything. No root/sudo is used: everything goes into the home directory of the user running the app. It needs internet access and a lot of disk space.

**Pi Zero performance caveat:** ESP-IDF plus its tools is roughly 1–2 GB. On a Pi Zero (single-core ARMv6, 512 MB RAM) cloning and installing can take an hour or more, may run out of disk or memory, and may fail outright if Espressif ships no toolchain for `armv6l`. Arduino-CLI is much smaller, but the esp32 core download is still several hundred MB. Prefer installing on a PC if you can.

**Status:** green dot = installed (ESP-IDF: `~/esp/esp-idf/tools/idf.py` exists; Arduino-CLI: `arduino-cli` on `PATH` or in `~/.local/bin`, plus whether `esp32:esp32` shows in `arduino-cli core list`).

**Safety:** every step runs as an argument list with `shell=False`. The upstream shell scripts are started as `bash <fixed path>` / `sh <temp file>` with no user text interpolated. The version must match `vN.N[.N]` and targets come from a fixed allowlist. Only one toolchain install runs at a time (HTTP 409 otherwise). Steps stop at the first failure.

**API:** `GET /api/esp32/toolchain/status`; `POST /api/esp32/toolchain/install` with JSON `{"item": "esp-idf"|"arduino-cli", "version": "v5.3.1", "targets": ["esp32"], "with_esp32_core": true}`. It streams plain-text output that ends with `[EXIT n]`.

This is ESP32 feature 3 of 4.

### Not available today

These are **not** in the code: automatic device discovery, a side-by-side fleet status dashboard, drift detection or re-sync, unattended first-boot provisioning, rollback, job cancel or retry, log export, saved passwords, SSH host-key pinning, a built-in VNC viewer, SD-card flashing (Pi Imager), a native Android app, and Pi Zero 2 W support. See [ROADMAP.md](../ROADMAP.md).

---

## 4. Permissions and access, and why

| What | Why |
|---|---|
| **Root on the Pi** (default SSH user `root`; `sudo` for on-device mode) | Commands such as `apt-get install`, writing under `/opt`, `systemctl`, and `vncserver` need root. The app runs commands exactly as given and does not add `sudo` for you. If you log in as a non-root user, many installs fail. |
| **SSH access to the Pi** | This is the only way PC mode talks to the Pi. |
| **Network listening** | `server.py` binds **`0.0.0.0`** (all interfaces) with **no authentication**. That is deliberate, so a phone can reach an on-device server at `172.16.0.1:8080`. It also means **anyone who can reach that port on your network can install or remove software and run VNC on your Pi**. Use it only on trusted networks, or use the launcher instead. |
| **Native window** | `launcher.py` binds **`127.0.0.1` only**, so other machines cannot reach it. |
| **Local files** | The app reads and writes `devices.json` and `profiles.json` in your user config folder (§7). |
| **SSH host keys** | Unknown host keys are **auto-accepted** (Paramiko `AutoAddPolicy`). This is convenient for a USB-attached Pi, but it does not protect you from man-in-the-middle attacks on untrusted networks. |
| **Serial ports (ESP32 flashing)** | Flashing opens the board's USB serial port on the computer running the app. On Linux your user usually needs to be in the `dialout` group (`sudo usermod -aG dialout $USER`, then log out and back in), or the port open fails with "Permission denied". Windows may need the CP210x/CH340 USB-serial driver. *Untested on hardware.* |
| **VNC** | `vncserver` is started with `-localhost no`, so port 5901 is open on the Pi's network interfaces, protected only by the VNC password (default `bakerpi`). |

The catalog's security tools (nmap, aircrack-ng, Metasploit, …) are for **authorized** testing and research only.

---

## 5. Fleet integration: what exists and what doesn't

**Exists (untested on hardware):**
- Fleet class `HOST_PROCESS_TOOL`: a host process with an HTTP UI/API and CLI entry points.
- A manual device inventory with parallel install/update/remove/update-all across target devices, one log tab per device, and failures isolated per device.
- Fleet install profiles (save, edit, delete, apply).
- A JSON HTTP API that other local tools can call (no auth; see §4).

**Does not exist:**
- No connection to other Victorious fleet apps (no shared accounts, sync, message bus, webhooks or telemetry).
- No device discovery, fleet dashboard, drift detection, unattended provisioning, or rollback.
- No Android APK, and no app-signing key in the repo. CI does not code-sign the binaries.
- Status views (tool status, system info, VNC) cover one device at a time (the *viewed* device).

---

## 6. Troubleshooting and FAQ

**The top bar says "Disconnected".**
SSH is not connected. Open **⚙ SSH** or **🖧 Devices → Connect**. Check that the cable is in the Pi's *USB data* port and that `ping 172.16.0.1` works *(untested on hardware)*. Check the user/password or key. The connection timeout is 15 seconds.

**Install says `[ERROR] SSH not connected` or `Could not connect to …`.**
Same as above. Jobs try to reconnect once using the remembered in-memory credentials, key, or SSH agent.

**Script-based tools fail with "No such file" over SSH.**
The scripts are expected at `/usr/local/BakerPi/tool_installer/install_scripts/` on the Pi. Copy the repo's `install_scripts/` there, or run the app on the Pi with `--mode local`.

**Installs fail with permission errors.**
Connect as `root`, or run on-device mode with `sudo`.

**The launcher controls my PC instead of the Pi.**
You started it without `--mode ssh`. The launcher's default is `local`.

**"Server failed to start" in the native window.**
The window gave up after 30 seconds. Something may be using the port; try `--server-port 8090`. On Linux, check that the WebKit/GTK packages are installed.

**Port 8080 is already in use (server mode).**
Use `--server-port <other>`.

**My devices or profiles disappeared.**
If the JSON file was unreadable, the app moved it to `devices.json.bad` / `profiles.json.bad` and started empty. Fix or restore the file from there.

**A profile's Apply button is greyed out.**
The profile references a tool that is no longer in the catalog. Edit the profile to remove it.

**VNC start fails.**
Install a Kali XFCE or Parrot MATE OS environment first, then check the error message shown in the toast. *(Untested on hardware.)*

**Can I cancel a running job?** No. Closing the log window does not stop the job.

**Are logs saved?** No. They live in memory only and are lost on restart.

**Does it support the Pi Zero 2 W?** Not yet; it is planned and untested.

**Is there an Android app?** No. Use the PWA (§3.13).

---

## 7. Privacy and data handling

- **No telemetry, analytics, or accounts.** The app contacts only the Pi(s) you connect to. Package downloads (apt, pip, git) happen *on the Pi*, from the sources defined by the install commands.
- **Passwords** are kept **in memory only** for the session and are never written to disk. Passing `--password` on the command line can leave it in your shell history and process list; prefer keys or the UI.
- **`devices.json`** stores the label, type, host, user, port, and key-file *path* (not the key itself). **`profiles.json`** stores only names, descriptions and tool ids. Both are written with mode `0600` and are in `.gitignore`.
  - Linux: `$XDG_CONFIG_HOME/BakerPi-Installer/` (default `~/.config/BakerPi-Installer/`)
  - macOS: `~/Library/Application Support/BakerPi-Installer/`
  - Windows: `%APPDATA%\BakerPi-Installer\`
  - You can override these with `--devices-file` / `--profiles-file` or `BAKERPI_DEVICES_FILE` / `BAKERPI_PROFILES_FILE`.
- **Job logs** stay in memory and disappear on restart. Server log lines (such as "SSH connected to user@host") go to the console only.
- **Theme preference** is stored in the browser/webview local storage.
- **Network exposure:** in server mode, anyone on your network can reach the UI and API with no login (see §4).
