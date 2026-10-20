"""ESP32 dev toolchain installer. subprocess / shutil.which are mocked: no real
installs run. Proves validation, command construction and prereq handling only;
untested on hardware."""
import os

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("paramiko")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import esp32_toolchain as tc  # noqa: E402
import server  # noqa: E402


@pytest.fixture
def env(monkeypatch, tmp_path):
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.setenv("BAKERPI_ESP_DIR", str(tmp_path / "esp"))
    monkeypatch.setattr(tc.platform, "system", lambda: "Linux")
    monkeypatch.setattr(tc.shutil, "which", lambda n: f"/usr/bin/{n}")
    calls = []

    class FakeProc:
        rc = 0

        def __init__(self, cmd, **kw):
            calls.append((cmd, kw))
            self.stdout = iter([f"ran {cmd[0]}\n"])
            self.returncode = FakeProc.rc

        def wait(self):
            return self.returncode

    monkeypatch.setattr(tc.subprocess, "Popen", FakeProc)
    monkeypatch.setattr(tc.subprocess, "run", lambda *a, **k: (_ for _ in ()).throw(OSError()))
    with TestClient(server.app) as client:
        client.calls, client.tmp, client.proc = calls, tmp_path, FakeProc
        yield client


def test_status_not_installed(env):
    st = env.get("/api/esp32/toolchain/status").json()
    assert st["hardware_tested"] is False
    assert st["esp-idf"]["installed"] is False
    assert st["arduino-cli"]["installed"] is True  # which() mocked to find it
    assert st["esp-idf"]["missing_prereqs"] == []


def test_status_detects_idf_and_arduino(env, monkeypatch):
    p = env.tmp / "esp" / "esp-idf" / "tools"
    p.mkdir(parents=True)
    (p / "idf.py").write_text("")
    monkeypatch.setattr(tc.shutil, "which", lambda n: None)
    b = env.tmp / ".local" / "bin"
    b.mkdir(parents=True)
    (b / "arduino-cli").write_text("")

    class R:
        returncode, stdout = 0, "ID  Installed\nesp32:esp32 3.0.0\n"
    monkeypatch.setattr(tc.subprocess, "run", lambda cmd, **k: R())
    st = env.get("/api/esp32/toolchain/status").json()
    assert st["esp-idf"]["installed"] is True
    assert st["arduino-cli"]["path"] == str(b / "arduino-cli")
    assert st["arduino-cli"]["esp32_core_installed"] is True
    assert set(st["esp-idf"]["missing_prereqs"]) == {"git", "python3", "bash"}


def test_idf_install_commands(env):
    r = env.post("/api/esp32/toolchain/install",
                 json={"item": "esp-idf", "version": "v5.2", "targets": ["esp32", "esp32s3"]})
    assert r.status_code == 200 and "[EXIT 0]" in r.text
    dest = str(env.tmp / "esp" / "esp-idf")
    cmds = [c for c, _ in env.calls]
    assert cmds == [
        ["git", "clone", "--depth", "1", "--branch", "v5.2", "--recursive",
         "--shallow-submodules", tc.IDF_REPO, dest],
        ["bash", os.path.join(dest, "install.sh"), "esp32,esp32s3"]]
    assert all(kw["shell"] is False for _, kw in env.calls)


def test_idf_skips_clone_when_present(env):
    d = env.tmp / "esp" / "esp-idf"
    d.mkdir(parents=True)
    (d / "install.sh").write_text("")
    assert tc.build_idf_steps("v5.3.1", ["all", "esp32"]) == [["bash", str(d / "install.sh"), "all"]]


def test_arduino_install_commands_and_cleanup(env):
    r = env.post("/api/esp32/toolchain/install", json={"item": "arduino-cli"})
    assert r.status_code == 200 and "[EXIT 0]" in r.text
    cmds = [c for c, _ in env.calls]
    script = cmds[0][3]
    assert cmds[0] == ["curl", "-fsSL", "-o", script, tc.ARDUINO_INSTALL_URL]
    assert cmds[1] == ["sh", script]
    cli = str(env.tmp / ".local" / "bin" / "arduino-cli")
    assert cmds[3] == [cli, "core", "install", "esp32:esp32", "--additional-urls", tc.ESP32_CORE_INDEX]
    assert env.calls[1][1]["env"]["BINDIR"] == str(env.tmp / ".local" / "bin")
    assert not os.path.exists(script)


def test_arduino_without_core(env):
    env.post("/api/esp32/toolchain/install", json={"item": "arduino-cli", "with_esp32_core": False})
    assert len(env.calls) == 2


def test_failure_stops_steps(env):
    env.proc.rc = 1
    r = env.post("/api/esp32/toolchain/install", json={"item": "arduino-cli"})
    assert "[EXIT 1]" in r.text and len(env.calls) == 1
    assert not tc._install_lock.locked()


@pytest.mark.parametrize("body", [
    {"item": "rm -rf /"},
    {"item": "esp-idf", "version": "v5.3; rm -rf ~"},
    {"item": "esp-idf", "version": "master"},
    {"item": "esp-idf", "targets": ["esp32;id"]},
    {"item": "esp-idf", "targets": []},
])
def test_validation_rejects(env, body):
    r = env.post("/api/esp32/toolchain/install", json=body)
    assert r.status_code in (400, 422)
    assert env.calls == []


def test_prereq_missing(env, monkeypatch):
    monkeypatch.setattr(tc.shutil, "which", lambda n: None if n == "git" else f"/usr/bin/{n}")
    r = env.post("/api/esp32/toolchain/install", json={"item": "esp-idf"})
    assert r.status_code == 424
    assert r.json()["detail"]["missing"] == ["git"]
    assert env.calls == []


def test_windows_unsupported(env, monkeypatch):
    monkeypatch.setattr(tc.platform, "system", lambda: "Windows")
    assert env.post("/api/esp32/toolchain/install", json={"item": "arduino-cli"}).status_code == 400


def test_concurrent_install_rejected(env):
    assert tc.acquire()
    try:
        r = env.post("/api/esp32/toolchain/install", json={"item": "arduino-cli"})
        assert r.status_code == 409
    finally:
        tc._install_lock.release()


def test_binary_not_found(env, monkeypatch):
    def boom(*a, **k):
        raise FileNotFoundError
    monkeypatch.setattr(tc.subprocess, "Popen", boom)
    r = env.post("/api/esp32/toolchain/install", json={"item": "arduino-cli"})
    assert "[EXIT 127]" in r.text
