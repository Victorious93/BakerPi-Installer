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
