"""Built-in fleet firmware profiles (VictorModem, Pyra Claw) and multi-image flashing.

ESP32 feature 4 of 4.

Facts come from the VictorModem and Pyra Claw project notes only:

* Neither project publishes release binaries; you build them yourself with
  PlatformIO (output in ``.pio/build/<env>/``).
* The offsets below have NOT been verified on hardware.
* Neither firmware supports serial provisioning yet.

UNTESTED ON HARDWARE: command construction and validation are covered by unit
tests with mocks only.
"""
from __future__ import annotations

import os
from typing import Optional

import esp32_flasher
from esp32_flasher import FlashValidationError

# Image role -> expected filename. Only these names are ever read from a build dir.
IMAGE_FILES = {
    "bootloader": "bootloader.bin",
    "partitions": "partitions.bin",
    "boot_app0": "boot_app0.bin",
    "firmware": "firmware.bin",
}
# boot_app0.bin ships with the Arduino-ESP32 framework (tools/partitions/), so
# PlatformIO usually doesn't copy it into .pio/build/<env>/.
OPTIONAL_ROLES = ("boot_app0",)

_VM_COMMON = {"partitions": "0x8000", "boot_app0": "0xe000", "firmware": "0x10000"}
_VM_POST = ("USB CDC serial at 115200 baud is a debug log only. Runtime control is "
            "over BLE GATT or Wi-Fi WebSocket (port 81). No serial provisioning.")

PROFILES: dict = {
    "victormodem": {
        "name": "VictorModem",
        "repo": "Victorious93/victormodem",
        "build_system": "PlatformIO",
        "published_binaries": False,
        "offsets_verified": False,
        "serial_provisioning": False,
        "notes": ("Flash mode/size are not specified by the project, so BakerPi "
                  "leaves them to esptool's defaults/detection (no N16R8 assumption)."),
        "post_flash": _VM_POST,
        "monitor_baud": 115200,
        "envs": {
            "esp32s3_bridge5g": {"chip": "esp32s3", "baud": 460800, "flash_args": [],
                                 "images": {"bootloader": "0x0", **_VM_COMMON}},
            "esp32s3_direct4g": {"chip": "esp32s3", "baud": 460800, "flash_args": [],
                                 "images": {"bootloader": "0x0", **_VM_COMMON}},
            "tsim7600_4g": {"chip": "esp32", "baud": 460800, "flash_args": [],
                            "partition_table": "huge_app",
                            "images": {"bootloader": "0x1000", **_VM_COMMON}},
        },
    },
    "pyra-claw": {
        "name": "Pyra Claw",
        "repo": "Victorious93/pyra-claw",
        "project_dir": "firmware/esp32-wake",
        "build_system": "PlatformIO",
        "published_binaries": False,
        "offsets_verified": False,
        "serial_provisioning": False,
        "notes": ("ESP32-S3 is not supported. Flash args are 'likely, PlatformIO "
                  "defaults' per the project, not confirmed."),
        "post_flash": ("Provisioning is compile-time (config.h) plus MQTT on the Pi. "
                       "No serial provisioning yet."),
        "monitor_baud": None,
        "envs": {
            "esp32dev": {"chip": "esp32", "baud": 460800,
                         "flash_args": ["--flash_mode", "dio", "--flash_freq", "40m",
                                        "--flash_size", "detect"],
                         "flash_args_confidence": "likely (PlatformIO defaults)",
                         "images": {"bootloader": "0x1000", "partitions": "0x8000",
                                    "boot_app0": "0xe000", "firmware": "0x10000"}},
        },
    },
}


def list_profiles() -> list[dict]:
    out = []
    for pid, p in PROFILES.items():
        envs = []
        for eid, e in p["envs"].items():
            envs.append({"id": eid, **{k: v for k, v in e.items() if k != "images"},
                         "build_dir_hint": f".pio/build/{eid}/",
                         "images": [{"role": r, "file": IMAGE_FILES[r], "address": a,
                                     "optional": r in OPTIONAL_ROLES}
                                    for r, a in e["images"].items()]})
        out.append({"id": pid, **{k: v for k, v in p.items() if k != "envs"},
                    "envs": envs, "hardware_tested": False})
    return out


def get_env(profile: str, env: str) -> dict:
    p = PROFILES.get(profile) if isinstance(profile, str) else None
    if p is None:
        raise FlashValidationError(f"Unknown profile. Allowed: {', '.join(PROFILES)}")
    e = p["envs"].get(env) if isinstance(env, str) else None
    if e is None:
        raise FlashValidationError(
            f"Unknown env for {p['name']}. Allowed: {', '.join(p['envs'])}")
    return e


def validate_build_dir(path: str) -> str:
    """Strictly validate a local PlatformIO build dir; return its real path."""
    if not isinstance(path, str) or not path or len(path) > 4096 or "\x00" in path:
        raise FlashValidationError("Invalid build directory path.")
    if any(c in path for c in "\r\n"):
        raise FlashValidationError("Invalid build directory path.")
    expanded = os.path.expanduser(path)
    if not os.path.isabs(expanded):
        raise FlashValidationError("Build directory must be an absolute path.")
    parts = expanded.replace("\\", "/").split("/")
    if ".." in parts:
        raise FlashValidationError("Build directory must not contain '..'.")
    real = os.path.realpath(expanded)
    if not os.path.isdir(real):
        raise FlashValidationError("Build directory does not exist.")
    return real


def collect_from_build_dir(build_dir: str, env_cfg: dict,
                           extra: Optional[dict] = None) -> dict:
    """Map role -> file path from a validated build dir (fixed filenames only).

    ``extra`` holds role -> path for images supplied by upload (e.g. boot_app0).
    Each file must be a regular file inside build_dir (symlinks out are refused).
    """
    real = validate_build_dir(build_dir)
    found = dict(extra or {})
    for role in env_cfg["images"]:
        if role in found:
            continue
        p = os.path.join(real, IMAGE_FILES[role])
        if not os.path.lexists(p):
            continue
        rp = os.path.realpath(p)
        if os.path.dirname(rp) != real or os.path.islink(p) or not os.path.isfile(rp):
            raise FlashValidationError(f"{IMAGE_FILES[role]} is not a regular file in the build dir.")
        found[role] = rp
    return found


def check_images(env_cfg: dict, images: dict) -> None:
    """Required images present, sizes sane, no overlaps."""
    missing = [IMAGE_FILES[r] for r in env_cfg["images"]
               if r not in images and r not in OPTIONAL_ROLES]
    if missing:
        raise FlashValidationError("Missing required image(s): " + ", ".join(missing))
    unknown = set(images) - set(env_cfg["images"])
    if unknown:
        raise FlashValidationError("Unexpected image role(s): " + ", ".join(sorted(unknown)))
    spans = []
    for role, path in images.items():
        addr = esp32_flasher.validate_address(env_cfg["images"][role])
        size = os.path.getsize(path)
        esp32_flasher.validate_firmware(IMAGE_FILES[role], size, addr)
        spans.append((int(addr, 16), int(addr, 16) + size, IMAGE_FILES[role]))
    spans.sort()
    for a, b in zip(spans, spans[1:]):
        if a[1] > b[0]:
            raise FlashValidationError(f"{a[2]} overlaps {b[2]} at the profile offsets.")


def build_multi_flash_cmd(esptool_cmd: list[str], port: str, baud: int,
                          env_cfg: dict, images: dict) -> list[str]:
    """List-form esptool write_flash with several addr/file pairs (shell=False)."""
    check_images(env_cfg, images)
    cmd = [*esptool_cmd, "--chip", esp32_flasher.validate_chip(env_cfg["chip"]),
           "--port", esp32_flasher.validate_port(port),
           "--baud", str(esp32_flasher.validate_baud(baud)),
           "write_flash", *env_cfg.get("flash_args", [])]
    for role, addr in sorted(env_cfg["images"].items(), key=lambda kv: int(kv[1], 16)):
        if role in images:
            cmd += [esp32_flasher.validate_address(addr), images[role]]
    return cmd
