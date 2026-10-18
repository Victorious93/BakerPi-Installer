# BakerPi Tool Installer — Roadmap

> **Status: mostly planned / aspirational.**
> Unless an item below says otherwise, it is *planned work only*: not implemented, and not built, tested, or verified on a real Raspberry Pi Zero (or any other hardware). Items marked **Implemented (untested on hardware)** exist in the code and are covered by unit/API tests that use fake command execution, but they have **never been run against a real Pi**. Items may change, be re-scoped, or be dropped. There are no committed timelines.
>
> For what the installer does **today**, see the [README](README.md).

BakerPi Tool Installer is part of the wider *Victorious fleet* of apps. The directions below aim to grow it from a single-device installer into a tool for provisioning and managing several Pis, and to bring it closer to the rest of the fleet on Android.

---

## Multi-Pi fleet management (planned)

| # | Feature | Status |
|---|---|---|
| 1 | Multi-device targeting | Partly implemented (untested on hardware) — manual device inventory + parallel targeting; discovery not implemented |
| 2 | Fleet install profiles | Implemented (untested on hardware) — save / edit / delete / apply; no drift detection |
| 3 | Device inventory + status dashboard | Planned — not implemented |
| 4 | Config sync / drift detection | Planned — not implemented |
| 5 | Headless / unattended provisioning | Planned — not implemented |
| 6 | Batch update + rollback | Planned — not implemented |

### 1. Multi-device targeting in the UI
Discover and list every reachable Pi (over USB OTG and SSH), select one or many, and push installs to the selected devices in parallel.

**Implemented so far (untested on real hardware):** a manually maintained device inventory (SSH, USB-RNDIS or local entries), a Devices panel, and install / update / remove jobs that run on several selected devices in parallel with one log tab per device. **Not implemented:** automatic discovery of devices over USB OTG or the network.

### 2. Fleet install profiles
Save a named toolset once (for example a "recon kit" or "wifi kit") and apply it to any device, so multiple Pis come up with the same set of tools.

**Implemented (untested on real hardware):** a profile is a named, ordered list of tools picked from the catalog, stored per user in `profiles.json` (outside the repo, mode `0600`, no secrets). The Profiles panel creates, edits and deletes profiles, and **Apply to selected device(s)** runs an install job for the profile's tools on the targeted devices, reusing the existing parallel per-device jobs and log tabs (a failure on one device does not stop the others). It is covered by unit/API tests with faked command execution only. **Not implemented:** drift detection or re-sync against a profile (item 4), unattended first-boot provisioning of a profile (item 5), per-device profile assignment, import/export or sharing of profiles, and applying a profile as update/remove.

### 3. Device inventory + status dashboard
A view of known devices showing hostname, IP address, connection type, installed tools, last-seen time, and online/health indicators.

### 4. Config sync / drift detection
Flag when a device no longer matches its assigned profile (tools missing or added), with a one-click re-sync to bring it back in line.

### 5. Headless / unattended provisioning
A config file or manifest flashed onto the SD card, so a fresh Pi can install its assigned profile automatically on first boot without the UI.

### 6. Batch update + rollback
Update a tool across the whole fleet at once, report per-device success/failure, and allow rolling back devices where the update failed.

---

## Native Android app (planned)

| # | Feature | Status |
|---|---|---|
| 7 | Android APK wrapper | Planned — not implemented |
| 8 | Pi Imager (SD-card flashing) | Planned — not implemented |
| 8a | Phone → Pi over USB-OTG: flash → provision → manage | Planned — not implemented |
| 8b | Full control of a connected Pi from the phone | Planned — not implemented |

### 7. Android APK wrapper
A native Android app — in line with the other Android apps in the Victorious fleet — wrapping the existing installer UI. The goal is to add native USB-OTG device control and offline use, going beyond the current "Add to Home Screen" PWA (which remains the supported Android option today). The intent is for the APK not only to manage a Pi that is already set up, but also to install BakerPi onto a fresh Pi directly from the phone (see items 8 and 8a).

### 8. Pi Imager
SD-card flashing built into the app: pick a Raspberry Pi OS image and write it to an SD card over USB-OTG from a phone or PC, then hand off directly to BakerPi's tool installer — flash → provision in one flow. In the Android APK this flashing step is meant to run on the phone itself, so no PC is needed.

### 8a. Phone → Pi over USB-OTG: flash → provision → manage
An end-to-end flow driven entirely from the Android APK, with the phone connected to the Pi over USB-OTG:

1. **Flash** — write a Raspberry Pi OS image from the phone (item 8).
2. **Provision** — once the Pi boots and is reachable from the phone over USB-OTG, install and configure BakerPi and the selected tools onto it from the APK.
3. **Manage** — keep using the same app to install, update, or remove tools on that Pi afterwards.

This extends the APK beyond managing a Pi that has already been configured elsewhere: the goal is to take a blank Pi to a working BakerPi setup using only an Android phone. As with everything on this page, this is planned only — it has not been implemented or tested on any hardware.

### 8b. Full control of a connected Pi from the phone
Drive a connected Pi entirely from the Android APK — natively, over USB-OTG or SSH — mirroring the capabilities the current web UI has:

- run tool installs, updates, and uninstalls;
- view live job output and logs;
- view system information for the Pi;
- start and stop VNC desktop sessions;
- and the other management actions available in the web UI today.

The goal is for the phone to be a complete control surface for a Pi, not just a flashing/provisioning tool. This is planned only — it has not been implemented or tested on any hardware.

---

## Supported hardware (planned)

| # | Target | Status |
|---|---|---|
| 9 | Raspberry Pi Zero 2 W as a supported target | Planned — not implemented, untested |

### 9. Raspberry Pi Zero 2 W
The project currently targets the **Raspberry Pi Zero 1.3** (no onboard Wi-Fi/Bluetooth; USB-OTG only), and that remains the only target today. Support for the **Raspberry Pi Zero 2 W** is planned as an additional target. The Zero 2 W is a different, more capable board — quad-core CPU plus onboard Wi-Fi and Bluetooth, which the Zero 1.3 lacks — so support is **not** automatic. It has not been implemented or tested on Zero 2 W hardware, and the Zero 2 W should not be considered supported until it has been.

---

## Contributing to the roadmap

Ideas, feedback, and design discussion are welcome via issues or pull requests. If you start work on any item, please note it in an issue first so effort isn't duplicated, and keep the status here accurate — only mark something as available once it has actually been implemented and tested.
