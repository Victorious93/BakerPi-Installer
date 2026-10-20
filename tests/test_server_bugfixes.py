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
