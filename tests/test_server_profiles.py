"""API-level tests for fleet install profiles. Commands are faked: no SSH, no Pi."""
import json
import stat
import sys
import time

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("paramiko")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402
from device_registry import DeviceRegistry, build_default_device  # noqa: E402
from profile_registry import ProfileRegistry  # noqa: E402


@pytest.fixture
def api(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "config", {"mode": "ssh", "host": "192.0.2.10",
                                           "user": "pi", "port": 22})
    monkeypatch.setattr(server, "registry", DeviceRegistry(
        tmp_path / "devices.json",
        default_factory=lambda: build_default_device(server.config)))
    monkeypatch.setattr(server, "profiles", ProfileRegistry(
        tmp_path / "profiles.json", known_tools=lambda: server.catalog_tool_ids()))
    monkeypatch.setattr(server, "jobs", {})
    monkeypatch.setattr(server, "ssh_clients", {})
    monkeypatch.setattr(server, "_ssh_creds", {})

    calls = []  # (device_id, cmd)

    def fake_stream(cmd, device=None):
        calls.append((device.id, cmd))
        yield f"ran on {device.label}\n"
        yield f"\n[EXIT {1 if device.host == '192.0.2.99' else 0}]\n"

    monkeypatch.setattr(server, "stream_cmd", fake_stream)
    monkeypatch.setattr(server, "run_cmd", lambda cmd, device=None: (0, ""))
    monkeypatch.setattr(server, "ensure_connected", lambda device: None)
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


def add_device(client, **kw):
    r = client.post("/api/devices", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def add_profile(client, **kw):
    r = client.post("/api/profiles", json=kw)
    assert r.status_code == 201, r.text
    return r.json()


def real_tool_ids(n=3):
    """Real, non-builtin ids from tools/catalog.json (so catalog validation is genuine)."""
    tools = server.flat_tools(server.load_catalog())
    ids = [tid for tid, t in tools.items() if not t.get("builtin")][:n]
    assert len(ids) == n
    return ids


# ── CRUD endpoints ───────────────────────────────────────────────────────────

def test_starts_empty(api):
    assert api.get("/api/profiles").json() == {"profiles": []}


def test_crud_roundtrip(api):
    t1, t2, t3 = real_tool_ids()
    p = add_profile(api, name="Recon kit", description="d", tool_ids=[t1, t2])
    assert p["tool_ids"] == [t1, t2] and p["unknown_tool_ids"] == []
    assert api.get("/api/profiles").json()["profiles"] == [p]
    assert api.get(f"/api/profiles/{p['id']}").json() == p

    u = api.put(f"/api/profiles/{p['id']}", json={"name": "Recon+", "tool_ids": [t3, t1]}).json()
    assert (u["name"], u["tool_ids"], u["description"]) == ("Recon+", [t3, t1], "d")
    assert api.put(f"/api/profiles/{p['id']}", json={"description": None}).json()["description"] == ""

    r = api.delete(f"/api/profiles/{p['id']}")
    assert r.status_code == 200 and r.json() == {"removed": p["id"]}
    assert api.get("/api/profiles").json() == {"profiles": []}


def test_unknown_profile_is_404(api):
    assert api.get("/api/profiles/ghost").status_code == 404
    assert api.put("/api/profiles/ghost", json={"name": "x"}).status_code == 404
    assert api.delete("/api/profiles/ghost").status_code == 404
    assert api.post("/api/profiles/ghost/apply", json={}).status_code == 404
    assert api.calls == []


def test_create_validation_errors_are_400(api):
    t1 = real_tool_ids(1)[0]
    assert api.post("/api/profiles", json={"tool_ids": [t1]}).status_code == 400          # no name
    assert api.post("/api/profiles", json={"name": "A"}).status_code == 400               # no tools
    assert api.post("/api/profiles", json={"name": "A", "tool_ids": []}).status_code == 400
    assert api.get("/api/profiles").json() == {"profiles": []}


def test_create_rejects_unknown_tool_ids(api):
    t1 = real_tool_ids(1)[0]
    r = api.post("/api/profiles", json={"name": "A", "tool_ids": [t1, "definitely_not_a_tool"]})
    assert r.status_code == 400 and "definitely_not_a_tool" in r.json()["detail"]
    assert api.get("/api/profiles").json() == {"profiles": []}


def test_update_rejects_unknown_tool_ids_and_keeps_old(api):
    t1 = real_tool_ids(1)[0]
    p = add_profile(api, name="A", tool_ids=[t1])
    r = api.put(f"/api/profiles/{p['id']}", json={"tool_ids": ["definitely_not_a_tool"]})
    assert r.status_code == 400
    assert api.get(f"/api/profiles/{p['id']}").json()["tool_ids"] == [t1]


def test_duplicate_name_is_400(api):
    t1 = real_tool_ids(1)[0]
    add_profile(api, name="Recon", tool_ids=[t1])
    assert api.post("/api/profiles", json={"name": "RECON", "tool_ids": [t1]}).status_code == 400


# ── persistence / permissions through the API ────────────────────────────────

def test_profiles_persist_and_file_is_private_and_secret_free(api, tmp_path):
    t1, t2, _ = real_tool_ids()
    p = add_profile(api, name="Kit", tool_ids=[t1, t2])
    path = tmp_path / "profiles.json"
    data = json.loads(path.read_text())
    assert [x["id"] for x in data["profiles"]] == [p["id"]]
    if not sys.platform.startswith("win"):
        assert stat.S_IMODE(path.stat().st_mode) == 0o600
    # a second registry on the same file sees the same data
    again = ProfileRegistry(path, known_tools=lambda: server.catalog_tool_ids())
    assert [x.id for x in again.list()] == [p["id"]]


# ── apply: targeting ─────────────────────────────────────────────────────────

def test_apply_without_target_uses_default_device(api):
    t1, t2, _ = real_tool_ids()
    p = add_profile(api, name="Kit", tool_ids=[t1, t2])
    r = api.post(f"/api/profiles/{p['id']}/apply")  # no body at all
    assert r.status_code == 200
    body = r.json()
    assert [d["id"] for d in body["devices"]] == ["default"]
    assert body["profile"] == {"id": p["id"], "name": "Kit"}
    assert body["tool_ids"] == [t1, t2]
    job = wait_done(api, body["job_id"])
    assert job["action"] == "install" and job["profile"] == body["profile"]
    assert job["devices"][0]["status"] == "done"
    assert job["devices"][0]["tool_ids"] == [t1, t2]
    assert {c[0] for c in api.calls} == {"default"}
    assert len(api.calls) == 2  # one install command per tool, in order


def test_apply_runs_each_tool_in_profile_order(api):
    t1, t2, t3 = real_tool_ids()
    p = add_profile(api, name="Kit", tool_ids=[t3, t1, t2])
    job = wait_done(api, api.post(f"/api/profiles/{p['id']}/apply", json={}).json()["job_id"])
    out = job["output"]
    names = server.flat_tools(server.load_catalog())
    positions = [out.index(f"Installing: {names[t]['name']}") for t in (t3, t1, t2)]
    assert positions == sorted(positions)


def test_apply_empty_body_uses_current_selection(api):
    t1 = real_tool_ids(1)[0]
    a = add_device(api, label="A", type="ssh", host="192.0.2.20")
    api.put("/api/devices/selected", json={"device_ids": [a["id"]]})
    p = add_profile(api, name="Kit", tool_ids=[t1])
    body = api.post(f"/api/profiles/{p['id']}/apply", json={}).json()
    assert [d["id"] for d in body["devices"]] == [a["id"]]
    wait_done(api, body["job_id"])
    assert {c[0] for c in api.calls} == {a["id"]}


def test_apply_single_device_id(api):
    t1 = real_tool_ids(1)[0]
    a = add_device(api, label="A", type="ssh", host="192.0.2.20")
    p = add_profile(api, name="Kit", tool_ids=[t1])
    body = api.post(f"/api/profiles/{p['id']}/apply", json={"device_id": a["id"]}).json()
    wait_done(api, body["job_id"])
    assert {c[0] for c in api.calls} == {a["id"]}


def test_apply_device_ids_beat_device_id(api):
    t1 = real_tool_ids(1)[0]
    a = add_device(api, label="A", type="ssh", host="192.0.2.20")
    b = add_device(api, label="B", type="ssh", host="192.0.2.21")
    p = add_profile(api, name="Kit", tool_ids=[t1])
    body = api.post(f"/api/profiles/{p['id']}/apply",
                    json={"device_id": a["id"], "device_ids": [b["id"], "default"]}).json()
    assert [d["id"] for d in body["devices"]] == [b["id"], "default"]
    wait_done(api, body["job_id"])
    assert {c[0] for c in api.calls} == {b["id"], "default"}


def test_apply_unknown_device_is_404_and_runs_nothing(api):
    t1 = real_tool_ids(1)[0]
    p = add_profile(api, name="Kit", tool_ids=[t1])
    r = api.post(f"/api/profiles/{p['id']}/apply", json={"device_ids": ["default", "ghost"]})
    assert r.status_code == 404
    assert api.calls == [] and server.jobs == {}


def test_apply_to_many_devices_runs_in_parallel_per_device_and_isolates_failures(api):
    t1, t2, _ = real_tool_ids()
    a = add_device(api, label="A", type="ssh", host="192.0.2.20")
    bad = add_device(api, label="Bad", type="ssh", host="192.0.2.99")  # fake returns EXIT 1
    p = add_profile(api, name="Kit", tool_ids=[t1, t2])
    r = api.post(f"/api/profiles/{p['id']}/apply",
                 json={"device_ids": ["default", a["id"], bad["id"]]}).json()
    job = wait_done(api, r["job_id"])
    status = {d["id"]: d["status"] for d in job["devices"]}
    assert status == {"default": "done", a["id"]: "done", bad["id"]: "failed"}
    # every device got every tool of the profile, and the failing device did not
    # stop the others (nor its own remaining tools)
    for dev_id in ("default", a["id"], bad["id"]):
        assert sum(1 for c in api.calls if c[0] == dev_id) == 2
    for d in job["devices"]:
        assert d["tool_ids"] == [t1, t2]
        assert f"ran on {d['label']}" in d["output"]  # per-device log


def test_apply_connection_failure_marks_only_that_device_failed(api, monkeypatch):
    t1 = real_tool_ids(1)[0]
    a = add_device(api, label="Down", type="ssh", host="192.0.2.20")

    def flaky(device):
        if device.id == a["id"]:
            raise RuntimeError("no route")
    monkeypatch.setattr(server, "ensure_connected", flaky)
    p = add_profile(api, name="Kit", tool_ids=[t1])
    r = api.post(f"/api/profiles/{p['id']}/apply", json={"device_ids": ["default", a["id"]]}).json()
    job = wait_done(api, r["job_id"])
    assert {d["id"]: d["status"] for d in job["devices"]} == {"default": "done", a["id"]: "failed"}
    assert "no route" in next(d for d in job["devices"] if d["id"] == a["id"])["output"]
    assert {c[0] for c in api.calls} == {"default"}


def test_apply_sse_stream_tags_events_with_device(api):
    t1 = real_tool_ids(1)[0]
    a = add_device(api, label="A", type="ssh", host="192.0.2.20")
    p = add_profile(api, name="Kit", tool_ids=[t1])
    job_id = api.post(f"/api/profiles/{p['id']}/apply",
                      json={"device_ids": ["default", a["id"]]}).json()["job_id"]
    wait_done(api, job_id)
    with api.stream("GET", f"/api/jobs/{job_id}/stream") as resp:
        events = [json.loads(l[6:]) for l in resp.iter_lines() if l.startswith("data: ")]
    assert events[-1]["done"] is True
    assert events[-1]["devices"] == {"default": "done", a["id"]: "done"}
    assert {e["device"] for e in events if "line" in e} == {"default", a["id"]}


# ── apply: guard rails ───────────────────────────────────────────────────────

def test_apply_refuses_profile_with_tools_missing_from_catalog(api, monkeypatch):
    t1, t2, _ = real_tool_ids()
    p = add_profile(api, name="Kit", tool_ids=[t1, t2])
    real = server.catalog_tool_ids()
    monkeypatch.setattr(server, "catalog_tool_ids", lambda: real - {t2})  # t2 dropped later
    listed = api.get("/api/profiles").json()["profiles"][0]
    assert listed["unknown_tool_ids"] == [t2]
    r = api.post(f"/api/profiles/{p['id']}/apply", json={})
    assert r.status_code == 400 and t2 in r.json()["detail"]
    assert api.calls == [] and server.jobs == {}


def test_apply_does_not_touch_other_job_actions(api):
    """Install-only: profile apply must never uninstall/update."""
    t1 = real_tool_ids(1)[0]
    p = add_profile(api, name="Kit", tool_ids=[t1])
    job = wait_done(api, api.post(f"/api/profiles/{p['id']}/apply", json={}).json()["job_id"])
    assert job["action"] == "install"
    assert all("apt-get remove" not in c[1] and "pip3 uninstall" not in c[1] for c in api.calls)


def test_existing_install_endpoint_job_has_no_profile(api):
    t1 = real_tool_ids(1)[0]
    job = wait_done(api, api.post("/api/install", json={"tool_ids": [t1]}).json()["job_id"])
    assert job["profile"] is None
