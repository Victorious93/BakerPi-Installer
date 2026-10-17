"""API-level tests for device targeting. Commands are faked: no SSH, no Pi."""
import json
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("paramiko")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from device_registry import DeviceRegistry, build_default_device  # noqa: E402


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "config", {"mode": "ssh", "host": "192.0.2.10",
                                           "user": "pi", "port": 22})
    monkeypatch.setattr(server, "registry", DeviceRegistry(
        tmp_path / "devices.json",
        default_factory=lambda: build_default_device(server.config)))
    monkeypatch.setattr(server, "jobs", {})
    monkeypatch.setattr(server, "ssh_clients", {})
    monkeypatch.setattr(server, "_ssh_creds", {})

    calls = []  # (device_id, cmd)

    def fake_stream(cmd, device=None):
        calls.append((device.id, cmd))
        yield f"ran on {device.label}\n"
        yield f"\n[EXIT {1 if device.host == '192.0.2.99' else 0}]\n"

    def fake_run(cmd, device=None):
        calls.append((device.id, cmd))
        return 0, f"out-{device.host}"

    monkeypatch.setattr(server, "stream_cmd", fake_stream)
    monkeypatch.setattr(server, "run_cmd", fake_run)
    monkeypatch.setattr(server, "ensure_connected", lambda device: None)
    monkeypatch.setattr(server, "check_tool_installed_fast", lambda tool, device=None: True)
    with TestClient(server.app) as client:
        client.calls = calls
        yield client


def wait_done(client, job_id, timeout=5):
    end = time.time() + timeout
    while time.time() < end:
        j = client.get(f"/api/jobs/{job_id}").json()
        if j["status"] == "done":
            return j
        time.sleep(0.02)
    raise AssertionError("job did not finish")


def add(client, **kw):
    r = client.post("/api/devices", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def test_default_only_with_no_config(api):
    d = api.get("/api/devices").json()
    assert [x["id"] for x in d["devices"]] == ["default"]
    assert d["selected"] == ["default"] and d["primary"] == "default"
    assert d["devices"][0]["builtin"] is True


def test_crud_and_selection_endpoints(api):
    a = add(api, label="A", type="ssh", host="192.0.2.20")
    assert api.put(f"/api/devices/{a['id']}", json={"label": "A2"}).json()["label"] == "A2"
    assert api.put("/api/devices/default", json={"label": "x"}).status_code == 400
    assert api.post("/api/devices", json={"type": "ssh"}).status_code == 400
    assert api.put("/api/devices/ghost", json={"label": "x"}).status_code == 404

    r = api.put("/api/devices/selected", json={"device_ids": [a["id"], "default"]})
    assert r.json()["selected"] == [a["id"], "default"]
    assert api.get("/api/devices/selected").json()["primary"] == a["id"]
    assert api.put("/api/devices/selected", json={"device_ids": ["ghost"]}).status_code == 404
    assert api.put("/api/devices/selected", json={"device_ids": []}).status_code == 400

    assert api.delete("/api/devices/default").status_code == 400
    r = api.delete(f"/api/devices/{a['id']}")
    assert r.json()["selected"] == ["default"]
    assert api.delete(f"/api/devices/{a['id']}").status_code == 404


def test_install_without_target_uses_default_device(api):
    r = api.post("/api/install", json={"tool_ids": ["nmap"]})
    assert r.status_code == 200
    body = r.json()
    assert [d["id"] for d in body["devices"]] == ["default"]
    job = wait_done(api, body["job_id"])
    assert job["devices"][0]["status"] == "done"
    assert "Installing:" in job["output"] and "ran on" in job["output"]
    assert {c[0] for c in api.calls} == {"default"}


def test_install_targets_specific_device(api):
    a = add(api, label="A", type="ssh", host="192.0.2.20")
    job_id = api.post("/api/install", json={"tool_ids": ["nmap"], "device_id": a["id"]}).json()["job_id"]
    wait_done(api, job_id)
    assert {c[0] for c in api.calls} == {a["id"]}


def test_install_unknown_device_is_404(api):
    r = api.post("/api/install", json={"tool_ids": ["nmap"], "device_id": "ghost"})
    assert r.status_code == 404
    assert api.calls == []


def test_multi_device_job_runs_per_device_and_isolates_failures(api):
    a = add(api, label="A", type="ssh", host="192.0.2.20")
    bad = add(api, label="Bad", type="ssh", host="192.0.2.99")  # fake returns EXIT 1
    r = api.post("/api/update", json={"tool_ids": ["nmap"],
                                      "device_ids": ["default", a["id"], bad["id"]]}).json()
    job = wait_done(api, r["job_id"])
    status = {d["id"]: d["status"] for d in job["devices"]}
    assert status == {"default": "done", a["id"]: "done", bad["id"]: "failed"}
    assert {c[0] for c in api.calls} == {"default", a["id"], bad["id"]}
    for d in job["devices"]:  # logs are kept per device
        assert f"ran on {d['label']}" in d["output"]


def test_sse_stream_tags_events_with_device(api):
    a = add(api, label="A", type="ssh", host="192.0.2.20")
    job_id = api.post("/api/install", json={"tool_ids": ["nmap"],
                                            "device_ids": ["default", a["id"]]}).json()["job_id"]
    wait_done(api, job_id)
    with api.stream("GET", f"/api/jobs/{job_id}/stream") as resp:
        events = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]
    assert events[-1]["done"] is True
    assert events[-1]["devices"] == {"default": "done", a["id"]: "done"}
    lines = [e for e in events if "line" in e]
    assert {e["device"] for e in lines} == {"default", a["id"]}
    assert all(e["device"] in ("default", a["id"]) for e in lines)


def test_connection_failure_marks_only_that_device_failed(api, monkeypatch):
    a = add(api, label="Down", type="ssh", host="192.0.2.20")

    def flaky(device):
        if device.id == a["id"]:
            raise RuntimeError("no route")
    monkeypatch.setattr(server, "ensure_connected", flaky)
    r = api.post("/api/install", json={"tool_ids": ["nmap"],
                                       "device_ids": ["default", a["id"]]}).json()
    job = wait_done(api, r["job_id"])
    status = {d["id"]: d["status"] for d in job["devices"]}
    assert status == {"default": "done", a["id"]: "failed"}
    assert "no route" in next(d for d in job["devices"] if d["id"] == a["id"])["output"]


def test_uninstall_rejects_builtin_before_starting(api):
    tool = next(t for t in server.flat_tools(server.load_catalog()).values() if t.get("builtin"))
    r = api.post("/api/uninstall", json={"tool_ids": [tool["id"]]})
    assert r.status_code == 400 and api.calls == []


def test_update_all_per_device_and_skips_empty(api, monkeypatch):
    a = add(api, label="A", type="ssh", host="192.0.2.20")
    monkeypatch.setattr(server, "check_tool_installed_fast",
                        lambda tool, device=None: device.id == a["id"])
    r = api.post("/api/update-all", json={"device_ids": ["default", a["id"]]}).json()
    assert [d["id"] for d in r["devices"]] == [a["id"]]
    assert [d["id"] for d in r["skipped_devices"]] == ["default"]
    wait_done(api, r["job_id"])
    # legacy call (no body) targets the current selection and 400s if nothing installed
    assert api.post("/api/update-all").status_code == 400


def test_system_info_is_per_device_and_labelled(api):
    a = add(api, label="A", type="ssh", host="192.0.2.20")
    d = api.get("/api/system").json()
    assert d["device_id"] == "default" and d["hostname"] == "out-192.0.2.10"
    assert d["mode"] == "ssh"
    d = api.get("/api/system", params={"device_id": a["id"]}).json()
    assert d["device_id"] == a["id"] and d["device_label"] == "A"
    assert d["hostname"] == "out-192.0.2.20"
    # no explicit id follows the primary selected device
    api.put("/api/devices/selected", json={"device_ids": [a["id"]]})
    assert api.get("/api/system").json()["device_id"] == a["id"]
    assert api.get("/api/system", params={"device_id": "ghost"}).status_code == 404


def test_tools_status_follow_target(api):
    a = add(api, label="A", type="ssh", host="192.0.2.20")
    tools = api.get("/api/tools", params={"device_id": a["id"]}).json()
    assert tools and all(t["installed"] for t in tools)
    assert api.get("/api/tools", params={"device_id": "ghost"}).status_code == 404


def test_legacy_ssh_connect_repoints_default_device(api, monkeypatch):
    seen = {}
    monkeypatch.setattr(server, "connect_ssh",
                        lambda host, user, port, pw, key, device_id="default":
                        seen.update(host=host, user=user, port=port, device_id=device_id))
    r = api.post("/api/ssh/connect", json={"host": "192.0.2.77", "user": "me", "port": 2022})
    assert r.json() == {"connected": True, "host": "192.0.2.77"}
    assert seen == {"host": "192.0.2.77", "user": "me", "port": 2022, "device_id": "default"}
    assert server.registry.get("default").host == "192.0.2.77"


def test_device_connect_endpoint_uses_registry_settings(api, monkeypatch):
    a = add(api, label="A", type="ssh", host="192.0.2.20", user="pi", port=2200)
    seen = {}
    monkeypatch.setattr(server, "connect_ssh",
                        lambda host, user, port, pw, key, device_id="default":
                        seen.update(host=host, user=user, port=port, pw=pw, id=device_id))
    r = api.post(f"/api/devices/{a['id']}/connect", json={"password": "pw"})
    assert r.status_code == 200
    assert seen == {"host": "192.0.2.20", "user": "pi", "port": 2200, "pw": "pw", "id": a["id"]}
    assert "pw" not in (server.registry.path.read_text())
