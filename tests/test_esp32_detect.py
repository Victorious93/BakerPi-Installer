"""ESP32 detection / chip-info endpoints (feature 2).

pyserial and subprocess are mocked and esptool output is canned sample text:
no hardware needed, and real-board behaviour is UNTESTED ON HARDWARE.
"""
import subprocess
import sys
import types

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("paramiko")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

import esp32_flasher  # noqa: E402
import server  # noqa: E402

FAKE_ESPTOOL = ["/usr/bin/esptool"]

V4_FLASH_ID = """esptool.py v4.7.0
Serial port /dev/ttyUSB0
Connecting....
Detecting chip type... ESP32
Chip is ESP32-D0WD-V3 (revision v3.0)
Features: WiFi, BT, Dual Core, 240MHz, VRef calibration in efuse, Coding Scheme None
Crystal is 40MHz
MAC: 24:0A:C4:12:34:56
Uploading stub...
Running stub...
Stub running...
Manufacturer: c8
Device: 4016
Detected flash size: 4MB
Hard resetting via RTS pin...
"""

V5_FLASH_ID = """esptool v5.0.0
Connected to ESP32-S3 on /dev/ttyACM0:
Chip type:          ESP32-S3 (QFN56) (revision v0.2)
Features:           Wi-Fi, BT 5 (LE), Dual Core + LP Core, 240MHz
Crystal frequency:  40MHz
MAC:                f4:12:fa:aa:bb:cc
Manufacturer: 20
Device: 4018
Detected flash size: 16MB
"""

V4_CHIP_ID = """Chip is ESP8266EX
MAC: 5c:cf:7f:01:02:03
Chip ID: 0x00010203
"""


class FakeRun:
    def __init__(self, stdout="", code=0, exc=None):
        self.calls, self.stdout, self.code, self.exc = [], stdout, code, exc

    def __call__(self, cmd, **kw):
        self.calls.append((cmd, kw))
        if self.exc:
            raise self.exc
        return types.SimpleNamespace(stdout=self.stdout, returncode=self.code)


@pytest.fixture
def api(monkeypatch):
    run = FakeRun(V4_FLASH_ID)
    monkeypatch.setattr(esp32_flasher.subprocess, "run", run)
    monkeypatch.setattr(esp32_flasher, "find_esptool", lambda: list(FAKE_ESPTOOL))
    with TestClient(server.app) as client:
        client.run = run
        yield client


def info(client, **form):
    data = {"port": "/dev/ttyUSB0"}
    data.update(form)
    return client.post("/api/esp32/chip-info", data=data)


def fake_pyserial(monkeypatch, ports):
    lp = types.ModuleType("serial.tools.list_ports")
    lp.comports = lambda: ports
    tools = types.ModuleType("serial.tools")
    tools.list_ports = lp
    serial = types.ModuleType("serial")
    serial.tools = tools
    monkeypatch.setitem(sys.modules, "serial", serial)
    monkeypatch.setitem(sys.modules, "serial.tools", tools)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", lp)


def port(device, vid=None, pid=None, **kw):
    d = dict(device=device, description="", hwid="", vid=vid, pid=pid,
             manufacturer=None, product=None, serial_number=None, location=None)
    d.update(kw)
    return types.SimpleNamespace(**d)


# ── parsing ──────────────────────────────────────────────────────────────────

def test_parse_v4_flash_id():
    i = esp32_flasher.parse_esptool_info(V4_FLASH_ID)
    assert i["chip"] == "ESP32-D0WD-V3 (revision v3.0)"
    assert i["chip_family"] == "ESP32"
    assert i["features"].startswith("WiFi, BT, Dual Core")
    assert i["crystal"] == "40MHz"
    assert i["mac"] == "24:0a:c4:12:34:56"
    assert i["flash_manufacturer"] == "c8" and i["flash_device"] == "4016"
    assert i["flash_size"] == "4MB"
    assert i["chip_id"] is None


def test_parse_v5_flash_id():
    i = esp32_flasher.parse_esptool_info(V5_FLASH_ID)
    assert i["chip"] == "ESP32-S3 (QFN56) (revision v0.2)"
    assert i["chip_family"] == "ESP32-S3"
    assert i["crystal"] == "40MHz"
    assert i["mac"] == "f4:12:fa:aa:bb:cc"
    assert i["flash_size"] == "16MB"


def test_parse_chip_id_and_derived_family():
    i = esp32_flasher.parse_esptool_info(V4_CHIP_ID)
    assert i["chip_id"] == "0x00010203"
    assert i["chip_family"] == "ESP8266EX"
    assert i["flash_size"] is None


def test_parse_garbage_is_all_none():
    i = esp32_flasher.parse_esptool_info("A fatal error occurred: Failed to connect\n")
    assert all(v is None for v in i.values())


# ── chip-info endpoint ───────────────────────────────────────────────────────

def test_chip_info_runs_list_command_and_parses(api):
    r = info(api)
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["ok"] is True and d["hardware_tested"] is False
    assert d["info"]["mac"] == "24:0a:c4:12:34:56" and d["info"]["flash_size"] == "4MB"
    (cmd, kw), = api.run.calls
    assert kw.get("shell") is False and kw.get("timeout")
    assert cmd == FAKE_ESPTOOL + ["--chip", "auto", "--port", "/dev/ttyUSB0",
                                  "--baud", "115200", "flash_id"]


@pytest.mark.parametrize("op", ["read_mac", "chip_id"])
def test_chip_info_other_ops(api, op):
    assert info(api, op=op, chip="esp32").status_code == 200
    assert api.run.calls[0][0][-1] == op


def test_chip_info_nonzero_exit(api):
    api.run.stdout, api.run.code = "A fatal error occurred: Failed to connect\n", 2
    d = info(api).json()
    assert d["ok"] is False and d["exit_code"] == 2 and d["info"]["chip"] is None


def test_chip_info_timeout(api):
    api.run.exc = subprocess.TimeoutExpired(["esptool"], 45)
    d = info(api).json()
    assert d["exit_code"] == 124 and "Timed out" in d["output"]


def test_chip_info_exec_not_found(api):
    api.run.exc = FileNotFoundError()
    assert info(api).json()["exit_code"] == 127


@pytest.mark.parametrize("form", [
    {"port": "/dev/ttyUSB0; id"}, {"port": "$(reboot)"}, {"port": "/etc/shadow"},
    {"port": "COM3\n"}, {"op": "erase_flash"}, {"op": "write_flash"},
    {"op": "flash_id --after hard_reset"}, {"chip": "esp99"}, {"baud": "1234"},
    {"baud": "115200;id"},
])
def test_chip_info_rejects_bad_input(api, form):
    assert info(api, **form).status_code in (400, 422)
    assert api.run.calls == []


def test_chip_info_esptool_missing_503(api, monkeypatch):
    monkeypatch.setattr(esp32_flasher, "find_esptool", lambda: None)
    r = info(api)
    assert r.status_code == 503 and "pip install esptool" in r.json()["detail"]
    assert api.run.calls == []


# ── device enumeration ───────────────────────────────────────────────────────

def test_devices_with_pyserial(api, monkeypatch):
    fake_pyserial(monkeypatch, [
        port("/dev/ttyUSB0", 0x10C4, 0xEA60, description="CP2102 USB to UART",
             manufacturer="Silicon Labs", product="CP2102", serial_number="0001",
             hwid="USB VID:PID=10C4:EA60 SER=0001"),
        port("/dev/ttyS0", description="n/a"),
        port("/dev/ttyACM0", 0x303A, 0x1001, manufacturer="Espressif"),
    ])
    d = api.get("/api/esp32/devices").json()
    assert d["pyserial"] is True and d["esptool_available"] is True
    assert d["hardware_tested"] is False
    devs = {x["device"]: x for x in d["devices"]}
    assert list(devs) == ["/dev/ttyACM0", "/dev/ttyS0", "/dev/ttyUSB0"]
    u = devs["/dev/ttyUSB0"]
    assert u["vid_pid"] == "10C4:EA60" and u["manufacturer"] == "Silicon Labs"
    assert u["likely_esp32"] is True and "CP210x" in u["bridge"]
    assert u["serial_number"] == "0001"
    assert devs["/dev/ttyS0"]["usb"] is False and devs["/dev/ttyS0"]["vid_pid"] == ""
    assert devs["/dev/ttyACM0"]["likely_esp32"] is True


def test_devices_unknown_vid_not_likely(api, monkeypatch):
    fake_pyserial(monkeypatch, [port("/dev/ttyACM1", 0x2341, 0x0043)])
    (d,) = api.get("/api/esp32/devices").json()["devices"]
    assert d["vid_pid"] == "2341:0043" and d["likely_esp32"] is False


def test_devices_without_pyserial_or_esptool(api, monkeypatch):
    monkeypatch.setitem(sys.modules, "serial", None)
    monkeypatch.setitem(sys.modules, "serial.tools", None)
    monkeypatch.setattr(esp32_flasher, "find_esptool", lambda: None)
    monkeypatch.setattr(esp32_flasher.glob, "glob",
                        lambda pat: ["/dev/ttyUSB0"] if pat == "/dev/ttyUSB*" else [])
    d = api.get("/api/esp32/devices").json()
    assert d["pyserial"] is False and d["esptool_available"] is False
    (dev,) = d["devices"]
    assert dev["device"] == "/dev/ttyUSB0" and dev["vid_pid"] == "" and dev["usb"] is False
