"""Optional scrcpy + adb support: detect, install, list devices, view a screen.

scrcpy (https://github.com/Genymobile/scrcpy) is by Genymobile, Apache-2.0.
BakerPi never bundles scrcpy or adb binaries. It only detects them on PATH and,
when the user explicitly asks (POST /api/scrcpy/install with confirm: true),
installs them with the host platform's normal package manager:

- Debian / Ubuntu / Raspberry Pi OS: ``apt-get install -y scrcpy adb``
  (via ``sudo -n`` when the app is not running as root)
- Windows: ``winget install --exact --id Genymobile.scrcpy``
- macOS: ``brew install scrcpy`` and ``brew install --cask android-platform-tools``

Anything else gets manual-install instructions pointing at the scrcpy repo.
Nothing installs at startup or by default.

Everything runs on the machine hosting the BakerPi Installer server (the PC
with the native window, or the Pi in on-device mode) -- never over SSH. Every
command is a fixed argument list with shell=False; the only user value that
reaches a command line is a device serial, which must pass a strict regex,
must not start with '-', and must be listed by ``adb devices`` as ready.

UNTESTED ON HARDWARE: covered by unit tests with mocked subprocess only. Not
run against a real Android device, a real package manager, or a real Pi.
"""
from __future__ import annotations

import os
import platform
import re
import shutil
import subprocess
import tempfile
import threading
from pathlib import Path
from typing import Iterator, Optional

SCRCPY_URL = "https://github.com/Genymobile/scrcpy"
CREDIT = "scrcpy by Genymobile, Apache-2.0"
APT_PACKAGES = ("scrcpy", "adb")
WINGET_ID = "Genymobile.scrcpy"
BREW_FORMULA = "scrcpy"
BREW_CASK = "android-platform-tools"
DEBIAN_IDS = ("debian", "ubuntu", "raspbian")
MAX_SIZE_LIMIT = 8192

# adb serials: USB serials, emulator-5554, host:port, mDNS names
# (adb-XXXX-abc._adb-tls-connect._tcp). No spaces, no leading '-'.
_SERIAL_RE = re.compile(r"^[A-Za-z0-9._:][A-Za-z0-9._:\-]{0,127}$")
_KV_RE = re.compile(r"^([a-z_]+):(\S+)$")
_VERSION_RE = re.compile(r"(\d+(?:\.\d+)+)")

_install_lock = threading.Lock()


class ScrcpyValidationError(ValueError):
    """User input rejected before anything is executed."""


class ScrcpyUnavailable(RuntimeError):
    """A required program, route or display is missing."""

    def __init__(self, message: str, missing: Optional[list[str]] = None):
        self.missing = missing or []
        super().__init__(message)


class NoInstallRoute(RuntimeError):
    def __init__(self):
        super().__init__("No supported package manager found on this host. "
                         "Install scrcpy and adb manually.")
        self.manual = manual_instructions()


# ── Detection ─────────────────────────────────────────────────────────────────

def _version(cmd: list[str]) -> Optional[str]:
    try:
        r = subprocess.run(cmd, capture_output=True, text=True, timeout=10, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return None
    text = (r.stdout or "") + "\n" + (r.stderr or "")
    first = next((ln.strip() for ln in text.splitlines() if ln.strip()), "")
    m = _VERSION_RE.search(first)
    return m.group(1) if m else (first[:80] or None)


def detect() -> dict:
    scrcpy = shutil.which("scrcpy")
    adb = shutil.which("adb")
    return {
        "scrcpy": {"installed": scrcpy is not None, "path": scrcpy,
                   "version": _version([scrcpy, "--version"]) if scrcpy else None},
        "adb": {"installed": adb is not None, "path": adb,
                "version": _version([adb, "version"]) if adb else None},
    }


def _os_release_ids(path: str = "/etc/os-release") -> set[str]:
    ids: set[str] = set()
    try:
        text = Path(path).read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ids
    for line in text.splitlines():
        key, _, val = line.partition("=")
        if key in ("ID", "ID_LIKE"):
            ids.update(val.strip().strip('"').strip("'").lower().split())
    return ids


def install_route() -> Optional[str]:
    """Return 'apt', 'winget', 'brew' or None for this host."""
    system = platform.system()
    if system == "Linux":
        if _os_release_ids() & set(DEBIAN_IDS) and shutil.which("apt-get"):
            return "apt"
        return None
    if system == "Windows":
        return "winget" if shutil.which("winget") else None
    if system == "Darwin":
        return "brew" if shutil.which("brew") else None
    return None


def manual_instructions() -> dict:
    return {
        "url": SCRCPY_URL,
        "text": ("Install scrcpy and adb (Android platform-tools) by following the "
                 f"official instructions at {SCRCPY_URL} (see its doc/ folder for "
                 "Linux, Windows and macOS), make sure both are on PATH, then "
                 "restart BakerPi Installer."),
    }


def display_available() -> bool:
    if platform.system() != "Linux":
        return True
    return bool(os.environ.get("DISPLAY") or os.environ.get("WAYLAND_DISPLAY"))


def status() -> dict:
    route = install_route()
    st = detect()
    st.update({
        "hardware_tested": False,
        "optional": True,
        "credit": CREDIT,
        "url": SCRCPY_URL,
        "host": {"system": platform.system(), "machine": platform.machine()},
        "busy": _install_lock.locked(),
        "install_route": route,
        "manual": None if route else manual_instructions(),
        "display_available": display_available(),
    })
    return st


# ── Install ───────────────────────────────────────────────────────────────────

def _is_root() -> bool:
    geteuid = getattr(os, "geteuid", None)
    return bool(geteuid) and geteuid() == 0


def build_install_steps(route: str) -> list[list[str]]:
    if route == "apt":
        if _is_root():
            pre: list[str] = []
        elif shutil.which("sudo"):
            pre = ["sudo", "-n"]  # never prompt: fails fast if a password is needed
        else:
            raise ScrcpyUnavailable(
                "apt-get needs root. Run BakerPi Installer as root, or install sudo.",
                missing=["sudo"])
        return [pre + ["apt-get", "update"],
                pre + ["apt-get", "install", "-y", *APT_PACKAGES]]
    if route == "winget":
        return [["winget", "install", "--exact", "--id", WINGET_ID,
                 "--accept-source-agreements", "--accept-package-agreements"]]
    if route == "brew":
        return [["brew", "install", BREW_FORMULA],
                ["brew", "install", "--cask", BREW_CASK]]
    raise ScrcpyValidationError(f"Unknown install route: {route!r}")


def install_env(route: str) -> Optional[dict]:
    if route != "apt":
        return None
    env = dict(os.environ)
    env["DEBIAN_FRONTEND"] = "noninteractive"
    return env


def plan_install(confirm) -> tuple[list[list[str]], Optional[dict]]:
    """Validate and return (steps, env). Executes nothing."""
    if confirm is not True:
        raise ScrcpyValidationError(
            "scrcpy is optional and off by default. Send confirm: true to install it.")
    route = install_route()
    if route is None:
        raise NoInstallRoute()
    return build_install_steps(route), install_env(route)


def acquire() -> bool:
    return _install_lock.acquire(blocking=False)


def _run_step(cmd: list[str], env: Optional[dict]) -> Iterator:
    yield "$ " + " ".join(cmd) + "\n"
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                stdin=subprocess.DEVNULL, text=True, bufsize=1,
                                shell=False, env=env)
    except FileNotFoundError:
        yield f"{cmd[0]} could not be started (not found).\n"
        yield 127
        return
    for line in proc.stdout:
        yield line
    proc.wait()
    yield proc.returncode


def run_steps(steps: list[list[str]], env: Optional[dict] = None) -> Iterator[str]:
    """Run steps in order, stop at the first failure, end with [EXIT n].
    Caller must already hold the install lock; it is released here."""
    rc = 0
    try:
        for cmd in steps:
            for chunk in _run_step(cmd, env):
                if isinstance(chunk, int):
                    rc = chunk
                else:
                    yield chunk
            if rc != 0:
                yield f"\nStep failed (exit {rc}); stopping.\n"
                if cmd[:2] == ["sudo", "-n"]:
                    yield ("sudo needs a password here. Run BakerPi Installer as root, "
                           "or run the commands above yourself in a terminal.\n")
                break
        yield f"\n[EXIT {rc}]\n"
    finally:
        _install_lock.release()


# ── Devices ───────────────────────────────────────────────────────────────────

def parse_adb_devices(text: str) -> list[dict]:
    """Parse ``adb devices -l`` output."""
    devices = []
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("*") or line.startswith("List of devices"):
            continue
        parts = line.split()
        if len(parts) < 2:
            continue
        serial, rest = parts[0], parts[1:]
        if rest[:2] == ["no", "permissions"]:
            state = "no permissions"
        else:
            state = rest[0]
        info = {}
        for tok in rest:
            m = _KV_RE.match(tok)
            if m:
                info[m.group(1)] = m.group(2)
        devices.append({"serial": serial, "state": state,
                        "model": info.get("model"), "product": info.get("product"),
                        "device": info.get("device"), "usb": info.get("usb"),
                        "transport_id": info.get("transport_id"),
                        "ready": state == "device"})
    return devices


def find_adb() -> str:
    adb = shutil.which("adb")
    if not adb:
        raise ScrcpyUnavailable("adb is not installed on this computer.", missing=["adb"])
    return adb


def list_devices() -> list[dict]:
    adb = find_adb()
    try:
        r = subprocess.run([adb, "devices", "-l"], capture_output=True, text=True,
                           timeout=15, shell=False)
    except subprocess.TimeoutExpired:
        raise RuntimeError("adb devices timed out.")
    except OSError as e:
        raise RuntimeError(f"adb could not be started: {e}")
    if r.returncode != 0:
        raise RuntimeError(f"adb devices failed (exit {r.returncode}): "
                           f"{(r.stderr or r.stdout or '').strip()[:300]}")
    return parse_adb_devices(r.stdout)


# ── View ──────────────────────────────────────────────────────────────────────

def validate_serial(serial) -> str:
    if not isinstance(serial, str) or not _SERIAL_RE.fullmatch(serial):
        raise ScrcpyValidationError(
            "Invalid device serial. Use a serial exactly as listed by adb devices.")
    return serial


def validate_max_size(max_size) -> Optional[int]:
    if max_size is None:
        return None
    if isinstance(max_size, bool) or not isinstance(max_size, int) \
            or not 0 <= max_size <= MAX_SIZE_LIMIT:
        raise ScrcpyValidationError(f"max_size must be an integer 0-{MAX_SIZE_LIMIT}.")
    return max_size


def build_view_cmd(scrcpy: str, serial: str, max_size: Optional[int] = None) -> list[str]:
    cmd = [scrcpy, "--serial", validate_serial(serial)]
    max_size = validate_max_size(max_size)
    if max_size:
        cmd += ["--max-size", str(max_size)]
    return cmd


def launch_view(serial, max_size=None, check_secs: float = 1.0) -> dict:
    """Start scrcpy for one ready device without waiting for it to close."""
    serial = validate_serial(serial)
    max_size = validate_max_size(max_size)
    scrcpy = shutil.which("scrcpy")
    if not scrcpy:
        raise ScrcpyUnavailable("scrcpy is not installed on this computer.",
                                missing=["scrcpy"])
    if not display_available():
        raise ScrcpyUnavailable(
            "No graphical display on this computer (DISPLAY / WAYLAND_DISPLAY unset). "
            "scrcpy opens a window on the machine running BakerPi Installer.",
            missing=["display"])
    devices = {d["serial"]: d for d in list_devices()}
    dev = devices.get(serial)
    if dev is None:
        raise LookupError(f"Device {serial} is not connected (not in adb devices).")
    if not dev["ready"]:
        raise PermissionError(f"Device {serial} is '{dev['state']}', not ready. "
                              "Unlock the phone and accept the USB debugging prompt.")
    cmd = build_view_cmd(scrcpy, serial, max_size)
    fd, log_path = tempfile.mkstemp(prefix="bakerpi-scrcpy-", suffix=".log")
    with os.fdopen(fd, "w") as log:
        proc = subprocess.Popen(cmd, stdin=subprocess.DEVNULL, stdout=log,
                                stderr=subprocess.STDOUT, shell=False,
                                start_new_session=True)
    try:
        rc = proc.wait(timeout=check_secs)
    except subprocess.TimeoutExpired:
        return {"launched": True, "pid": proc.pid, "serial": serial,
                "cmd": cmd, "log": log_path}
    try:
        tail = Path(log_path).read_text(errors="replace")[-1500:]
    except OSError:
        tail = ""
    return {"launched": False, "exit_code": rc, "serial": serial, "cmd": cmd,
            "log": log_path, "output": tail}
