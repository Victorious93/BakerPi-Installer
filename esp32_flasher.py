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
