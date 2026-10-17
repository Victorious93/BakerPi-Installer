"""
Device inventory / registry for the BakerPi Tool Installer.

Keeps a persisted list of Pi targets plus the current target selection.
This module is deliberately dependency-free (stdlib only) so it can be
unit-tested without FastAPI, paramiko or any hardware.

Design notes
------------
* A built-in device with the reserved id ``"default"`` always exists. It is
  built from the CLI arguments (``--mode/--host/--user/--port``) and is never
  written to disk, so single-device usage keeps working with no config file.
* Only non-secret connection metadata is persisted (id, label, type, host,
  user, port, optional key-file *path*). Passwords are never stored here.
* The registry file lives in a per-user config directory (outside the repo),
  see :func:`default_devices_path`.
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import uuid
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

log = logging.getLogger("installer.devices")

DEFAULT_DEVICE_ID = "default"
DEVICE_TYPES = ("ssh", "local", "usb-rndis")
SSH_TYPES = ("ssh", "usb-rndis")
USB_RNDIS_DEFAULT_HOST = "172.16.0.1"  # Pi Zero gadget address used by BakerPi
REGISTRY_VERSION = 1

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_HOST_RE = re.compile(r"^[A-Za-z0-9._:%\-\[\]]+$")
_MAX_LABEL = 64
_MAX_HOST = 255
_MAX_USER = 64
_MAX_PATH = 1024


class DeviceError(ValueError):
    """Raised for invalid device data or disallowed operations."""


class DeviceNotFound(LookupError):
    """Raised when a device id is not in the registry."""


@dataclass
class Device:
    id: str
    label: str
    type: str = "ssh"
    host: str = ""
    user: str = "root"
    port: int = 22
    key_file: Optional[str] = None
    builtin: bool = False

    @property
    def is_local(self) -> bool:
        return self.type == "local"

    def to_dict(self) -> dict:
        return asdict(self)

    def to_storage(self) -> dict:
        d = asdict(self)
        d.pop("builtin", None)
        return d


def default_devices_path(env: Optional[dict] = None, platform: Optional[str] = None) -> Path:
    """Per-user, out-of-repo location of the device registry file.

    ``BAKERPI_DEVICES_FILE`` overrides it (also used by ``--devices-file``).
    """
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    override = env.get("BAKERPI_DEVICES_FILE")
    if override:
        return Path(override).expanduser()
    if platform.startswith("win"):
        base = Path(env.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    elif platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(env.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "BakerPi-Installer" / "devices.json"


def build_default_device(config: dict) -> Device:
    """Build the built-in device from the CLI-provided single-target config."""
    if config.get("mode") == "local":
        return Device(id=DEFAULT_DEVICE_ID, label="This device (local)", type="local",
                      host="localhost", user="", port=22, builtin=True)
    host = config.get("host") or USB_RNDIS_DEFAULT_HOST
    user = config.get("user") or "root"
    port = int(config.get("port") or 22)
    return Device(id=DEFAULT_DEVICE_ID, label=f"Default ({user}@{host})", type="ssh",
                  host=host, user=user, port=port,
                  key_file=config.get("key_file"), builtin=True)


def _clean_str(value: Any, name: str, max_len: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise DeviceError(f"{name} must be a string")
    value = value.strip()
    if len(value) > max_len:
        raise DeviceError(f"{name} is too long (max {max_len})")
    if any(ord(c) < 32 for c in value):
        raise DeviceError(f"{name} contains control characters")
    return value


def validate_device_fields(fields: dict, device_id: str) -> Device:
    """Validate/normalise a complete set of fields into a Device."""
    dtype = _clean_str(fields.get("type") or "ssh", "type", 32)
    if dtype not in DEVICE_TYPES:
        raise DeviceError(f"type must be one of {', '.join(DEVICE_TYPES)}")

    host = _clean_str(fields.get("host"), "host", _MAX_HOST)
    user = _clean_str(fields.get("user"), "user", _MAX_USER)
    key_file = _clean_str(fields.get("key_file"), "key_file", _MAX_PATH) or None

    port_raw = fields.get("port")
    try:
        port = 22 if port_raw in (None, "") else int(port_raw)
    except (TypeError, ValueError):
        raise DeviceError("port must be an integer")
    if isinstance(port_raw, bool) or not (1 <= port <= 65535):
        raise DeviceError("port must be between 1 and 65535")

    if dtype == "local":
        host, user, key_file = "localhost", "", None
    else:
        if not host and dtype == "usb-rndis":
            host = USB_RNDIS_DEFAULT_HOST
        if not host:
            raise DeviceError("host is required for ssh / usb-rndis devices")
        if not _HOST_RE.match(host):
            raise DeviceError("host contains invalid characters")
        user = user or "root"

    label = _clean_str(fields.get("label"), "label", _MAX_LABEL)
    if not label:
        label = "This device" if dtype == "local" else f"{user}@{host}"

    return Device(id=device_id, label=label, type=dtype, host=host, user=user,
                  port=port, key_file=key_file)


class DeviceRegistry:
    """Persisted list of devices + current target selection (thread-safe)."""

    def __init__(self, path: Optional[Path] = None,
                 default_factory: Optional[Callable[[], Device]] = None):
        self.path = Path(path) if path else default_devices_path()
        self._default_factory = default_factory or (
            lambda: build_default_device({"mode": "local"}))
        self._lock = threading.RLock()
        self._devices: list[Device] = []
        self._selected: list[str] = []
        self._loaded = False

    # ── persistence ──────────────────────────────────────────────────────────

    def _ensure_loaded(self) -> None:
        if self._loaded:
            return
        self._loaded = True
        if not self.path.exists():
            return
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                raise ValueError("registry root must be an object")
            devices = []
            seen = {DEFAULT_DEVICE_ID}
            for raw in data.get("devices", []):
                dev = validate_device_fields(raw, str(raw.get("id") or ""))
                if not _ID_RE.match(dev.id) or dev.id in seen:
                    raise ValueError(f"missing or duplicate device id: {dev.id!r}")
                seen.add(dev.id)
                devices.append(dev)
            selected = data.get("selected", [])
            if not isinstance(selected, list):
                raise ValueError("selected must be a list")
            self._devices = devices
            self._selected = [s for s in selected if isinstance(s, str)]
        except Exception as e:  # corrupt or hand-edited file: keep it, start clean
            bad = self.path.with_name(self.path.name + ".bad")
            log.warning("Ignoring unreadable device registry %s (%s); moved to %s",
                        self.path, e, bad)
            try:
                os.replace(self.path, bad)
            except OSError:
                pass
            self._devices, self._selected = [], []

    def _save(self) -> None:
        payload = {
            "version": REGISTRY_VERSION,
            "devices": [d.to_storage() for d in self._devices],
            "selected": list(self._selected),
        }
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_name(self.path.name + f".{os.getpid()}.tmp")
        tmp.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    # ── queries ──────────────────────────────────────────────────────────────

    def default_device(self) -> Device:
        return self._default_factory()

    def list(self) -> list[Device]:
        with self._lock:
            self._ensure_loaded()
            return [self.default_device(), *self._devices]

    def get(self, device_id: str) -> Device:
        with self._lock:
            self._ensure_loaded()
            if device_id == DEFAULT_DEVICE_ID:
                return self.default_device()
            for d in self._devices:
                if d.id == device_id:
                    return d
        raise DeviceNotFound(f"Unknown device: {device_id}")

    # ── mutations ────────────────────────────────────────────────────────────

    def add(self, **fields) -> Device:
        with self._lock:
            self._ensure_loaded()
            existing = {d.id for d in self._devices} | {DEFAULT_DEVICE_ID}
            new_id = uuid.uuid4().hex[:8]
            while new_id in existing:
                new_id = uuid.uuid4().hex[:8]
            dev = validate_device_fields(fields, new_id)
            self._devices.append(dev)
            self._save()
            return dev

    def update(self, device_id: str, **fields) -> Device:
        """Partial update: only keys present in ``fields`` change."""
        with self._lock:
            self._ensure_loaded()
            if device_id == DEFAULT_DEVICE_ID:
                raise DeviceError("The built-in default device cannot be edited")
            for i, d in enumerate(self._devices):
                if d.id == device_id:
                    merged = d.to_storage()
                    merged.update({k: v for k, v in fields.items() if k != "id"})
                    if d.type == "local" and merged.get("type") != "local" \
                            and "host" not in fields:
                        merged["host"] = ""  # don't inherit the placeholder "localhost"
                    updated = validate_device_fields(merged, d.id)
                    self._devices[i] = updated
                    self._save()
                    return updated
        raise DeviceNotFound(f"Unknown device: {device_id}")

    def remove(self, device_id: str) -> None:
        with self._lock:
            self._ensure_loaded()
            if device_id == DEFAULT_DEVICE_ID:
                raise DeviceError("The built-in default device cannot be removed")
            before = len(self._devices)
            self._devices = [d for d in self._devices if d.id != device_id]
            if len(self._devices) == before:
                raise DeviceNotFound(f"Unknown device: {device_id}")
            self._selected = [s for s in self._selected if s != device_id]
            self._save()

    # ── selection ────────────────────────────────────────────────────────────

    def get_selected_ids(self) -> list[str]:
        """Selected ids (order = priority; first is the 'primary' device).

        Falls back to the built-in default device when nothing valid is selected.
        """
        with self._lock:
            self._ensure_loaded()
            valid = {DEFAULT_DEVICE_ID} | {d.id for d in self._devices}
            out: list[str] = []
            for s in self._selected:
                if s in valid and s not in out:
                    out.append(s)
            return out or [DEFAULT_DEVICE_ID]

    def get_selected(self) -> list[Device]:
        return [self.get(i) for i in self.get_selected_ids()]

    def primary(self) -> Device:
        return self.get_selected()[0]

    def set_selected(self, device_ids: Iterable[str]) -> list[str]:
        with self._lock:
            self._ensure_loaded()
            ids: list[str] = []
            for i in device_ids:
                if i not in ids:
                    ids.append(i)
            if not ids:
                raise DeviceError("Select at least one device")
            for i in ids:
                self.get(i)  # raises DeviceNotFound
            self._selected = ids
            self._save()
            return list(ids)

    def resolve(self, device_id: Optional[str] = None,
                device_ids: Optional[Iterable[str]] = None) -> list[Device]:
        """Resolve the targets of a request.

        Explicit ``device_ids`` win, then ``device_id``, then the current
        selection (which itself falls back to the built-in default device).
        """
        with self._lock:
            if device_ids:
                ids: list[str] = []
                for i in device_ids:
                    if i not in ids:
                        ids.append(i)
                return [self.get(i) for i in ids]
            if device_id:
                return [self.get(device_id)]
            return self.get_selected()
