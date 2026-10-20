"""ESP32 firmware flashing helpers (esptool wrapper).

The ESP32 must be plugged into the machine running the BakerPi Installer
server (not a remote Pi reached over SSH). esptool always runs as a list-form
subprocess, never through a shell, and every user input is checked against a
strict allowlist / regex before it reaches the command line.

UNTESTED ON HARDWARE: command construction, validation and output streaming
are covered by unit tests with mocks only. Nothing here has been verified
against a real ESP32 board yet.
"""
from __future__ import annotations

import glob
import importlib.util
import re
import shutil
import subprocess
import sys
from typing import Iterator, Optional

# Chips esptool understands (``--chip``). "auto" lets esptool detect it.
ALLOWED_CHIPS = ("auto", "esp32", "esp32s2", "esp32s3", "esp32c2", "esp32c3",
                 "esp32c6", "esp32h2", "esp8266")
ALLOWED_BAUDS = (9600, 57600, 115200, 230400, 460800, 921600, 1500000, 2000000)
DEFAULT_BAUD = 460800
DEFAULT_ADDRESS = "0x10000"     # typical app offset for ESP-IDF / Arduino builds
MAX_FLASH_BYTES = 16 * 1024 * 1024  # largest common ESP32 flash (16 MB)
MAX_FIRMWARE_BYTES = MAX_FLASH_BYTES
ALLOWED_EXTENSIONS = (".bin",)

# Linux USB-serial, macOS callout/tty devices, Windows COM ports.
_PORT_RE = re.compile(
    r"^(?:/dev/tty(?:USB|ACM|AMA|S)\d{1,3}"
    r"|/dev/(?:cu|tty)\.[A-Za-z0-9_\-.]{1,64}"
    r"|COM\d{1,3})$"
)
_ADDR_RE = re.compile(r"^0x[0-9a-fA-F]{1,8}$")


class FlashValidationError(ValueError):
    """User input rejected before anything is executed."""


class EsptoolNotFound(RuntimeError):
    """esptool is not installed / not on PATH."""


# ── Validation ────────────────────────────────────────────────────────────────

def validate_port(port: str) -> str:
    if not isinstance(port, str) or not _PORT_RE.fullmatch(port):
        raise FlashValidationError(
            "Invalid serial port. Expected e.g. /dev/ttyUSB0, /dev/ttyACM0, "
            "/dev/cu.usbserial-0001 or COM3.")
    return port


def validate_chip(chip: str) -> str:
    if chip not in ALLOWED_CHIPS:
        raise FlashValidationError(f"Invalid chip. Allowed: {', '.join(ALLOWED_CHIPS)}")
    return chip


def validate_baud(baud) -> int:
    s = str(baud)
    b = int(s) if re.fullmatch(r"[0-9]{1,7}", s) else None
    if b not in ALLOWED_BAUDS:
        raise FlashValidationError(
            f"Invalid baud rate. Allowed: {', '.join(map(str, ALLOWED_BAUDS))}")
    return b


def validate_address(address: str) -> str:
    if not isinstance(address, str) or not _ADDR_RE.fullmatch(address):
        raise FlashValidationError("Invalid flash address. Use hex like 0x10000.")
    value = int(address, 16)
    if value >= MAX_FLASH_BYTES:
        raise FlashValidationError("Flash address is beyond 16 MB.")
    if value % 0x1000:
        raise FlashValidationError("Flash address must be 4 KB (0x1000) aligned.")
    return f"0x{value:x}"


def validate_firmware(filename: Optional[str], size: int, address: str = "0x0") -> None:
    name = (filename or "").lower()
    if not name.endswith(ALLOWED_EXTENSIONS):
        raise FlashValidationError("Firmware must be a .bin file.")
    if size <= 0:
        raise FlashValidationError("Firmware file is empty.")
    if size > MAX_FIRMWARE_BYTES:
        raise FlashValidationError("Firmware file is larger than 16 MB.")
    if int(address, 16) + size > MAX_FLASH_BYTES:
        raise FlashValidationError("Firmware does not fit in 16 MB at that address.")


# ── esptool discovery / ports ────────────────────────────────────────────────

def find_esptool() -> Optional[list[str]]:
    """Command prefix that runs esptool, or None if it isn't installed."""
    for name in ("esptool", "esptool.py"):
        path = shutil.which(name)
        if path:
            return [path]
    # `python -m esptool` only works when running from source (not frozen builds).
    if not getattr(sys, "frozen", False) and importlib.util.find_spec("esptool"):
        return [sys.executable, "-m", "esptool"]
    return None


def list_serial_ports() -> list[dict]:
    """Serial ports visible to this machine. Uses pyserial when available."""
    try:
        from serial.tools import list_ports  # pyserial (installed with esptool)
    except ImportError:
        list_ports = None
    if list_ports is not None:
        return [{"device": p.device, "description": p.description or "",
                 "hwid": p.hwid or ""}
                for p in sorted(list_ports.comports(), key=lambda p: p.device)]
    found = []
    for pattern in ("/dev/ttyUSB*", "/dev/ttyACM*", "/dev/cu.*"):
        found.extend(sorted(glob.glob(pattern)))
    return [{"device": d, "description": "", "hwid": ""} for d in found]


def build_flash_cmd(esptool_cmd: list[str], port: str, chip: str, baud: int,
                    address: str, firmware_path: str) -> list[str]:
    """Validated, list-form esptool write_flash command (never shell=True)."""
    return [*esptool_cmd,
            "--chip", validate_chip(chip),
            "--port", validate_port(port),
            "--baud", str(validate_baud(baud)),
            "write_flash", validate_address(address), firmware_path]


def stream_flash(cmd: list[str]) -> Iterator[str]:
    """Run esptool and yield its output line by line, then an [EXIT n] marker."""
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, shell=False)
    except FileNotFoundError:
        yield "esptool could not be started (not found).\n\n[EXIT 127]\n"
        return
    for line in proc.stdout:
        yield line
    proc.wait()
    yield f"\n[EXIT {proc.returncode}]\n"


# ── Detection / device info (ESP32 feature 2) ───────────────────────────────
# UNTESTED ON HARDWARE: the regexes below were written against esptool's
# documented/sample output (v4 "Chip is ..." and v5 "Chip type: ..." styles)
# and are exercised only with canned output in tests/test_esp32_detect.py.

# esptool read-only info commands we allow. flash_id also prints chip/MAC.
ALLOWED_INFO_OPS = ("flash_id", "read_mac", "chip_id")
DEFAULT_INFO_OP = "flash_id"
INFO_TIMEOUT_S = 45

# Common USB-serial bridges seen on ESP32 dev boards (VID:PID -> label).
KNOWN_USB_BRIDGES = {
    "10C4:EA60": "Silicon Labs CP210x",
    "1A86:7523": "WCH CH340",
    "1A86:55D4": "WCH CH9102",
    "0403:6001": "FTDI FT232R",
    "0403:6010": "FTDI FT2232",
    "303A:1001": "Espressif USB-JTAG/serial (native USB)",
    "303A:0002": "Espressif USB CDC (ESP32-S2/S3)",
}


def validate_info_op(op: str) -> str:
    if op not in ALLOWED_INFO_OPS:
        raise FlashValidationError(f"Invalid operation. Allowed: {', '.join(ALLOWED_INFO_OPS)}")
    return op


def _fmt_id(v) -> str:
    return f"{v:04X}" if isinstance(v, int) else ""


def list_usb_devices() -> dict:
    """Serial devices with USB detail where pyserial exposes it.

    Returns {"pyserial": bool, "devices": [...]}; without pyserial, falls back
    to the bare glob list from list_serial_ports() with empty USB fields.
    """
    try:
        from serial.tools import list_ports
    except ImportError:
        list_ports = None
    devices = []
    if list_ports is None:
        for p in list_serial_ports():
            devices.append({"device": p["device"], "description": p["description"],
                            "hwid": p["hwid"], "vid": "", "pid": "", "vid_pid": "",
                            "manufacturer": "", "product": "", "serial_number": "",
                            "location": "", "usb": False, "likely_esp32": False,
                            "bridge": ""})
        return {"pyserial": False, "devices": devices}
    for p in sorted(list_ports.comports(), key=lambda p: p.device):
        vid, pid = _fmt_id(getattr(p, "vid", None)), _fmt_id(getattr(p, "pid", None))
        vp = f"{vid}:{pid}" if vid and pid else ""
        bridge = KNOWN_USB_BRIDGES.get(vp, "")
        devices.append({
            "device": p.device,
            "description": getattr(p, "description", "") or "",
            "hwid": getattr(p, "hwid", "") or "",
            "vid": vid, "pid": pid, "vid_pid": vp,
            "manufacturer": getattr(p, "manufacturer", None) or "",
            "product": getattr(p, "product", None) or "",
            "serial_number": getattr(p, "serial_number", None) or "",
            "location": getattr(p, "location", None) or "",
            "usb": bool(vp),
            # Heuristic only: a known bridge does not prove an ESP32 is attached.
            "likely_esp32": bool(bridge),
            "bridge": bridge,
        })
    return {"pyserial": True, "devices": devices}


def build_info_cmd(esptool_cmd: list[str], port: str, op: str = DEFAULT_INFO_OP,
                   chip: str = "auto", baud: int = 115200) -> list[str]:
    """Validated list-form read-only esptool command (never shell=True)."""
    return [*esptool_cmd, "--chip", validate_chip(chip), "--port", validate_port(port),
            "--baud", str(validate_baud(baud)), validate_info_op(op)]


_INFO_PATTERNS = {
    "chip": [r"^Chip is (.+?)\s*$", r"^Chip type:\s*(.+?)\s*$"],
    "chip_family": [r"^Detecting chip type\.*\s*(\S+)\s*$", r"Connected to (ESP\S+)"],
    "features": [r"^Features:\s*(.+?)\s*$"],
    "crystal": [r"^Crystal is (\S+)", r"^Crystal frequency:\s*(\S+)"],
    "mac": [r"^MAC:\s*([0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5})"],
    "chip_id": [r"^Chip ID:\s*(0x[0-9A-Fa-f]+)"],
    "flash_manufacturer": [r"^Manufacturer:\s*([0-9A-Fa-f]+)"],
    "flash_device": [r"^Device:\s*([0-9A-Fa-f]+)"],
    "flash_size": [r"^Detected flash size:\s*(\S+)"],
}


def parse_esptool_info(output: str) -> dict:
    """Pull chip/MAC/flash details out of esptool output. Missing keys -> None."""
    info = {k: None for k in _INFO_PATTERNS}
    for key, pats in _INFO_PATTERNS.items():
        for pat in pats:
            m = re.search(pat, output, re.MULTILINE)
            if m:
                info[key] = m.group(1).strip()
                break
    if info["mac"]:
        info["mac"] = info["mac"].lower()
    if info["chip_family"] is None and info["chip"]:
        info["chip_family"] = info["chip"].split()[0].split("-")[0]
    return info


def run_info(cmd: list[str], timeout: int = INFO_TIMEOUT_S) -> dict:
    """Run a read-only esptool command; return exit code, raw output, parsed info."""
    try:
        r = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                           text=True, timeout=timeout, shell=False)
        out, code = r.stdout or "", r.returncode
    except FileNotFoundError:
        out, code = "esptool could not be started (not found).", 127
    except subprocess.TimeoutExpired as e:
        out = (e.output if isinstance(e.output, str) else "") + \
              f"\nTimed out after {timeout}s (is the board in bootloader mode?)."
        code = 124
    return {"exit_code": code, "ok": code == 0, "output": out,
            "info": parse_esptool_info(out)}
