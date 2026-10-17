"""Unit tests for the device registry. No hardware or network required.

Hosts use RFC 5737 documentation addresses (192.0.2.0/24) — not real devices.
"""
import json
import stat
import sys

import pytest

from device_registry import (
    DEFAULT_DEVICE_ID, Device, DeviceError, DeviceNotFound, DeviceRegistry,
    build_default_device, default_devices_path,
)

ssh_cfg = {"mode": "ssh", "host": "192.0.2.10", "user": "pi", "port": 2222}


def make(tmp_path, config=None):
    cfg = {"mode": "local"} if config is None else config
    return DeviceRegistry(tmp_path / "devices.json",
                          default_factory=lambda: build_default_device(cfg))


# ── default / fallback ───────────────────────────────────────────────────────

def test_no_config_file_falls_back_to_cli_target(tmp_path):
    reg = make(tmp_path, ssh_cfg)
    devs = reg.list()
    assert [d.id for d in devs] == [DEFAULT_DEVICE_ID]
    d = devs[0]
    assert (d.type, d.host, d.user, d.port, d.builtin) == ("ssh", "192.0.2.10", "pi", 2222, True)
    assert reg.get_selected_ids() == [DEFAULT_DEVICE_ID]
    assert reg.primary().id == DEFAULT_DEVICE_ID
    assert not (tmp_path / "devices.json").exists()  # nothing written until a change


def test_local_mode_default_is_local_device(tmp_path):
    d = make(tmp_path).default_device()
    assert d.is_local and d.type == "local"


def test_default_tracks_live_config_changes(tmp_path):
    cfg = dict(ssh_cfg)
    reg = make(tmp_path, cfg)
    cfg["host"] = "192.0.2.99"
    assert reg.get(DEFAULT_DEVICE_ID).host == "192.0.2.99"


def test_default_cannot_be_edited_or_removed(tmp_path):
    reg = make(tmp_path, ssh_cfg)
    with pytest.raises(DeviceError):
        reg.update(DEFAULT_DEVICE_ID, label="x")
    with pytest.raises(DeviceError):
        reg.remove(DEFAULT_DEVICE_ID)


# ── add / update / remove ────────────────────────────────────────────────────

def test_add_assigns_id_and_normalises(tmp_path):
    reg = make(tmp_path, ssh_cfg)
    d = reg.add(label="  Bench Pi ", type="ssh", host="192.0.2.20")
    assert d.id and d.id != DEFAULT_DEVICE_ID
    assert (d.label, d.user, d.port, d.builtin) == ("Bench Pi", "root", 22, False)
    assert [x.id for x in reg.list()] == [DEFAULT_DEVICE_ID, d.id]
    assert reg.get(d.id) == d


def test_add_generates_default_label(tmp_path):
    d = make(tmp_path).add(type="ssh", host="192.0.2.21", user="pi")
    assert d.label == "pi@192.0.2.21"


def test_usb_rndis_defaults_host(tmp_path):
    d = make(tmp_path).add(type="usb-rndis")
    assert d.type == "usb-rndis" and d.host == "172.16.0.1"


def test_local_type_ignores_host_and_user(tmp_path):
    d = make(tmp_path).add(type="local", host="evil host", user="x")
    assert d.is_local and d.host == "localhost" and d.user == ""


@pytest.mark.parametrize("fields", [
    {"type": "telnet", "host": "192.0.2.1"},
    {"type": "ssh"},                                   # host required
    {"type": "ssh", "host": "bad host;rm -rf"},
    {"type": "ssh", "host": "192.0.2.1", "port": 0},
    {"type": "ssh", "host": "192.0.2.1", "port": 70000},
    {"type": "ssh", "host": "192.0.2.1", "port": "abc"},
    {"type": "ssh", "host": "192.0.2.1", "label": "x" * 200},
    {"type": "ssh", "host": "192.0.2.1", "label": "a\nb"},
])
def test_add_rejects_invalid(tmp_path, fields):
    reg = make(tmp_path)
    with pytest.raises(DeviceError):
        reg.add(**fields)
    assert len(reg.list()) == 1  # nothing added


def test_update_is_partial(tmp_path):
    reg = make(tmp_path)
    d = reg.add(label="A", type="ssh", host="192.0.2.30", user="pi", port=2200)
    u = reg.update(d.id, label="B")
    assert (u.label, u.host, u.user, u.port) == ("B", "192.0.2.30", "pi", 2200)
    u = reg.update(d.id, port=2201, host="192.0.2.31")
    assert (u.label, u.host, u.port) == ("B", "192.0.2.31", 2201)
    assert reg.get(d.id) == u


def test_update_rejects_invalid_and_keeps_old_value(tmp_path):
    reg = make(tmp_path)
    d = reg.add(type="ssh", host="192.0.2.30")
    with pytest.raises(DeviceError):
        reg.update(d.id, port=99999)
    assert reg.get(d.id).port == 22


def test_update_cannot_change_id(tmp_path):
    reg = make(tmp_path)
    d = reg.add(type="ssh", host="192.0.2.30")
    assert reg.update(d.id, id="hacked").id == d.id


def test_update_type_from_local_does_not_keep_placeholder_host(tmp_path):
    reg = make(tmp_path)
    d = reg.add(type="local")
    with pytest.raises(DeviceError):
        reg.update(d.id, type="ssh")  # no host supplied
    assert reg.update(d.id, type="ssh", host="192.0.2.40").host == "192.0.2.40"


def test_update_and_remove_unknown(tmp_path):
    reg = make(tmp_path)
    with pytest.raises(DeviceNotFound):
        reg.update("nope", label="x")
    with pytest.raises(DeviceNotFound):
        reg.remove("nope")
    with pytest.raises(DeviceNotFound):
        reg.get("nope")


def test_remove(tmp_path):
    reg = make(tmp_path)
    a = reg.add(type="ssh", host="192.0.2.50")
    b = reg.add(type="ssh", host="192.0.2.51")
    reg.remove(a.id)
    assert [d.id for d in reg.list()] == [DEFAULT_DEVICE_ID, b.id]


# ── selection ────────────────────────────────────────────────────────────────

def test_select_single_and_multi_keeps_order(tmp_path):
    reg = make(tmp_path)
    a = reg.add(type="ssh", host="192.0.2.60")
    b = reg.add(type="ssh", host="192.0.2.61")
    assert reg.set_selected([b.id]) == [b.id]
    assert reg.primary().id == b.id
    assert reg.set_selected([b.id, a.id, b.id]) == [b.id, a.id]  # de-duplicated
    assert [d.id for d in reg.get_selected()] == [b.id, a.id]


def test_select_validation(tmp_path):
    reg = make(tmp_path)
    with pytest.raises(DeviceError):
        reg.set_selected([])
    with pytest.raises(DeviceNotFound):
        reg.set_selected(["ghost"])
    assert reg.get_selected_ids() == [DEFAULT_DEVICE_ID]  # unchanged


def test_removing_selected_device_falls_back(tmp_path):
    reg = make(tmp_path)
    a = reg.add(type="ssh", host="192.0.2.62")
    reg.set_selected([a.id])
    reg.remove(a.id)
    assert reg.get_selected_ids() == [DEFAULT_DEVICE_ID]


def test_removing_one_of_many_selected_keeps_the_rest(tmp_path):
    reg = make(tmp_path)
    a = reg.add(type="ssh", host="192.0.2.63")
    b = reg.add(type="ssh", host="192.0.2.64")
    reg.set_selected([a.id, b.id])
    reg.remove(a.id)
    assert reg.get_selected_ids() == [b.id]


def test_resolve_precedence(tmp_path):
    reg = make(tmp_path)
    a = reg.add(type="ssh", host="192.0.2.65")
    b = reg.add(type="ssh", host="192.0.2.66")
    # nothing given -> current selection -> default
    assert [d.id for d in reg.resolve()] == [DEFAULT_DEVICE_ID]
    reg.set_selected([a.id])
    assert [d.id for d in reg.resolve()] == [a.id]
    # explicit single id beats selection; explicit list beats both
    assert [d.id for d in reg.resolve(device_id=b.id)] == [b.id]
    assert [d.id for d in reg.resolve(device_id=b.id, device_ids=[a.id, b.id])] == [a.id, b.id]
    assert [d.id for d in reg.resolve(device_ids=[])] == [a.id]  # empty list = not given
    with pytest.raises(DeviceNotFound):
        reg.resolve(device_id="ghost")


# ── persistence ──────────────────────────────────────────────────────────────

def test_persists_devices_and_selection_across_instances(tmp_path):
    reg = make(tmp_path)
    a = reg.add(label="A", type="ssh", host="192.0.2.70", user="pi", port=2222,
                key_file="/tmp/key")
    b = reg.add(label="B", type="usb-rndis")
    reg.set_selected([b.id, a.id])
    reg.update(a.id, label="A2")

    again = make(tmp_path)
    ids = [d.id for d in again.list()]
    assert ids == [DEFAULT_DEVICE_ID, a.id, b.id]
    assert again.get(a.id).label == "A2"
    assert again.get(a.id).key_file == "/tmp/key"
    assert again.get_selected_ids() == [b.id, a.id]


def test_default_device_is_never_written_to_disk(tmp_path):
    reg = make(tmp_path, ssh_cfg)
    reg.add(type="ssh", host="192.0.2.71")
    data = json.loads((tmp_path / "devices.json").read_text())
    assert [d["host"] for d in data["devices"]] == ["192.0.2.71"]
    assert "builtin" not in data["devices"][0]
    assert "192.0.2.10" not in (tmp_path / "devices.json").read_text()


def test_no_secrets_persisted(tmp_path):
    reg = make(tmp_path)
    reg.add(type="ssh", host="192.0.2.72", password="hunter2")  # unknown field ignored
    assert "hunter2" not in (tmp_path / "devices.json").read_text()


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions")
def test_registry_file_is_private(tmp_path):
    make(tmp_path).add(type="ssh", host="192.0.2.73")
    mode = stat.S_IMODE((tmp_path / "devices.json").stat().st_mode)
    assert mode == 0o600


def test_creates_missing_parent_directory(tmp_path):
    reg = DeviceRegistry(tmp_path / "a" / "b" / "devices.json")
    reg.add(type="ssh", host="192.0.2.74")
    assert (tmp_path / "a" / "b" / "devices.json").exists()


def test_corrupt_file_is_set_aside_not_fatal(tmp_path):
    path = tmp_path / "devices.json"
    path.write_text("{not json")
    reg = make(tmp_path)
    assert [d.id for d in reg.list()] == [DEFAULT_DEVICE_ID]
    assert (tmp_path / "devices.json.bad").read_text() == "{not json"
    reg.add(type="ssh", host="192.0.2.75")  # still usable afterwards
    assert len(make(tmp_path).list()) == 2


def test_stale_selection_in_file_is_ignored(tmp_path):
    (tmp_path / "devices.json").write_text(json.dumps(
        {"version": 1, "devices": [], "selected": ["gone", "also-gone"]}))
    assert make(tmp_path).get_selected_ids() == [DEFAULT_DEVICE_ID]


def test_duplicate_ids_in_file_treated_as_corrupt(tmp_path):
    dev = {"id": "x1", "label": "A", "type": "ssh", "host": "192.0.2.80"}
    (tmp_path / "devices.json").write_text(json.dumps(
        {"version": 1, "devices": [dev, dev], "selected": []}))
    reg = make(tmp_path)
    assert [d.id for d in reg.list()] == [DEFAULT_DEVICE_ID]


# ── config path ──────────────────────────────────────────────────────────────

def test_default_path_is_outside_repo_per_platform(tmp_path):
    home_env = {"XDG_CONFIG_HOME": str(tmp_path / "xdg")}
    assert default_devices_path(home_env, "linux") == tmp_path / "xdg" / "BakerPi-Installer" / "devices.json"
    win = default_devices_path({"APPDATA": str(tmp_path / "ad")}, "win32")
    assert win == tmp_path / "ad" / "BakerPi-Installer" / "devices.json"


def test_env_override_for_path(tmp_path):
    p = default_devices_path({"BAKERPI_DEVICES_FILE": str(tmp_path / "x.json")}, "linux")
    assert p == tmp_path / "x.json"


def test_unsafe_ids_in_file_treated_as_corrupt(tmp_path):
    dev = {"id": "<img src=x>", "label": "A", "type": "ssh", "host": "192.0.2.81"}
    (tmp_path / "devices.json").write_text(json.dumps(
        {"version": 1, "devices": [dev], "selected": []}))
    assert [d.id for d in make(tmp_path).list()] == [DEFAULT_DEVICE_ID]
