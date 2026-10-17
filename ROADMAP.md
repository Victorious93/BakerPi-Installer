# BakerPi Tool Installer — Roadmap

> **Status: planned / aspirational.**
> Everything on this page is *planned work only*. **None of it is implemented yet**, and nothing here has been built, tested, or verified on a real Raspberry Pi Zero (or any other hardware). Items may change, be re-scoped, or be dropped. There are no committed timelines.
>
> For what the installer does **today**, see the [README](README.md).

BakerPi Tool Installer is part of the wider *Victorious fleet* of apps. The directions below aim to grow it from a single-device installer into a tool for provisioning and managing several Pis, and to bring it closer to the rest of the fleet on Android.

---

## Multi-Pi fleet management (planned)

| # | Feature | Status |
|---|---|---|
| 1 | Multi-device targeting | Planned — not implemented |
| 2 | Fleet install profiles | Planned — not implemented |
| 3 | Device inventory + status dashboard | Planned — not implemented |
| 4 | Config sync / drift detection | Planned — not implemented |
| 5 | Headless / unattended provisioning | Planned — not implemented |
| 6 | Batch update + rollback | Planned — not implemented |

### 1. Multi-device targeting in the UI
Discover and list every reachable Pi (over USB OTG and SSH), select one or many, and push installs to the selected devices in parallel.

### 2. Fleet install profiles
Save a named toolset once (for example a "recon kit" or "wifi kit") and apply it to any device, so multiple Pis come up with the same set of tools.

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

### 7. Android APK wrapper
A native Android app — in line with the other Android apps in the Victorious fleet — wrapping the existing installer UI. The goal is to add native USB-OTG device control and offline use, going beyond the current "Add to Home Screen" PWA (which remains the supported Android option today).

### 8. Pi Imager
SD-card flashing built into the app: pick a Raspberry Pi OS image and write it to an SD card over USB-OTG from a phone or PC, then hand off directly to BakerPi's tool installer — flash → provision in one flow.

---

## Contributing to the roadmap

Ideas, feedback, and design discussion are welcome via issues or pull requests. If you start work on any item, please note it in an issue first so effort isn't duplicated, and keep the status here accurate — only mark something as available once it has actually been implemented and tested.
