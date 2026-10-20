"""Regression tests for bugs fixed in the bug-test pass."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("paramiko")
pytest.importorskip("httpx")

import server  # noqa: E402
from test_server_targeting import api, add  # noqa: E402,F401


def test_ssh_status_unknown_device_is_404(api):
    r = api.get("/api/ssh/status", params={"device_id": "nope"})
    assert r.status_code == 404


@pytest.mark.parametrize("geom", ["1280x800; touch /tmp/pwned", "$(id)", "1280x800\n", "1x1", "abc", ""])
def test_vnc_start_rejects_bad_geometry(api, geom):
    r = api.post("/api/services/vnc/start", json={"geometry": geom})
    assert r.status_code == 400
    assert api.calls == []


def test_vnc_start_accepts_valid_geometry(api):
    r = api.post("/api/services/vnc/start", json={"geometry": "1920x1080"})
    assert r.status_code == 200
    assert any("-geometry 1920x1080 " in c for _, c in api.calls)


def test_failed_connect_keeps_previous_creds(monkeypatch):
    monkeypatch.setattr(server, "_ssh_creds", {"d1": {"password": "good", "key_file": None}})
    monkeypatch.setattr(server, "ssh_clients", {})

    class FailingClient:
        def set_missing_host_key_policy(self, p): pass
        def connect(self, **kw): raise server.paramiko.AuthenticationException("bad")

    monkeypatch.setattr(server.paramiko, "SSHClient", FailingClient)
    with pytest.raises(server.paramiko.AuthenticationException):
        server.connect_ssh("192.0.2.1", "pi", 22, "wrong", None, "d1")
    assert server._ssh_creds["d1"] == {"password": "good", "key_file": None}


def test_successful_connect_saves_creds(monkeypatch):
    monkeypatch.setattr(server, "_ssh_creds", {})
    monkeypatch.setattr(server, "ssh_clients", {})

    class OkClient:
        def set_missing_host_key_policy(self, p): pass
        def connect(self, **kw): pass
        def close(self): pass

    monkeypatch.setattr(server.paramiko, "SSHClient", OkClient)
    server.connect_ssh("192.0.2.1", "pi", 22, "pw", None, "d1")
    assert server._ssh_creds["d1"] == {"password": "pw", "key_file": None}


def test_device_edit_clears_saved_creds(api):
    d = add(api, label="pi2", type="ssh", host="192.0.2.20", user="pi", key_file="/old/key")
    server._ssh_creds[d["id"]] = {"password": None, "key_file": "/old/key"}
    r = api.put(f"/api/devices/{d['id']}", json={"key_file": "/new/key"})
    assert r.status_code == 200, r.text
    assert d["id"] not in server._ssh_creds


def test_device_label_edit_keeps_saved_creds(api):
    d = add(api, label="pi2", type="ssh", host="192.0.2.20", user="pi")
    server._ssh_creds[d["id"]] = {"password": "pw", "key_file": None}
    r = api.put(f"/api/devices/{d['id']}", json={"label": "renamed"})
    assert r.status_code == 200, r.text
    assert server._ssh_creds[d["id"]] == {"password": "pw", "key_file": None}


def test_vnc_stop_defaults_to_display_1(api):
    r = api.post("/api/services/vnc/stop")
    assert r.status_code == 200 and r.json()["display"] == ":1"
    assert any("vncserver -kill :1 " in c for _, c in api.calls)


def test_vnc_stop_other_display(api):
    r = api.post("/api/services/vnc/stop", params={"display": 2})
    assert r.status_code == 200 and r.json()["display"] == ":2"
    cmds = " ".join(c for _, c in api.calls)
    assert "vncserver -kill :2 " in cmds and ":1" not in cmds


def test_vnc_status_other_display(api):
    r = api.get("/api/services/vnc/status", params={"display": 3})
    assert r.status_code == 200
    j = r.json()
    assert j["display"] == ":3" and j["port"] == 5903
    assert any(":3( |$)" in c for _, c in api.calls)


def test_vnc_status_default_display(api):
    j = api.get("/api/services/vnc/status").json()
    assert j["display"] == ":1" and j["port"] == 5901


@pytest.mark.parametrize("bad", ["x", "-1", "1;id"])
def test_vnc_display_param_validated(api, bad):
    assert api.post("/api/services/vnc/stop", params={"display": bad}).status_code == 422
    assert api.calls == []
