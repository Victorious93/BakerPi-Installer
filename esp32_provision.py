"""Host side of the fleet USB serial provisioning contract v1.

Shared by VictorModem and Pyra Claw firmware. JSON lines at 115200 baud,
'\\n'-terminated; every reply carries "v":1. Lines that do not start with '{'
are firmware logs and are skipped. Commands: hello, get, provision {cfg},
reboot, factory_reset. Unknown commands get ok:false, err "unknown_cmd".

The board accepts commands for 10 s after boot, or at any time while it is
unprovisioned; changes apply after a reboot.

Secrets are NEVER logged or returned: they are replaced by "***" in every
reply, transcript line and error message produced here.

UNTESTED ON HARDWARE: covered by unit tests with a mocked serial port only.
The firmware side lives in open PRs (Pyra Claw branch feat/serial-provisioning,
victormodem PR #3); a board must run firmware with this feature.
"""
from __future__ import annotations

import ipaddress
import json
import re
import time
from typing import Any, Callable, Optional

import esp32_flasher

PROTOCOL_VERSION = 1
BAUD = 115200
READ_TIMEOUT_S = 1.0          # per readline
REPLY_TIMEOUT_S = 5.0         # waiting for one reply
WINDOW_S = 10.0               # firmware command window after boot
HELLO_TIMEOUT_S = 13.0        # covers boot + the 10 s window
HELLO_RETRY_S = 0.5
MAX_LINE_BYTES = 4096
MAX_LOG_LINES = 400
REDACTED = "***"

COMMANDS = ("hello", "get", "provision", "reboot", "factory_reset")


class ProvisionError(RuntimeError):
    """Protocol / transport failure. Message is always redaction-safe."""


class ProvisionTimeout(ProvisionError):
    pass


class SchemaError(ValueError):
    """Client-side cfg validation failure. Message never contains values."""


# ── Schemas ───────────────────────────────────────────────────────────────────
# field: type ("str"/"int"), min/max (length for str, value for int),
# secret, envs (None = all), default, fmt (extra validator), label.

_MAC_RE = re.compile(r"^[0-9A-Fa-f]{2}(?::[0-9A-Fa-f]{2}){5}$")


def _fmt_mac(v: str) -> bool:
    return bool(_MAC_RE.fullmatch(v))


def _fmt_ipv4(v: str) -> bool:
    try:
        ipaddress.IPv4Address(v)
        return True
    except ValueError:
        return False


_FORMATS: dict[str, Callable[[str], bool]] = {"mac": _fmt_mac, "ipv4": _fmt_ipv4}

_VM_APN_ENVS = ("esp32s3_direct4g", "tsim7600_4g")
_VM_ENVS = ("esp32s3_bridge5g", "esp32s3_direct4g", "tsim7600_4g")

SCHEMAS: dict[str, dict] = {
    "pyra-claw": {
        "label": "Pyra Claw",
        "partial": True,          # firmware merges partial updates
        "reject_unknown": True,   # we only send known keys anyway
        "envs": None,
        "fields": {
            "ssid":         {"type": "str", "min": 1, "max": 32, "label": "Wi-Fi SSID"},
            "pass":         {"type": "str", "min": 0, "max": 63, "secret": True, "label": "Wi-Fi password"},
            "broker":       {"type": "str", "min": 1, "max": 128, "label": "MQTT broker host"},
            "broker_port":  {"type": "int", "min": 1, "max": 65535, "default": 1883, "label": "MQTT port"},
            "node_id":      {"type": "str", "min": 1, "max": 64, "label": "Node ID"},
            "mqtt_user":    {"type": "str", "min": 0, "max": 64, "label": "MQTT user"},
            "mqtt_pass":    {"type": "str", "min": 0, "max": 128, "secret": True, "label": "MQTT password"},
            "pc_mac":       {"type": "str", "fmt": "mac", "label": "PC MAC (AA:BB:CC:DD:EE:FF)"},
            "pc_broadcast": {"type": "str", "fmt": "ipv4", "default": "255.255.255.255", "label": "WoL broadcast IPv4"},
            "hub_token":    {"type": "str", "min": 0, "max": 128, "secret": True, "label": "Hub token"},
        },
    },
    "victormodem": {
        "label": "VictorModem",
        "partial": False,         # whole cfg validated atomically
        "reject_unknown": True,
        "envs": _VM_ENVS,
        "fields": {
            "ap_ssid":   {"type": "str", "min": 1, "max": 32, "label": "AP SSID"},
            "ap_pass":   {"type": "str", "min": 8, "max": 63, "secret": True, "label": "AP password"},
            "api_token": {"type": "str", "min": 16, "max": 128, "secret": True, "label": "API token"},
            "apn":       {"type": "str", "min": 0, "max": 63, "envs": _VM_APN_ENVS, "label": "APN"},
            "apn_user":  {"type": "str", "min": 0, "max": 63, "envs": _VM_APN_ENVS, "label": "APN user"},
            "apn_pass":  {"type": "str", "min": 0, "max": 63, "secret": True, "envs": _VM_APN_ENVS, "label": "APN password"},
            "hub_baud":  {"type": "int", "min": 9600, "max": 3000000, "envs": ("esp32s3_bridge5g",), "label": "Hub UART baud"},
        },
    },
}

# Pyra Claw pass/mqtt_pass/hub_token lengths and other str bounds are
# conservative host-side limits; the firmware remains the authority.


def get_schema(project: str, env: Optional[str] = None) -> dict:
    """Fields applicable to project/env, as a JSON-safe description."""
    s = SCHEMAS.get(project)
    if s is None:
        raise SchemaError("Unsupported project. Known: " + ", ".join(SCHEMAS))
    if s["envs"] is not None and env not in s["envs"]:
        raise SchemaError("Unsupported env for " + project + ". Known: " + ", ".join(s["envs"]))
    fields = []
    for name, f in s["fields"].items():
        if f.get("envs") is not None and env not in f["envs"]:
            continue
        d = {"name": name, "type": f["type"], "label": f.get("label", name),
             "secret": bool(f.get("secret"))}
        for k in ("min", "max", "default", "fmt"):
            if k in f:
                d[k] = f[k]
        fields.append(d)
    return {"project": project, "env": env, "label": s["label"],
            "partial": s["partial"], "fields": fields}


def secret_keys(project: str) -> set[str]:
    s = SCHEMAS.get(project, {})
    keys = {k for k, f in s.get("fields", {}).items() if f.get("secret")}
    # Unknown project: treat anything that smells secret as secret.
    return keys | {"pass", "password", "token", "secret", "key", "psk"}


_SECRETISH = re.compile(r"(pass|token|secret|psk|key)", re.I)


def redact(obj: Any, project: str = "") -> Any:
    """Deep-copy obj with secret values replaced by '***'."""
    keys = secret_keys(project)
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            if isinstance(k, str) and (k in keys or (_SECRETISH.search(k) and k != "keys")) \
                    and not isinstance(v, (dict, list, bool)) and v not in (None, ""):
                out[k] = REDACTED
            else:
                out[k] = redact(v, project)
        return out
    if isinstance(obj, list):
        return [redact(v, project) for v in obj]
    return obj


def scrub(text: str, secrets: list[str]) -> str:
    """Remove any literal secret values from free text (e.g. firmware errors)."""
    for s in sorted({s for s in secrets if isinstance(s, str) and s}, key=len, reverse=True):
        text = text.replace(s, REDACTED)
    return text


def validate_cfg(project: str, env: Optional[str], cfg: Any) -> dict:
    """Validate cfg client-side. Returns a cleaned copy (ints coerced).

    Pyra Claw: partial (any non-empty subset). VictorModem: atomic, every
    field applicable to env is required, unknown keys rejected. Error messages
    name fields only, never values.
    """
    schema = SCHEMAS.get(project)
    if schema is None:
        raise SchemaError("Unsupported project.")
    if schema["envs"] is not None and env not in schema["envs"]:
        raise SchemaError("Unsupported env for this project.")
    if not isinstance(cfg, dict) or not cfg:
        raise SchemaError("cfg must be a non-empty object.")
    fields = {f["name"]: schema["fields"][f["name"]] for f in get_schema(project, env)["fields"]}
    errors = []
    unknown = sorted(k for k in cfg if k not in fields)
    if unknown:
        errors.append("unknown or not valid for this env: " + ", ".join(map(str, unknown)))
    if not schema["partial"]:
        missing = [k for k in fields if k not in cfg]
        if missing:
            errors.append("missing (atomic update needs all fields): " + ", ".join(missing))
    out = {}
    for k, v in cfg.items():
        f = fields.get(k)
        if f is None:
            continue
        if f["type"] == "int":
            if isinstance(v, bool):
                errors.append(f"{k}: must be an integer"); continue
            if isinstance(v, str) and re.fullmatch(r"[0-9]{1,8}", v.strip()):
                v = int(v.strip())
            if not isinstance(v, int):
                errors.append(f"{k}: must be an integer"); continue
            if not (f.get("min", v) <= v <= f.get("max", v)):
                errors.append(f"{k}: must be {f['min']}-{f['max']}"); continue
        else:
            if not isinstance(v, str):
                errors.append(f"{k}: must be a string"); continue
            if any(c in v for c in "\x00\r\n"):
                errors.append(f"{k}: control characters not allowed"); continue
            n = len(v.encode("utf-8"))
            if "min" in f and n < f["min"] or "max" in f and n > f["max"]:
                errors.append(f"{k}: length must be {f.get('min', 0)}-{f.get('max', '')}"); continue
            if "fmt" in f and not _FORMATS[f["fmt"]](v):
                errors.append(f"{k}: invalid format ({f['fmt']})"); continue
        out[k] = v
    if errors:
        raise SchemaError("; ".join(errors))
    return out


# ── Protocol ──────────────────────────────────────────────────────────────────

def encode(cmd: str, **kw) -> bytes:
    if cmd not in COMMANDS:
        raise ProvisionError("Command not allowed.")
    return (json.dumps({"v": PROTOCOL_VERSION, "cmd": cmd, **kw},
                       separators=(",", ":")) + "\n").encode()


class Session:
    """One open serial connection to a board.

    ``serial_factory`` builds an *unopened* pyserial-like object (tests pass a
    fake). DTR/RTS are deasserted before open so opening does not reset the
    board; ``reset=True`` then pulses EN via RTS to restart it and open the
    10 s command window (classic auto-reset wiring; native USB CDC on
    esp32s3 also maps RTS to reset).
    """

    def __init__(self, port: str, reset: bool = False,
                 serial_factory: Optional[Callable[[], Any]] = None,
                 clock: Callable[[], float] = time.monotonic,
                 sleep: Callable[[float], None] = time.sleep):
        esp32_flasher.validate_port(port)
        self.port_name = port
        self.reset = reset
        self.clock, self.sleep = clock, sleep
        self.project = ""
        self.secrets: list[str] = []
        self.logs: list[str] = []
        if serial_factory is None:
            try:
                import serial  # pyserial
            except ImportError as e:
                raise ProvisionError("pyserial is not installed: pip install pyserial") from e
            serial_factory = serial.Serial
        self._factory = serial_factory
        self.ser = None

    def __enter__(self):
        try:
            s = self._factory()
            s.port = self.port_name
            s.baudrate = BAUD
            s.timeout = READ_TIMEOUT_S
            s.write_timeout = 2.0
            s.dtr = False
            s.rts = False
            s.open()
        except ProvisionError:
            raise
        except Exception as e:
            raise ProvisionError(f"Could not open {self.port_name}: {type(e).__name__}") from e
        self.ser = s
        if self.reset:
            s.rts = True
            self.sleep(0.1)
            s.rts = False
        try:
            s.reset_input_buffer()
        except Exception:
            pass
        return self

    def __exit__(self, *exc):
        try:
            if self.ser is not None:
                self.ser.close()
        except Exception:
            pass
        return False

    def _log(self, line: str) -> None:
        if len(self.logs) < MAX_LOG_LINES:
            self.logs.append(scrub(line[:300], self.secrets))

    def read_reply(self, timeout: float = REPLY_TIMEOUT_S) -> dict:
        deadline = self.clock() + timeout
        while self.clock() < deadline:
            raw = self.ser.readline()
            if not raw:
                continue
            if len(raw) > MAX_LINE_BYTES:
                self._log("[oversized line skipped]")
                continue
            s = raw.decode("utf-8", errors="replace").strip()
            if not s.startswith("{"):
                if s:
                    self._log(s)
                continue
            try:
                obj = json.loads(s)
            except ValueError:
                self._log("[malformed JSON line skipped]")
                continue
            if isinstance(obj, dict) and obj.get("v") == PROTOCOL_VERSION and "ok" in obj:
                return obj
            self._log("[non-v1 JSON line skipped]")
        raise ProvisionTimeout("No reply from board (timeout). Is it running firmware "
                               "with serial provisioning, and inside its 10 s window?")

    def transact(self, cmd: str, timeout: float = REPLY_TIMEOUT_S, **kw) -> dict:
        try:
            self.ser.write(encode(cmd, **kw))
            self.ser.flush()
        except ProvisionError:
            raise
        except Exception as e:
            raise ProvisionError(f"Serial write failed: {type(e).__name__}") from e
        return self.safe(self.read_reply(timeout))

    def safe(self, reply: dict) -> dict:
        r = redact(reply, self.project)
        if isinstance(r.get("err"), str):
            r["err"] = scrub(r["err"], self.secrets)
        return r

    def hello(self, timeout: float = HELLO_TIMEOUT_S) -> dict:
        """Send hello repeatedly until a reply arrives or timeout (boot window)."""
        deadline = self.clock() + timeout
        while True:
            left = deadline - self.clock()
            if left <= 0:
                raise ProvisionTimeout("No hello reply. Reset the board (or tick 'reset on "
                                       "open') and retry within its 10 s window; the board "
                                       "must run firmware with serial provisioning.")
            try:
                r = self.transact("hello", timeout=min(1.5, left))
            except ProvisionTimeout:
                self.sleep(HELLO_RETRY_S)
                continue
            if r.get("ok") and isinstance(r.get("project"), str):
                self.project = r["project"]
            return r


def _info(sess: Session, hello: dict) -> dict:
    project, env = hello.get("project"), hello.get("env")
    out = {"hello": hello, "logs": sess.logs, "hardware_tested": False}
    try:
        out["schema"] = get_schema(project, env)
    except SchemaError as e:
        out["schema"] = None
        out["schema_error"] = str(e)
    return out


def _require_hello(sess: Session) -> dict:
    h = sess.hello()
    if not h.get("ok"):
        raise ProvisionError("Board rejected hello: " + str(h.get("err", "unknown")))
    return h


def do_hello(port: str, reset: bool = False, **kw) -> dict:
    with Session(port, reset=reset, **kw) as s:
        return _info(s, _require_hello(s))


def do_get(port: str, reset: bool = False, **kw) -> dict:
    with Session(port, reset=reset, **kw) as s:
        out = _info(s, _require_hello(s))
        out["reply"] = s.transact("get")
        return out


def do_apply(port: str, cfg: dict, reset: bool = False, **kw) -> dict:
    with Session(port, reset=reset, **kw) as s:
        s.secrets = [v for v in (cfg.values() if isinstance(cfg, dict) else []) if isinstance(v, str)]
        h = _require_hello(s)
        out = _info(s, h)
        clean = validate_cfg(h.get("project"), h.get("env"), cfg)   # raises SchemaError
        out["reply"] = s.transact("provision", cfg=clean)
        out["sent_keys"] = sorted(clean)
        out["note"] = "Changes apply after a reboot."
        return out


def do_simple(port: str, cmd: str, reset: bool = False, **kw) -> dict:
    if cmd not in ("reboot", "factory_reset"):
        raise ProvisionError("Command not allowed.")
    with Session(port, reset=reset, **kw) as s:
        out = _info(s, _require_hello(s))
        out["reply"] = s.transact(cmd)
        return out
