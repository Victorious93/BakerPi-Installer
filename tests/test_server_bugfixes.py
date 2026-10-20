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
