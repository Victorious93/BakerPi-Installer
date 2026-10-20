"""ESP32 fleet firmware profiles (feature 4). Subprocess mocked: no hardware.

Proves validation and command construction only; untested on hardware.
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
import esp32_fleet_profiles as fp  # noqa: E402
import server  # noqa: E402

FAKE = ["/usr/bin/esptool"]


@pytest.fixture
def api(monkeypatch):
    calls = []

    class FakeProc:
        def __init__(self, cmd, **kw):
            calls.append((cmd, kw))
            self.stdout = iter(["Hash of data verified.\n"])
            self.returncode = 0

        def wait(self):
            return 0

    monkeypatch.setattr(esp32_flasher.subprocess, "Popen", FakeProc)
    monkeypatch.setattr(esp32_flasher, "find_esptool", lambda: list(FAKE))
    with TestClient(server.app) as c:
        c.calls = calls
        yield c


def make_build(tmp_path, names=("bootloader.bin", "partitions.bin", "firmware.bin"),
               extra=("firmware.elf",)):
    d = tmp_path / "build"
    d.mkdir()
    for n in names:
        (d / n).write_bytes(b"\xe9" * 512)
    for n in extra:
        (d / n).write_bytes(b"x")
    return d


def post(c, files=None, **form):
    data = {"profile": "victormodem", "env": "esp32s3_bridge5g", "port": "/dev/ttyACM0"}
    data.update(form)
    return c.post("/api/esp32/fleet/flash", data=data, files=files or {})


def test_profiles_facts():
    vm = fp.PROFILES["victormodem"]["envs"]
    for e in ("esp32s3_bridge5g", "esp32s3_direct4g"):
        assert vm[e]["chip"] == "esp32s3" and vm[e]["images"]["bootloader"] == "0x0"
        assert vm[e]["flash_args"] == []  # no hardcoded flash mode/size (no N16R8)
    assert vm["tsim7600_4g"]["chip"] == "esp32"
    assert vm["tsim7600_4g"]["images"]["bootloader"] == "0x1000"
    for e in vm.values():
        assert {k: e["images"][k] for k in ("partitions", "boot_app0", "firmware")} == \
            {"partitions": "0x8000", "boot_app0": "0xe000", "firmware": "0x10000"}
    pc = fp.PROFILES["pyra-claw"]["envs"]
    assert list(pc) == ["esp32dev"] and pc["esp32dev"]["chip"] == "esp32"
    assert pc["esp32dev"]["flash_args"] == ["--flash_mode", "dio", "--flash_freq", "40m",
                                            "--flash_size", "detect"]
    for p in fp.PROFILES.values():
        assert not p["published_binaries"] and not p["offsets_verified"]
        assert not p["serial_provisioning"]


def test_list_endpoint(api):
    r = api.get("/api/esp32/fleet/profiles")
    assert r.status_code == 200
    j = r.json()
    assert j["hardware_tested"] is False
    assert {p["id"] for p in j["profiles"]} == {"victormodem", "pyra-claw"}


def test_flash_from_build_dir_without_boot_app0(api, tmp_path):
    d = make_build(tmp_path)
    r = post(api, build_dir=str(d))
    assert r.status_code == 200, r.text
    assert "Not flashing boot_app0.bin" in r.text and "[EXIT 0]" in r.text
    (cmd, kw), = api.calls
    assert kw["shell"] is False
    assert cmd == FAKE + ["--chip", "esp32s3", "--port", "/dev/ttyACM0", "--baud", "460800",
                          "write_flash", "0x0", str(d / "bootloader.bin"),
                          "0x8000", str(d / "partitions.bin"),
                          "0x10000", str(d / "firmware.bin")]


def test_pyra_with_uploaded_boot_app0(api, tmp_path):
    d = make_build(tmp_path)
    r = post(api, profile="pyra-claw", env="esp32dev", build_dir=str(d),
             files={"boot_app0": ("boot_app0.bin", io.BytesIO(b"\x00" * 100))})
    assert r.status_code == 200, r.text
    (cmd, _), = api.calls
    i = cmd.index("write_flash")
    assert cmd[i + 1:i + 7] == ["--flash_mode", "dio", "--flash_freq", "40m",
                                "--flash_size", "detect"]
    assert cmd[cmd.index("0x1000") + 1] == str(d / "bootloader.bin")
    boot = cmd[cmd.index("0xe000") + 1]
    assert boot.endswith("boot_app0.bin") and not os.path.exists(boot)  # temp cleaned


def test_all_uploads_no_build_dir(api):
    f = {r: (n, io.BytesIO(b"\xe9" * 64)) for r, n in fp.IMAGE_FILES.items()}
    r = post(api, env="tsim7600_4g", files=f)
    assert r.status_code == 200, r.text
    (cmd, _), = api.calls
    assert cmd[cmd.index("--chip") + 1] == "esp32"
    assert [cmd[i] for i in range(cmd.index("write_flash") + 1, len(cmd), 2)] == \
        ["0x1000", "0x8000", "0xe000", "0x10000"]


def test_missing_required_image(api, tmp_path):
    d = make_build(tmp_path, names=("bootloader.bin", "partitions.bin"))
    r = post(api, build_dir=str(d))
    assert r.status_code == 400 and "firmware.bin" in r.text
    assert api.calls == []


@pytest.mark.parametrize("bd", ["relative/dir", "/tmp/../etc", "/nonexistent/xyz",
                                "/tmp/x\n", "/tmp/\x00x"])
def test_bad_build_dir(api, bd):
    assert post(api, build_dir=bd).status_code == 400
    assert api.calls == []


def test_build_dir_is_file(api, tmp_path):
    f = tmp_path / "f"
    f.write_text("x")
    assert post(api, build_dir=str(f)).status_code == 400


def test_symlink_out_of_build_dir_refused(api, tmp_path):
    d = make_build(tmp_path, names=("bootloader.bin", "partitions.bin"))
    secret = tmp_path / "secret.bin"
    secret.write_bytes(b"s" * 10)
    os.symlink(secret, d / "firmware.bin")
    assert post(api, build_dir=str(d)).status_code == 400
    assert api.calls == []


@pytest.mark.parametrize("form", [{"profile": "evil"}, {"env": "esp32s3;id"},
                                  {"profile": "pyra-claw", "env": "esp32s3_bridge5g"},
                                  {"port": "/dev/ttyUSB0; rm -rf /"}, {"baud": "123"}])
def test_rejects_bad_inputs(api, tmp_path, form):
    d = make_build(tmp_path)
    assert post(api, build_dir=str(d), **form).status_code in (400, 422)
    assert api.calls == []


def test_rejects_non_bin_upload(api, tmp_path):
    d = make_build(tmp_path)
    r = post(api, build_dir=str(d), files={"boot_app0": ("x.sh", io.BytesIO(b"#!"))})
    assert r.status_code == 400


def test_overlap_detected(api, tmp_path):
    d = make_build(tmp_path, names=("partitions.bin", "firmware.bin"))
    (d / "bootloader.bin").write_bytes(b"\xe9" * 0x9000)  # 0x0 + 36K runs past 0x8000
    assert post(api, build_dir=str(d)).status_code == 400


def test_esptool_missing(api, tmp_path, monkeypatch):
    monkeypatch.setattr(esp32_flasher, "find_esptool", lambda: None)
    assert post(api, build_dir=str(make_build(tmp_path))).status_code == 503
