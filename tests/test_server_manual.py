"""Tests for the read-only in-app manual route (/api/manual)."""
import pytest

pytest.importorskip("fastapi")
pytest.importorskip("paramiko")
pytest.importorskip("httpx")

from fastapi.testclient import TestClient  # noqa: E402

import server  # noqa: E402


def test_manual_served_as_markdown():
    r = TestClient(server.app).get("/api/manual")
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/markdown")
    assert r.text.startswith("# BakerPi Tool Installer")
    assert r.text == server.MANUAL_PATH.read_text(encoding="utf-8")


def test_manual_is_read_only():
    client = TestClient(server.app)
    for method in ("post", "put", "delete"):
        assert getattr(client, method)("/api/manual").status_code == 405


def test_manual_missing_returns_404(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "MANUAL_PATH", tmp_path / "nope.md")
    assert TestClient(server.app).get("/api/manual").status_code == 404


def test_spec_bundles_manual():
    spec = (server.BASE_DIR / "bakerpi_installer.spec").read_text()
    assert '("docs/MANUAL.md",  "docs")' in spec


def test_index_has_help_view():
    html = (server.STATIC_DIR / "index.html").read_text()
    assert 'id="help-btn"' in html and "/api/manual" in html
