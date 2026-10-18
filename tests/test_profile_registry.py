"""Unit tests for fleet install profile storage. No hardware or network required."""
import json
import stat
import sys

import pytest

from profile_registry import (
    Profile, ProfileError, ProfileNotFound, ProfileRegistry, default_profiles_path,
)

CATALOG = {"nmap", "tcpdump", "kismet", "bakerpi_core"}


def make(tmp_path, known=CATALOG):
    return ProfileRegistry(tmp_path / "profiles.json",
                           known_tools=None if known is None else (lambda: set(known)))


# ── add / get / list ─────────────────────────────────────────────────────────

def test_empty_registry_has_no_profiles_and_writes_nothing(tmp_path):
    reg = make(tmp_path)
    assert reg.list() == []
    assert not (tmp_path / "profiles.json").exists()


def test_add_assigns_id_and_normalises(tmp_path):
    reg = make(tmp_path)
    p = reg.add(name="  Recon kit ", description=" scans ", tool_ids=["nmap", "tcpdump"])
    assert p.id
    assert (p.name, p.description, p.tool_ids) == ("Recon kit", "scans", ["nmap", "tcpdump"])
    assert reg.get(p.id) == p
    assert [x.id for x in reg.list()] == [p.id]


def test_description_is_optional(tmp_path):
    assert make(tmp_path).add(name="A", tool_ids=["nmap"]).description == ""


def test_tool_order_is_kept_and_duplicates_dropped(tmp_path):
    p = make(tmp_path).add(name="A", tool_ids=["tcpdump", "nmap", "tcpdump", "kismet"])
    assert p.tool_ids == ["tcpdump", "nmap", "kismet"]


def test_builtin_catalog_tools_are_allowed(tmp_path):
    assert make(tmp_path).add(name="A", tool_ids=["bakerpi_core"]).tool_ids == ["bakerpi_core"]


# ── validation ───────────────────────────────────────────────────────────────

@pytest.mark.parametrize("fields", [
    {"tool_ids": ["nmap"]},                                  # name required
    {"name": "   ", "tool_ids": ["nmap"]},
    {"name": "A"},                                           # tools required
    {"name": "A", "tool_ids": []},
    {"name": "A", "tool_ids": "nmap"},                       # must be a list
    {"name": "A", "tool_ids": [1]},
    {"name": "A", "tool_ids": ["nmap; rm -rf /"]},           # malformed id
    {"name": "A", "tool_ids": ["no_such_tool"]},             # not in catalog
    {"name": "A", "tool_ids": ["nmap", "no_such_tool"]},
    {"name": "x" * 200, "tool_ids": ["nmap"]},
    {"name": "a\nb", "tool_ids": ["nmap"]},
    {"name": "A", "description": "d" * 600, "tool_ids": ["nmap"]},
    {"name": "A", "description": 5, "tool_ids": ["nmap"]},
])
def test_add_rejects_invalid(tmp_path, fields):
    reg = make(tmp_path)
    with pytest.raises(ProfileError):
        reg.add(**fields)
    assert reg.list() == []
    assert not (tmp_path / "profiles.json").exists()


def test_unknown_tool_error_names_the_tool(tmp_path):
    with pytest.raises(ProfileError, match="ghost_tool"):
        make(tmp_path).add(name="A", tool_ids=["nmap", "ghost_tool"])


def test_duplicate_names_rejected_case_insensitively(tmp_path):
    reg = make(tmp_path)
    reg.add(name="Recon", tool_ids=["nmap"])
    with pytest.raises(ProfileError):
        reg.add(name="recon", tool_ids=["tcpdump"])
    assert len(reg.list()) == 1


# ── update / remove ──────────────────────────────────────────────────────────

def test_update_is_partial(tmp_path):
    reg = make(tmp_path)
    p = reg.add(name="A", description="d", tool_ids=["nmap"])
    u = reg.update(p.id, name="B")
    assert (u.name, u.description, u.tool_ids) == ("B", "d", ["nmap"])
    u = reg.update(p.id, tool_ids=["tcpdump", "nmap"])
    assert (u.name, u.tool_ids) == ("B", ["tcpdump", "nmap"])
    assert reg.get(p.id) == u


def test_update_can_clear_description(tmp_path):
    reg = make(tmp_path)
    p = reg.add(name="A", description="d", tool_ids=["nmap"])
    assert reg.update(p.id, description=None).description == ""


def test_update_rejects_invalid_and_keeps_old_value(tmp_path):
    reg = make(tmp_path)
    p = reg.add(name="A", tool_ids=["nmap"])
    with pytest.raises(ProfileError):
        reg.update(p.id, tool_ids=["ghost_tool"])
    with pytest.raises(ProfileError):
        reg.update(p.id, tool_ids=[])
    with pytest.raises(ProfileError):
        reg.update(p.id, name="")
    assert reg.get(p.id).tool_ids == ["nmap"] and reg.get(p.id).name == "A"


def test_update_cannot_change_id(tmp_path):
    reg = make(tmp_path)
    p = reg.add(name="A", tool_ids=["nmap"])
    assert reg.update(p.id, id="hacked").id == p.id


def test_update_name_collision_rejected_but_own_name_allowed(tmp_path):
    reg = make(tmp_path)
    a = reg.add(name="A", tool_ids=["nmap"])
    b = reg.add(name="B", tool_ids=["nmap"])
    with pytest.raises(ProfileError):
        reg.update(b.id, name="a")
    assert reg.update(a.id, name="A", description="same name is fine").name == "A"


def test_update_and_remove_unknown(tmp_path):
    reg = make(tmp_path)
    with pytest.raises(ProfileNotFound):
        reg.update("nope", name="x")
    with pytest.raises(ProfileNotFound):
        reg.remove("nope")
    with pytest.raises(ProfileNotFound):
        reg.get("nope")


def test_remove(tmp_path):
    reg = make(tmp_path)
    a = reg.add(name="A", tool_ids=["nmap"])
    b = reg.add(name="B", tool_ids=["nmap"])
    reg.remove(a.id)
    assert [p.id for p in reg.list()] == [b.id]
    assert [p.id for p in make(tmp_path).list()] == [b.id]


# ── catalog drift ────────────────────────────────────────────────────────────

def test_catalog_drift_does_not_invalidate_stored_profiles(tmp_path):
    p = make(tmp_path).add(name="A", tool_ids=["nmap", "kismet"])
    shrunk = make(tmp_path, known={"nmap"})  # kismet dropped from the catalog
    got = shrunk.get(p.id)
    assert got.tool_ids == ["nmap", "kismet"]
    assert shrunk.unknown_tools(got) == ["kismet"]
    # a rename is still possible; changing the tool list re-checks the catalog
    assert shrunk.update(p.id, name="B").name == "B"
    with pytest.raises(ProfileError):
        shrunk.update(p.id, tool_ids=["nmap", "kismet"])
    assert shrunk.update(p.id, tool_ids=["nmap"]).tool_ids == ["nmap"]


def test_without_catalog_callable_only_shape_is_checked(tmp_path):
    reg = make(tmp_path, known=None)
    assert reg.add(name="A", tool_ids=["whatever"]).tool_ids == ["whatever"]
    assert reg.unknown_tools(reg.list()[0]) == []


# ── persistence ──────────────────────────────────────────────────────────────

def test_persists_across_instances(tmp_path):
    reg = make(tmp_path)
    a = reg.add(name="A", description="first", tool_ids=["tcpdump", "nmap"])
    b = reg.add(name="B", tool_ids=["kismet"])
    reg.update(a.id, name="A2")

    again = make(tmp_path)
    assert [p.id for p in again.list()] == [a.id, b.id]
    assert again.get(a.id) == Profile(a.id, "A2", "first", ["tcpdump", "nmap"])


def test_storage_format_has_no_extra_fields_or_secrets(tmp_path):
    reg = make(tmp_path)
    reg.add(name="A", tool_ids=["nmap"], password="hunter2", host="192.0.2.1")
    text = (tmp_path / "profiles.json").read_text()
    assert "hunter2" not in text and "192.0.2.1" not in text
    data = json.loads(text)
    assert data["version"] == 1
    assert set(data["profiles"][0]) == {"id", "name", "description", "tool_ids"}


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions")
def test_profiles_file_is_private(tmp_path):
    make(tmp_path).add(name="A", tool_ids=["nmap"])
    assert stat.S_IMODE((tmp_path / "profiles.json").stat().st_mode) == 0o600


@pytest.mark.skipif(sys.platform.startswith("win"), reason="POSIX permissions")
def test_permissions_stay_private_after_rewrite(tmp_path):
    reg = make(tmp_path)
    p = reg.add(name="A", tool_ids=["nmap"])
    (tmp_path / "profiles.json").chmod(0o644)
    reg.update(p.id, name="B")
    assert stat.S_IMODE((tmp_path / "profiles.json").stat().st_mode) == 0o600


def test_creates_missing_parent_directory(tmp_path):
    reg = ProfileRegistry(tmp_path / "a" / "b" / "profiles.json")
    reg.add(name="A", tool_ids=["nmap"])
    assert (tmp_path / "a" / "b" / "profiles.json").exists()


def test_no_temp_files_left_behind(tmp_path):
    make(tmp_path).add(name="A", tool_ids=["nmap"])
    assert [p.name for p in tmp_path.iterdir()] == ["profiles.json"]


def test_corrupt_file_is_set_aside_not_fatal(tmp_path):
    (tmp_path / "profiles.json").write_text("{not json")
    reg = make(tmp_path)
    assert reg.list() == []
    assert (tmp_path / "profiles.json.bad").read_text() == "{not json"
    reg.add(name="A", tool_ids=["nmap"])  # still usable afterwards
    assert len(make(tmp_path).list()) == 1


def test_duplicate_ids_in_file_treated_as_corrupt(tmp_path):
    prof = {"id": "p1", "name": "A", "tool_ids": ["nmap"]}
    (tmp_path / "profiles.json").write_text(json.dumps(
        {"version": 1, "profiles": [prof, dict(prof, name="B")]}))
    assert make(tmp_path).list() == []
    assert (tmp_path / "profiles.json.bad").exists()


def test_unsafe_ids_in_file_treated_as_corrupt(tmp_path):
    prof = {"id": "<img src=x>", "name": "A", "tool_ids": ["nmap"]}
    (tmp_path / "profiles.json").write_text(json.dumps({"version": 1, "profiles": [prof]}))
    assert make(tmp_path).list() == []


def test_malformed_profile_in_file_treated_as_corrupt(tmp_path):
    prof = {"id": "p1", "name": "A", "tool_ids": []}
    (tmp_path / "profiles.json").write_text(json.dumps({"version": 1, "profiles": [prof]}))
    assert make(tmp_path).list() == []


# ── config path ──────────────────────────────────────────────────────────────

def test_default_path_is_outside_repo_per_platform(tmp_path):
    xdg = default_profiles_path({"XDG_CONFIG_HOME": str(tmp_path / "xdg")}, "linux")
    assert xdg == tmp_path / "xdg" / "BakerPi-Installer" / "profiles.json"
    win = default_profiles_path({"APPDATA": str(tmp_path / "ad")}, "win32")
    assert win == tmp_path / "ad" / "BakerPi-Installer" / "profiles.json"


def test_env_override_for_path(tmp_path):
    p = default_profiles_path({"BAKERPI_PROFILES_FILE": str(tmp_path / "x.json")}, "linux")
    assert p == tmp_path / "x.json"
