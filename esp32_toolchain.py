"""ESP32 development toolchain installer (ESP-IDF and Arduino-CLI).

Installs onto the machine running the BakerPi Installer server (the Pi in
on-device mode, or your PC) -- never over SSH. Every step is a fixed,
list-form subprocess (shell=False). The upstream installers are shell scripts
(ESP-IDF ``install.sh``, Arduino-CLI ``install.sh``); they are invoked as
``[bash|sh, <fixed path>, <validated args>]`` with no user-string
interpolation. User-supplied values (ESP-IDF version, chip targets) pass a
strict regex / allowlist first.

UNTESTED ON HARDWARE: covered by unit tests with mocked subprocess only. Not
verified end-to-end on a real Pi Zero. ESP-IDF is large (~1-2 GB with tools)
and slow to install on a Pi Zero (single-core ARMv6, 512 MB RAM): expect a
long run (possibly an hour or more) and Espressif may not ship prebuilt
toolchains for armv6l at all, in which case install.sh will fail.
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

ITEMS = ("esp-idf", "arduino-cli")
IDF_REPO = "https://github.com/espressif/esp-idf.git"
DEFAULT_IDF_VERSION = "v5.3.1"
IDF_TARGETS = ("all", "esp32", "esp32s2", "esp32s3", "esp32c2", "esp32c3",
               "esp32c6", "esp32h2")
DEFAULT_IDF_TARGETS = ("esp32",)
ARDUINO_INSTALL_URL = "https://raw.githubusercontent.com/arduino/arduino-cli/master/install.sh"
ESP32_CORE_INDEX = "https://espressif.github.io/arduino-esp32/package_esp32_index.json"
ESP32_CORE = "esp32:esp32"
_IDF_VERSION_RE = re.compile(r"^v\d{1,2}\.\d{1,2}(?:\.\d{1,2})?$")

PREREQS = {"esp-idf": ("git", "python3", "bash"), "arduino-cli": ("curl", "sh")}

_install_lock = threading.Lock()


class ToolchainValidationError(ValueError):
    """User input rejected before anything is executed."""


class PrereqMissing(RuntimeError):
    def __init__(self, item: str, missing: list[str]):
        self.item, self.missing = item, missing
        super().__init__(f"{item} needs these programs on PATH: {', '.join(missing)}")


# ── Paths ─────────────────────────────────────────────────────────────────────

def esp_root() -> Path:
    return Path(os.environ.get("BAKERPI_ESP_DIR") or Path.home() / "esp")


def idf_path() -> Path:
    return esp_root() / "esp-idf"


def arduino_bindir() -> Path:
    return Path.home() / ".local" / "bin"


# ── Validation ────────────────────────────────────────────────────────────────

def validate_item(item) -> str:
    if item not in ITEMS:
        raise ToolchainValidationError(f"Unknown toolchain item. Allowed: {', '.join(ITEMS)}")
    return item


def validate_idf_version(version) -> str:
    if not isinstance(version, str) or not _IDF_VERSION_RE.fullmatch(version):
        raise ToolchainValidationError("Invalid ESP-IDF version. Use a release tag like v5.3.1.")
    return version


def validate_idf_targets(targets) -> list[str]:
    if not isinstance(targets, (list, tuple)) or not targets or len(targets) > len(IDF_TARGETS):
        raise ToolchainValidationError("targets must be a non-empty list.")
    out = []
    for t in targets:
        if t not in IDF_TARGETS:
            raise ToolchainValidationError(f"Invalid target. Allowed: {', '.join(IDF_TARGETS)}")
        if t not in out:
            out.append(t)
    if "all" in out:
        return ["all"]
    return out


# ── Status / prerequisites ────────────────────────────────────────────────────

def missing_prereqs(item: str) -> list[str]:
    return [p for p in PREREQS[validate_item(item)] if shutil.which(p) is None]


def find_arduino_cli() -> Optional[str]:
    path = shutil.which("arduino-cli")
    if path:
        return path
    local = arduino_bindir() / "arduino-cli"
    return str(local) if local.is_file() else None


def esp32_core_installed(cli: str) -> bool:
    try:
        r = subprocess.run([cli, "core", "list"], capture_output=True, text=True,
                           timeout=30, shell=False)
    except (OSError, subprocess.TimeoutExpired):
        return False
    return r.returncode == 0 and ESP32_CORE in r.stdout


def status() -> dict:
    idf = idf_path()
    idf_installed = (idf / "tools" / "idf.py").is_file()
    cli = find_arduino_cli()
    windows = platform.system() == "Windows"
    return {
        "hardware_tested": False,
        "host": {"system": platform.system(), "machine": platform.machine()},
        "busy": _install_lock.locked(),
        "esp-idf": {
            "installed": idf_installed,
            "path": str(idf),
            "tools_dir_present": (Path.home() / ".espressif").is_dir(),
            "missing_prereqs": missing_prereqs("esp-idf"),
            "supported": not windows,
            "default_version": DEFAULT_IDF_VERSION,
            "targets": list(IDF_TARGETS),
        },
        "arduino-cli": {
            "installed": cli is not None,
            "path": cli,
            "esp32_core_installed": bool(cli) and esp32_core_installed(cli),
            "missing_prereqs": missing_prereqs("arduino-cli"),
            "supported": not windows,
        },
    }


# ── Command construction ──────────────────────────────────────────────────────

def build_idf_steps(version: str = DEFAULT_IDF_VERSION,
                    targets=DEFAULT_IDF_TARGETS) -> list[list[str]]:
    version = validate_idf_version(version)
    tgts = validate_idf_targets(list(targets))
    dest = idf_path()
    steps = []
    if not (dest / "install.sh").is_file():
        steps.append(["git", "clone", "--depth", "1", "--branch", version, "--recursive",
                      "--shallow-submodules", IDF_REPO, str(dest)])
    steps.append(["bash", str(dest / "install.sh"), ",".join(tgts)])
    return steps


def build_arduino_steps(script_path: str, with_esp32_core: bool) -> list[list[str]]:
    steps = [["curl", "-fsSL", "-o", script_path, ARDUINO_INSTALL_URL],
             ["sh", script_path]]
    if with_esp32_core:
        cli = str(arduino_bindir() / "arduino-cli")
        steps += [[cli, "core", "update-index", "--additional-urls", ESP32_CORE_INDEX],
                  [cli, "core", "install", ESP32_CORE, "--additional-urls", ESP32_CORE_INDEX]]
    return steps


def arduino_env() -> dict:
    env = dict(os.environ)
    env["BINDIR"] = str(arduino_bindir())  # arduino-cli install.sh honours BINDIR
    return env


# ── Running ───────────────────────────────────────────────────────────────────

def _run_step(cmd: list[str], env: Optional[dict] = None) -> Iterator[str]:
    yield "$ " + " ".join(cmd) + "\n"
    try:
        proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                                text=True, bufsize=1, shell=False, env=env)
    except FileNotFoundError:
        yield f"{cmd[0]} could not be started (not found).\n"
        yield 127
        return
    for line in proc.stdout:
        yield line
    proc.wait()
    yield proc.returncode


def run_steps(steps: list[list[str]], env: Optional[dict] = None,
              cleanup: Optional[str] = None) -> Iterator[str]:
    """Run steps in order, stop at the first failure, end with [EXIT n].
    Caller must already hold ``_install_lock``; it is released here."""
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
                break
        yield f"\n[EXIT {rc}]\n"
    finally:
        if cleanup:
            try:
                os.unlink(cleanup)
            except OSError:
                pass
        _install_lock.release()


def acquire() -> bool:
    return _install_lock.acquire(blocking=False)


def plan_install(item: str, version: str = DEFAULT_IDF_VERSION,
                 targets=DEFAULT_IDF_TARGETS, with_esp32_core: bool = True):
    """Validate and return (steps, env, cleanup_path). Raises on bad input or
    missing prerequisites; executes nothing."""
    validate_item(item)
    if platform.system() == "Windows":
        raise ToolchainValidationError(
            f"{item} install via BakerPi is Linux/macOS only. On Windows use the "
            "official Espressif / Arduino installers.")
    if item == "esp-idf":
        steps = build_idf_steps(version, targets)  # validates before prereq check
        missing = missing_prereqs(item)
        if missing:
            raise PrereqMissing(item, missing)
        root = esp_root()
        root.mkdir(parents=True, exist_ok=True)
        return steps, None, None
    missing = missing_prereqs(item)
    if missing:
        raise PrereqMissing(item, missing)
    arduino_bindir().mkdir(parents=True, exist_ok=True)
    fd, script = tempfile.mkstemp(prefix="bakerpi-arduino-cli-", suffix=".sh")
    os.close(fd)
    return build_arduino_steps(script, bool(with_esp32_core)), arduino_env(), script
