"""ESP32 flashing endpoints. Subprocess and serial are mocked: no hardware needed.

These tests prove validation and command construction only; real flashing is
untested on hardware.
"""
import io
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("paramiko")
pytest.importorskip("httpx")
pytest.importorskip("multipart")

from fastapi.testclient import TestClient  # noqa: E402

import esp32_flasher  # noqa: E402
import server  # noqa: E402

FAKE_ESPTOOL = ["/usr/bin/esptool"]


@pytest.fixture
def api(monkeypatch):
    popen_calls = []

    class FakeProc:
        def __init__(self, cmd, **kw):
            popen_calls.append((cmd, kw))
            self.fw_existed = os.path.exists(cmd[-1])
            self.stdout = iter(["Connecting....\n", "Hash of data verified.\n"])
            self.returncode = 0

        def wait(self):
            return 0

    monkeypatch.setattr(esp32_flasher.subprocess, "Popen", FakeProc)
    monkeypatch.setattr(esp32_flasher, "find_esptool", lambda: list(FAKE_ESPTOOL))
    with TestClient(server.app) as client:
        client.popen_calls = popen_calls
        yield client


def flash(client, fw=b"\xe9" * 1024, name="app.bin", **form):
    data = {"port": "/dev/ttyUSB0", "chip": "esp32", "baud": "460800", "address": "0x10000"}
    data.update(form)
    return client.post("/api/esp32/flash", data=data,
                       files={"firmware": (name, io.BytesIO(fw), "application/octet-stream")})


def test_flash_builds_list_command_and_streams(api):
    r = flash(api)
    assert r.status_code == 200, r.text
    assert "Hash of data verified." in r.text
    assert "[EXIT 0]" in r.text
    (cmd, kw), = api.popen_calls
    assert kw.get("shell") is False
    assert cmd[:-1] == FAKE_ESPTOOL + ["--chip", "esp32", "--port", "/dev/ttyUSB0",
                                       "--baud", "460800", "write_flash", "0x10000"]
    assert cmd[-1].endswith(".bin")
    assert not os.path.exists(cmd[-1])  # temp firmware cleaned up


@pytest.mark.parametrize("port", ["/dev/ttyUSB0; rm -rf /", "$(id)", "/etc/passwd",
                                  "COM3 && calc", "", "../dev/ttyUSB0", "/dev/ttyUSB0\n"])
def test_rejects_bad_port(api, port):
    assert flash(api, port=port).status_code in (400, 422)
    assert api.popen_calls == []


@pytest.mark.parametrize("chip", ["esp33", "esp32;id", "ESP32 --erase"])
def test_rejects_bad_chip(api, chip):
    assert flash(api, chip=chip).status_code == 400
    assert api.popen_calls == []


@pytest.mark.parametrize("baud", ["123", "abc", "-1", "460800 --x", "460800\n"])
def test_rejects_bad_baud(api, baud):
    assert flash(api, baud=baud).status_code == 400
    assert api.popen_calls == []


@pytest.mark.parametrize("addr", ["10000", "0x", "0xZZ", "0x10001", "0x1000000",
                                  "0x10000;id", "-0x1000", "0x123456789"])
def test_rejects_bad_address(api, addr):
    assert flash(api, address=addr).status_code == 400
    assert api.popen_calls == []


@pytest.mark.parametrize("name,fw", [("app.elf", b"x"), ("app.bin", b""), ("noext", b"x")])
def test_rejects_bad_firmware(api, name, fw):
    assert flash(api, fw=fw, name=name).status_code == 400
    assert api.popen_calls == []


def test_rejects_firmware_past_end_of_flash(api):
    r = flash(api, fw=b"x" * 0x2000, address="0xfff000")
    assert r.status_code == 400


def test_esptool_missing_returns_503(api, monkeypatch):
    monkeypatch.setattr(esp32_flasher, "find_esptool", lambda: None)
    r = flash(api)
    assert r.status_code == 503
    assert "pip install esptool" in r.json()["detail"]
    assert api.popen_calls == []
    s = api.get("/api/esp32/status").json()
    assert s["esptool_available"] is False and s["hardware_tested"] is False


def test_status_reports_available(api):
    s = api.get("/api/esp32/status").json()
    assert s["esptool_available"] is True
    assert "esp32" in s["chips"] and 460800 in s["bauds"]


def test_port_listing_uses_pyserial(api, monkeypatch):
    import sys
    import types

    class P:
        def __init__(self, d, desc):
            self.device, self.description, self.hwid = d, desc, "USB VID:PID=10C4:EA60"

    lp = types.ModuleType("serial.tools.list_ports")
    lp.comports = lambda: [P("/dev/ttyUSB1", "CP2102"), P("/dev/ttyACM0", "USB JTAG")]
    tools = types.ModuleType("serial.tools")
    tools.list_ports = lp
    serial = types.ModuleType("serial")
    serial.tools = tools
    monkeypatch.setitem(sys.modules, "serial", serial)
    monkeypatch.setitem(sys.modules, "serial.tools", tools)
    monkeypatch.setitem(sys.modules, "serial.tools.list_ports", lp)
    ports = api.get("/api/esp32/ports").json()["ports"]
    assert [p["device"] for p in ports] == ["/dev/ttyACM0", "/dev/ttyUSB1"]
    assert ports[1]["description"] == "CP2102"


def test_port_listing_falls_back_without_pyserial(api, monkeypatch):
    import sys
    monkeypatch.setitem(sys.modules, "serial", None)
    monkeypatch.setitem(sys.modules, "serial.tools", None)
    monkeypatch.setattr(esp32_flasher.glob, "glob",
                        lambda pat: ["/dev/ttyUSB0"] if pat == "/dev/ttyUSB*" else [])
    ports = api.get("/api/esp32/ports").json()["ports"]
    assert ports == [{"device": "/dev/ttyUSB0", "description": "", "hwid": ""}]


def test_find_esptool_none_when_absent(monkeypatch):
    monkeypatch.setattr(esp32_flasher.shutil, "which", lambda n: None)
    monkeypatch.setattr(esp32_flasher.importlib.util, "find_spec", lambda n: None)
    assert esp32_flasher.find_esptool() is None


def test_find_esptool_prefers_path(monkeypatch):
    monkeypatch.setattr(esp32_flasher.shutil, "which",
                        lambda n: "/opt/bin/esptool" if n == "esptool" else None)
    assert esp32_flasher.find_esptool() == ["/opt/bin/esptool"]


@pytest.mark.parametrize("port", ["/dev/ttyUSB0", "/dev/ttyACM12", "COM3",
                                  "/dev/cu.usbserial-0001", "/dev/tty.SLAB_USBtoUART"])
def test_accepts_good_ports(port):
    assert esp32_flasher.validate_port(port) == port
