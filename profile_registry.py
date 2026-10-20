"""
Fleet install profiles for the BakerPi Tool Installer.

A *profile* is a named, reusable, ordered set of tool ids (a selection from
``tools/catalog.json``) that can be applied to one or many devices in a single
action. This module only stores and validates profiles; running them is done by
the existing install-job machinery in ``server.py``.

Like :mod:`device_registry` this module is stdlib-only so it can be unit-tested
without FastAPI, paramiko or any hardware.

Design notes
------------
* Only non-secret data is persisted: id, name, description and tool ids.
* The file lives in a per-user config directory (outside the repo), see
  :func:`default_profiles_path`, and is written with mode ``0600``.
* Tool ids are validated against the catalog *when a profile is created or
  updated*. They are not re-validated on load, so a catalog that later drops a
  tool does not make the profile file unreadable; applying a profile that
  references a tool the catalog no longer has is refused instead (see
  :meth:`Profile.unknown_tools`).
"""

from __future__ import annotations

import json
import logging
import os
import re
import sys
import threading
import uuid
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

log = logging.getLogger("installer.profiles")

PROFILES_VERSION = 1

_ID_RE = re.compile(r"^[A-Za-z0-9_-]{1,32}$")
_TOOL_ID_RE = re.compile(r"^[A-Za-z0-9_.-]{1,64}$")
_MAX_NAME = 64
_MAX_DESCRIPTION = 500
_MAX_TOOLS = 200


class ProfileError(ValueError):
    """Raised for invalid profile data."""


class ProfileNotFound(LookupError):
    """Raised when a profile id is not in the registry."""


@dataclass
class Profile:
    id: str
    name: str
    description: str = ""
    tool_ids: list = field(default_factory=list)

    def to_dict(self) -> dict:
        return asdict(self)

    def to_storage(self) -> dict:
        return asdict(self)


def default_profiles_path(env: Optional[dict] = None, platform: Optional[str] = None) -> Path:
    """Per-user, out-of-repo location of the profiles file.

    ``BAKERPI_PROFILES_FILE`` overrides it (also used by ``--profiles-file``).
    """
    env = os.environ if env is None else env
    platform = sys.platform if platform is None else platform
    override = env.get("BAKERPI_PROFILES_FILE")
    if override:
        return Path(override).expanduser()
    if platform.startswith("win"):
        base = Path(env.get("APPDATA") or (Path.home() / "AppData" / "Roaming"))
    elif platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    else:
        base = Path(env.get("XDG_CONFIG_HOME") or (Path.home() / ".config"))
    return base / "BakerPi-Installer" / "profiles.json"


def _clean_str(value: Any, name: str, max_len: int) -> str:
    if value is None:
        return ""
    if not isinstance(value, str):
        raise ProfileError(f"{name} must be a string")
    value = value.strip()
    if len(value) > max_len:
        raise ProfileError(f"{name} is too long (max {max_len})")
    if any(ord(c) < 32 for c in value):
        raise ProfileError(f"{name} contains control characters")
    return value


def _clean_tool_ids(value: Any) -> list:
    """Order-preserving, de-duplicated list of well-formed tool ids."""
    if not isinstance(value, (list, tuple)):
        raise ProfileError("tool_ids must be a list")
    out: list = []
    for tid in value:
        if not isinstance(tid, str) or not _TOOL_ID_RE.match(tid):
            raise ProfileError(f"invalid tool id: {tid!r}")
        if tid not in out:
            out.append(tid)
    if not out:
        raise ProfileError("a profile needs at least one tool")
    if len(out) > _MAX_TOOLS:
        raise ProfileError(f"too many tools (max {_MAX_TOOLS})")
    return out


def validate_profile_fields(fields: dict, profile_id: str,
                            known_tools: Optional[Callable[[], Iterable[str]]] = None
                            ) -> Profile:
    """Validate/normalise a complete set of fields into a Profile.

    When ``known_tools`` is given, every tool id must be one it returns.
    """
    name = _clean_str(fields.get("name"), "name", _MAX_NAME)
    if not name:
        raise ProfileError("name is required")
    description = _clean_str(fields.get("description"), "description", _MAX_DESCRIPTION)
    tool_ids = _clean_tool_ids(fields.get("tool_ids"))
    if known_tools is not None:
        known = set(known_tools())
        unknown = [t for t in tool_ids if t not in known]
        if unknown:
            raise ProfileError("unknown tool id(s): " + ", ".join(unknown))
    return Profile(id=profile_id, name=name, description=description, tool_ids=tool_ids)


class ProfileRegistry:
    """Persisted list of install profiles (thread-safe)."""

    def __init__(self, path: Optional[Path] = None,
                 known_tools: Optional[Callable[[], Iterable[str]]] = None):
        self.path = Path(path) if path else default_profiles_path()
        self._known_tools = known_tools
        self._lock = threading.RLock()
        self._profiles: list[Profile] = []
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
                raise ValueError("profiles root must be an object")
            profiles = []
            seen: set = set()
            for raw in data.get("profiles", []):
                # structure only: catalog drift must not invalidate the file
                prof = validate_profile_fields(raw, str(raw.get("id") or ""))
                if not _ID_RE.match(prof.id) or prof.id in seen:
                    raise ValueError(f"missing or duplicate profile id: {prof.id!r}")
                seen.add(prof.id)
                profiles.append(prof)
            self._profiles = profiles
        except Exception as e:  # corrupt or hand-edited file: keep it, start clean
            bad = self.path.with_name(self.path.name + ".bad")
            log.warning("Ignoring unreadable profiles file %s (%s); moved to %s",
                        self.path, e, bad)
            try:
                os.replace(self.path, bad)
            except OSError:
                pass
            self._profiles = []

    def _save(self) -> None:
        payload = {
            "version": PROFILES_VERSION,
            "profiles": [p.to_storage() for p in self._profiles],
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

    def list(self) -> list[Profile]:
        with self._lock:
            self._ensure_loaded()
            return list(self._profiles)

    def get(self, profile_id: str) -> Profile:
        with self._lock:
            self._ensure_loaded()
            for p in self._profiles:
                if p.id == profile_id:
                    return p
        raise ProfileNotFound(f"Unknown profile: {profile_id}")

    def unknown_tools(self, profile: Profile) -> list:
        """Tool ids of ``profile`` that the current catalog no longer has."""
        if self._known_tools is None:
            return []
        known = set(self._known_tools())
        return [t for t in profile.tool_ids if t not in known]

    # ── mutations ────────────────────────────────────────────────────────────

    def _check_name_free(self, name: str, ignore_id: Optional[str] = None) -> None:
        lowered = name.casefold()
        for p in self._profiles:
            if p.id != ignore_id and p.name.casefold() == lowered:
                raise ProfileError(f"a profile named {p.name!r} already exists")

    def add(self, **fields) -> Profile:
        with self._lock:
            self._ensure_loaded()
            existing = {p.id for p in self._profiles}
            new_id = uuid.uuid4().hex[:8]
            while new_id in existing:
                new_id = uuid.uuid4().hex[:8]
            prof = validate_profile_fields(fields, new_id, self._known_tools)
            self._check_name_free(prof.name)
            self._profiles.append(prof)
            self._save()
            return prof

    def update(self, profile_id: str, **fields) -> Profile:
        """Partial update: only keys present in ``fields`` change."""
        with self._lock:
            self._ensure_loaded()
            for i, p in enumerate(self._profiles):
                if p.id == profile_id:
                    merged = p.to_storage()
                    merged.update({k: v for k, v in fields.items() if k != "id"})
                    # only re-check the catalog when the tool list itself changes, so a
                    # profile holding a since-removed tool can still be renamed/fixed
                    check = self._known_tools if "tool_ids" in fields else None
                    updated = validate_profile_fields(merged, p.id, check)
                    self._check_name_free(updated.name, ignore_id=p.id)
                    self._profiles[i] = updated
                    self._save()
                    return updated
        raise ProfileNotFound(f"Unknown profile: {profile_id}")

    def remove(self, profile_id: str) -> None:
        with self._lock:
            self._ensure_loaded()
            before = len(self._profiles)
            self._profiles = [p for p in self._profiles if p.id != profile_id]
            if len(self._profiles) == before:
                raise ProfileNotFound(f"Unknown profile: {profile_id}")
            self._save()
