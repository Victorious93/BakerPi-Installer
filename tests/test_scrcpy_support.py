"""Optional scrcpy + adb support. subprocess / shutil.which / platform are
mocked: no real installs, adb calls or scrcpy windows. Proves detection,
command construction, validation and parsing only; untested on hardware."""
import subprocess

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("paramiko")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import scrcpy_support as sc  # noqa: E402
import server  # noqa: E402

ADB_OUT = """* daemon not running; starting now at tcp:5037
* daemon started successfully
List of devices attached
R58M123ABC             device usb:1-1 product:a52qnsxx model:SM_A525F device:a52q transport_id:2
emulator-5554          device product:sdk_gphone64 model:sdk_gphone64_x86_64 device:emu64x transport_id:1
0123456789ABCDEF       unauthorized usb:1-2 transport_id:3
FA79L1A00001           no permissions (user in plugdev group; are your udev rules wrong?); see [http://developer.android.com/tools/device.html] usb:3-1 transport_id:4
192.168.1.20:5555      offline transport_id:5

"""


class R:
    def __init__(self, rc=0, stdout="", stderr=""):
        self.returncode, self.stdout, self.stderr = rc, stdout, stderr


@pytest.fixture
def env(monkeypatch, tmp_path):
    osr = tmp_path / "os-release"
    osr.write_text('PRETTY_NAME="Raspbian GNU/Linux 12"\nID=raspbian\nID_LIKE=debian\n')
    real_osr = sc._os_release_ids
    monkeypatch.setattr(sc, "_os_release_ids", lambda path=str(osr): real_osr(path))
    monkeypatch.setattr(sc.platform, "system", lambda: "Linux")
    monkeypatch.setenv("DISPLAY", ":0")
    have = {"scrcpy", "adb", "apt-get", "sudo"}
    monkeypatch.setattr(sc.shutil, "which", lambda n: f"/usr/bin/{n}" if n in have else None)
    monkeypatch.setattr(sc, "_is_root", lambda: False)
    runs, popens = [], []

    def fake_run(cmd, **kw):
        runs.append((cmd, kw))
        assert kw.get("shell") is False
        if cmd[1:] == ["--version"]:
            return R(stdout="scrcpy 2.4 <https://github.com/Genymobile/scrcpy>\n")
        if cmd[1:] == ["version"]:
            return R(stdout="Android Debug Bridge version 1.0.41\nVersion 34.0.5\n")
        if cmd[1:] == ["devices", "-l"]:
            return R(stdout=ADB_OUT)
        raise AssertionError(cmd)

    class FakeProc:
        rc = 0
        exits_fast = False

        def __init__(self, cmd, **kw):
            popens.append((cmd, kw))
            assert kw.get("shell") is False
            self.cmd, self.pid = cmd, 4242
            self.stdout = iter([f"ran {cmd[0]}\n"])
            self.returncode = FakeProc.rc

        def wait(self, timeout=None):
            if timeout is not None and not FakeProc.exits_fast:
                raise subprocess.TimeoutExpired(self.cmd, timeout)
            return self.returncode

    monkeypatch.setattr(sc.subprocess, "run", fake_run)
    monkeypatch.setattr(sc.subprocess, "Popen", FakeProc)
    with TestClient(server.app) as client:
        client.runs, client.popens, client.proc, client.have = runs, popens, FakeProc, have
        yield client


# ── status / detection ───────────────────────────────────────────────────────

def test_status_detects_versions_and_route(env):
    st = env.get("/api/scrcpy/status").json()
    assert st["hardware_tested"] is False and st["optional"] is True
    assert st["scrcpy"] == {"installed": True, "path": "/usr/bin/scrcpy", "version": "2.4"}
    assert st["adb"]["version"] == "1.0.41"
    assert st["install_route"] == "apt" and st["manual"] is None
    assert st["credit"] == "scrcpy by Genymobile, Apache-2.0"
    assert st["url"] == "https://github.com/Genymobile/scrcpy"
    assert env.popens == []  # status never installs or launches anything


def test_status_not_installed(env):
    env.have.difference_update({"scrcpy", "adb"})
    st = env.get("/api/scrcpy/status").json()
    assert st["scrcpy"] == {"installed": False, "path": None, "version": None}
    assert st["adb"]["installed"] is False
    assert env.runs == []


def test_version_handles_failure(monkeypatch):
    monkeypatch.setattr(sc.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    assert sc._version(["/x/scrcpy", "--version"]) is None


@pytest.mark.parametrize("system,tool,route", [
    ("Windows", "winget", "winget"), ("Darwin", "brew", "brew"),
    ("Windows", None, None), ("Darwin", None, None), ("FreeBSD", None, None)])
def test_install_route_by_platform(monkeypatch, system, tool, route):
    monkeypatch.setattr(sc.platform, "system", lambda: system)
    monkeypatch.setattr(sc.shutil, "which", lambda n: f"/bin/{n}" if n == tool else None)
    assert sc.install_route() == route


def test_install_route_non_debian_linux(monkeypatch, tmp_path):
    osr = tmp_path / "os-release"
    osr.write_text('ID=fedora\nID_LIKE="rhel centos"\n')
    monkeypatch.setattr(sc.platform, "system", lambda: "Linux")
    monkeypatch.setattr(sc.shutil, "which", lambda n: "/usr/bin/" + n)
    real = sc._os_release_ids
    monkeypatch.setattr(sc, "_os_release_ids", lambda path=str(osr): real(path))
    assert sc.install_route() is None
    ubuntu = tmp_path / "u"
    ubuntu.write_text("ID=ubuntu\nID_LIKE=debian\n")
    assert real(str(ubuntu)) >= {"ubuntu", "debian"}


# ── install ──────────────────────────────────────────────────────────────────

def test_install_requires_explicit_confirm(env):
    for body in ({}, {"confirm": False}):
        r = env.post("/api/scrcpy/install", json=body)
        assert r.status_code == 400 and "off by default" in r.json()["detail"]
    assert env.post("/api/scrcpy/install", json={"confirm": "yes"}).status_code == 422
    assert env.popens == []


def test_apt_install_uses_sudo_n_when_not_root(env):
    r = env.post("/api/scrcpy/install", json={"confirm": True})
    assert r.status_code == 200 and "[EXIT 0]" in r.text
    cmds = [c for c, _ in env.popens]
    assert cmds == [["sudo", "-n", "apt-get", "update"],
                    ["sudo", "-n", "apt-get", "install", "-y", "scrcpy", "adb"]]
    assert env.popens[0][1]["env"]["DEBIAN_FRONTEND"] == "noninteractive"


def test_apt_install_as_root_no_sudo(env, monkeypatch):
    monkeypatch.setattr(sc, "_is_root", lambda: True)
    assert sc.build_install_steps("apt") == [
        ["apt-get", "update"], ["apt-get", "install", "-y", "scrcpy", "adb"]]


def test_apt_install_without_sudo_returns_424(env):
    env.have.discard("sudo")
    r = env.post("/api/scrcpy/install", json={"confirm": True})
    assert r.status_code == 424
    assert r.json()["detail"]["missing"] == ["sudo"]
    assert env.popens == []


def test_install_failure_stops_and_hints_sudo(env):
    env.proc.rc = 1
    r = env.post("/api/scrcpy/install", json={"confirm": True})
    assert "[EXIT 1]" in r.text and "sudo needs a password" in r.text
    assert len(env.popens) == 1
    assert sc.acquire()  # lock released after the stream ended
    sc._install_lock.release()


def test_winget_and_brew_commands():
    assert sc.build_install_steps("winget") == [[
        "winget", "install", "--exact", "--id", "Genymobile.scrcpy",
        "--accept-source-agreements", "--accept-package-agreements"]]
    assert sc.build_install_steps("brew") == [
        ["brew", "install", "scrcpy"], ["brew", "install", "--cask", "android-platform-tools"]]
    with pytest.raises(sc.ScrcpyValidationError):
        sc.build_install_steps("pacman")


def test_no_route_returns_manual_instructions(env, monkeypatch):
    monkeypatch.setattr(sc.platform, "system", lambda: "FreeBSD")
    st = env.get("/api/scrcpy/status").json()
    assert st["install_route"] is None
    assert st["manual"]["url"] == "https://github.com/Genymobile/scrcpy"
    r = env.post("/api/scrcpy/install", json={"confirm": True})
    assert r.status_code == 424
    d = r.json()["detail"]
    assert d["manual"]["url"] == "https://github.com/Genymobile/scrcpy"
    assert "github.com/Genymobile/scrcpy" in d["manual"]["text"]
    assert env.popens == []


def test_install_busy_409(env):
    assert sc.acquire()
    try:
        assert env.post("/api/scrcpy/install", json={"confirm": True}).status_code == 409
    finally:
        sc._install_lock.release()


# ── devices ──────────────────────────────────────────────────────────────────

def test_parse_adb_devices():
    devs = sc.parse_adb_devices(ADB_OUT)
    assert [d["serial"] for d in devs] == [
        "R58M123ABC", "emulator-5554", "0123456789ABCDEF", "FA79L1A00001", "192.168.1.20:5555"]
    assert [d["state"] for d in devs] == [
        "device", "device", "unauthorized", "no permissions", "offline"]
    assert devs[0]["model"] == "SM_A525F" and devs[0]["usb"] == "1-1"
    assert devs[0]["transport_id"] == "2" and devs[0]["ready"] is True
    assert devs[3]["usb"] == "3-1" and devs[3]["ready"] is False
    assert sc.parse_adb_devices("List of devices attached\n\n") == []


def test_devices_endpoint(env):
    r = env.get("/api/scrcpy/devices")
    assert r.status_code == 200 and len(r.json()["devices"]) == 5
    assert env.runs[-1][0] == ["/usr/bin/adb", "devices", "-l"]


def test_devices_without_adb_424(env):
    env.have.discard("adb")
    r = env.get("/api/scrcpy/devices")
    assert r.status_code == 424 and r.json()["detail"]["missing"] == ["adb"]


def test_devices_adb_error_502(env, monkeypatch):
    monkeypatch.setattr(sc.subprocess, "run", lambda cmd, **k: R(1, "", "boom"))
    r = env.get("/api/scrcpy/devices")
    assert r.status_code == 502 and "boom" in r.json()["detail"]


# ── view ─────────────────────────────────────────────────────────────────────

def test_view_launches_non_blocking(env):
    r = env.post("/api/scrcpy/view", json={"serial": "R58M123ABC", "max_size": 1024})
    assert r.status_code == 200, r.text
    j = r.json()
    assert j["launched"] is True and j["pid"] == 4242
    cmd, kw = env.popens[-1]
    assert cmd == ["/usr/bin/scrcpy", "--serial", "R58M123ABC", "--max-size", "1024"]
    assert kw["shell"] is False and kw["start_new_session"] is True
    assert kw["stdin"] is subprocess.DEVNULL


def test_view_network_serial_without_max_size(env):
    r = env.post("/api/scrcpy/view", json={"serial": "emulator-5554"})
    assert r.status_code == 200
    assert env.popens[-1][0] == ["/usr/bin/scrcpy", "--serial", "emulator-5554"]


@pytest.mark.parametrize("serial", [
    "", "-s", "--help", "abc def", "abc;rm -rf /", "a|b", "$(id)", "x" * 200, "a\nb"])
def test_view_rejects_bad_serial(env, serial):
    r = env.post("/api/scrcpy/view", json={"serial": serial})
    assert r.status_code == 400
    assert env.popens == [] and env.runs == []


@pytest.mark.parametrize("max_size", [-1, 9000, True, "800", 1.5])
def test_view_rejects_bad_max_size(env, max_size):
    r = env.post("/api/scrcpy/view", json={"serial": "R58M123ABC", "max_size": max_size})
    assert r.status_code in (400, 422)
    assert env.popens == []


def test_view_unknown_and_unready_devices(env):
    assert env.post("/api/scrcpy/view", json={"serial": "NOTHERE1"}).status_code == 404
    r = env.post("/api/scrcpy/view", json={"serial": "0123456789ABCDEF"})
    assert r.status_code == 409 and "unauthorized" in r.json()["detail"]
    assert env.popens == []


def test_view_requires_scrcpy_and_display(env, monkeypatch):
    env.have.discard("scrcpy")
    r = env.post("/api/scrcpy/view", json={"serial": "R58M123ABC"})
    assert r.status_code == 424 and r.json()["detail"]["missing"] == ["scrcpy"]
    env.have.add("scrcpy")
    monkeypatch.delenv("DISPLAY", raising=False)
    monkeypatch.delenv("WAYLAND_DISPLAY", raising=False)
    r = env.post("/api/scrcpy/view", json={"serial": "R58M123ABC"})
    assert r.status_code == 424 and r.json()["detail"]["missing"] == ["display"]
    assert env.popens == []


def test_view_reports_immediate_exit(env):
    env.proc.exits_fast, env.proc.rc = True, 1
    r = env.post("/api/scrcpy/view", json={"serial": "R58M123ABC"})
    assert r.status_code == 502
    assert "exited immediately" in r.json()["detail"]["message"]


def test_no_shell_true_in_module():
    src = (server.BASE_DIR / "scrcpy_support.py").read_text()
    assert "shell=True" not in src


def test_spec_bundles_module():
    spec = (server.BASE_DIR / "bakerpi_installer.spec").read_text()
    assert '("scrcpy_support.py", ".")' in spec and '"scrcpy_support",' in spec


def test_ui_and_manual_have_scrcpy():
    html = (server.STATIC_DIR / "index.html").read_text()
    assert 'id="scrcpy-panel"' in html and "/api/scrcpy/view" in html
    assert "https://github.com/Genymobile/scrcpy" in html
    manual = server.MANUAL_PATH.read_text()
    assert "scrcpy by Genymobile, Apache-2.0" in manual
