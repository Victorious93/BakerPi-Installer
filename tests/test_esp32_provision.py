"""USB serial provisioning contract v1, host side. Serial port is mocked.

UNTESTED ON HARDWARE: these tests prove protocol handling, schema validation
and redaction only.
"""
import json

import pytest

import esp32_provision as ep

SECRET = "hunter2-super-secret-value"
TOKEN = "tok_ABCDEFGHIJKLMNOPQRSTUVWX"


class FakeSerial:
    """Scripted board: responder(cmd_dict) -> list of reply lines (bytes)."""
    instances = []

    def __init__(self, responder, preamble=(), dead=False):
        self.responder, self.dead = responder, dead
        self.rx = list(preamble)
        self.written, self.opened, self.closed = [], False, False
        self.rts_history = []
        self._rts = None
        self.dtr = None
        FakeSerial.instances.append(self)

    @property
    def rts(self):
        return self._rts

    @rts.setter
    def rts(self, v):
        self._rts = v
        self.rts_history.append(v)

    def open(self):
        self.opened = True
        self.rts_at_open = self._rts
        self.dtr_at_open = self.dtr

    def close(self):
        self.closed = True

    def reset_input_buffer(self):
        pass

    def write(self, data):
        self.written.append(data)
        if not self.dead:
            self.rx.extend(self.responder(json.loads(data.decode())))

    def flush(self):
        pass

    def readline(self):
        return self.rx.pop(0) if self.rx else b""

    def sent(self):
        return [json.loads(w.decode()) for w in self.written]


class Clock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        self.t += 0.25  # each poll costs time so timeouts terminate
        return self.t

    def sleep(self, s):
        self.t += s


def line(obj):
    return (json.dumps(obj) + "\n").encode()


def board(project, env=None, cfg=None, provision_reply=None):
    store = {"cfg": dict(cfg or {})}

    def respond(c):
        cmd = c.get("cmd")
        assert c.get("v") == 1
        if cmd == "hello":
            r = {"v": 1, "ok": True, "project": project, "fw": "0.2.0", "chip": "esp32s3",
                 "keys": list((cfg or {}).keys())}
            if env:
                r["env"] = env
            return [b"I (123) boot: log line\n", line(r)]
        if cmd == "get":
            return [line({"v": 1, "ok": True, "cfg": store["cfg"], "provisioned": True})]
        if cmd == "provision":
            store["last"] = c["cfg"]
            return [line(provision_reply or {"v": 1, "ok": True})]
        if cmd in ("reboot", "factory_reset"):
            return [line({"v": 1, "ok": True})]
        return [line({"v": 1, "ok": False, "err": "unknown_cmd"})]
    return respond, store


def session_kw(fake):
    clk = Clock()
    return {"serial_factory": lambda: fake, "clock": clk, "sleep": clk.sleep}


VM_BRIDGE = {"ap_ssid": "VictorModem", "ap_pass": SECRET, "api_token": TOKEN, "hub_baud": 921600}


# ── hello / log skipping / reset ───────────────────────────────────────────────

def test_hello_skips_logs_and_returns_schema():
    resp, _ = board("victormodem", "esp32s3_bridge5g")
    fake = FakeSerial(resp, preamble=[b"ESP-ROM:esp32s3\n", b"garbage {not json\n"])
    out = ep.do_hello("/dev/ttyACM0", **session_kw(fake))
    assert out["hello"]["project"] == "victormodem"
    names = [f["name"] for f in out["schema"]["fields"]]
    assert names == ["ap_ssid", "ap_pass", "api_token", "hub_baud"]
    assert out["schema"]["partial"] is False
    assert "ESP-ROM:esp32s3" in out["logs"]
    assert fake.closed and fake.dtr_at_open is False and fake.rts_at_open is False


def test_reset_pulses_rts():
    resp, _ = board("pyra-claw")
    fake = FakeSerial(resp)
    ep.do_hello("/dev/ttyUSB0", reset=True, **session_kw(fake))
    assert fake.rts_history[-2:] == [True, False]


def test_hello_retries_inside_window():
    resp, _ = board("pyra-claw")
    calls = {"n": 0}

    def flaky(c):
        calls["n"] += 1
        return [] if calls["n"] < 3 else resp(c)
    fake = FakeSerial(flaky)
    out = ep.do_hello("/dev/ttyUSB0", **session_kw(fake))
    assert out["hello"]["ok"] and calls["n"] == 3


def test_hello_timeout():
    fake = FakeSerial(lambda c: [], dead=True)
    with pytest.raises(ep.ProvisionTimeout):
        ep.do_hello("/dev/ttyUSB0", **session_kw(fake))
    assert fake.closed


def test_reply_timeout_on_get():
    resp, _ = board("pyra-claw")
    fake = FakeSerial(lambda c: resp(c) if c["cmd"] == "hello" else [b"log only\n"])
    with pytest.raises(ep.ProvisionTimeout):
        ep.do_get("/dev/ttyUSB0", **session_kw(fake))


def test_ignores_non_v1_json():
    fake = FakeSerial(lambda c: [line({"v": 2, "ok": True}), line({"hello": 1}),
                                 line({"v": 1, "ok": True, "project": "pyra-claw",
                                       "fw": "x", "chip": "esp32", "keys": []})])
    out = ep.do_hello("/dev/ttyUSB0", **session_kw(fake))
    assert out["hello"]["project"] == "pyra-claw"


def test_unknown_cmd_reply_surfaces():
    resp, _ = board("pyra-claw")
    fake = FakeSerial(resp)
    with ep.Session("/dev/ttyUSB0", **session_kw(fake)) as s:
        s.ser.write(b'{"v":1,"cmd":"bogus"}\n')
        r = s.read_reply()
    assert r == {"v": 1, "ok": False, "err": "unknown_cmd"}
    assert s.safe(r)["err_text"].startswith("The firmware does not know")
    with pytest.raises(ep.ProvisionError):
        ep.encode("bogus")


def test_bad_port_rejected():
    with pytest.raises(ep.esp32_flasher.FlashValidationError):
        ep.Session("/etc/passwd")


# ── get / redaction ─────────────────────────────────────────────────────────────

def test_get_redacts_even_if_firmware_leaks():
    resp, _ = board("victormodem", "esp32s3_bridge5g", cfg=VM_BRIDGE)
    fake = FakeSerial(resp)
    out = ep.do_get("/dev/ttyACM0", **session_kw(fake))
    cfg = out["reply"]["cfg"]
    assert cfg["ap_pass"] == "***" and cfg["api_token"] == "***"
    assert cfg["ap_ssid"] == "VictorModem" and cfg["hub_baud"] == 921600
    assert out["reply"]["provisioned"] is True
    assert SECRET not in json.dumps(out) and TOKEN not in json.dumps(out)


def test_pyra_get_redacts():
    resp, _ = board("pyra-claw", cfg={"ssid": "home", "pass": SECRET, "mqtt_pass": SECRET,
                                      "hub_token": TOKEN, "broker_port": 1883})
    out = ep.do_get("/dev/ttyUSB0", **session_kw(FakeSerial(resp)))
    s = json.dumps(out)
    assert SECRET not in s and TOKEN not in s and '"ssid": "home"' in s


def test_error_and_logs_scrub_secret():
    resp, _ = board("pyra-claw",
                    provision_reply={"v": 1, "ok": False, "err": f"bad pass {SECRET}"})

    def r(c):
        out = resp(c)
        return ([f"echo {SECRET}\n".encode()] + out) if c["cmd"] == "provision" else out
    out = ep.do_apply("/dev/ttyUSB0", {"pass": SECRET}, **session_kw(FakeSerial(r)))
    s = json.dumps(out)
    assert SECRET not in s and out["reply"]["ok"] is False and "***" in out["reply"]["err"]


# ── apply: partial vs atomic ────────────────────────────────────────────────────

def test_pyra_partial_update():
    resp, store = board("pyra-claw")
    fake = FakeSerial(resp)
    out = ep.do_apply("/dev/ttyUSB0", {"ssid": "home", "broker_port": "1884"}, **session_kw(fake))
    assert out["reply"]["ok"] and store["last"] == {"ssid": "home", "broker_port": 1884}
    assert out["sent_keys"] == ["broker_port", "ssid"]


def test_vm_atomic_requires_all_fields():
    resp, store = board("victormodem", "esp32s3_bridge5g")
    with pytest.raises(ep.SchemaError) as e:
        ep.do_apply("/dev/ttyACM0", {"ap_ssid": "x", "ap_pass": SECRET},
                    **session_kw(FakeSerial(resp)))
    assert "missing" in str(e.value) and SECRET not in str(e.value)
    assert "last" not in store


def test_vm_atomic_ok():
    resp, store = board("victormodem", "esp32s3_bridge5g")
    out = ep.do_apply("/dev/ttyACM0", VM_BRIDGE, **session_kw(FakeSerial(resp)))
    assert out["reply"]["ok"] and store["last"] == VM_BRIDGE
    assert SECRET not in json.dumps(out)


@pytest.mark.parametrize("env,expected", [
    ("esp32s3_bridge5g", {"ap_ssid", "ap_pass", "api_token", "hub_baud"}),
    ("esp32s3_direct4g", {"ap_ssid", "ap_pass", "api_token", "apn", "apn_user", "apn_pass"}),
    ("tsim7600_4g", {"ap_ssid", "ap_pass", "api_token", "apn", "apn_user", "apn_pass"}),
])
def test_vm_env_fields(env, expected):
    assert {f["name"] for f in ep.get_schema("victormodem", env)["fields"]} == expected


@pytest.mark.parametrize("cfg,needle", [
    ({**VM_BRIDGE, "apn": "internet"}, "unknown"),            # apn not for bridge5g
    ({**VM_BRIDGE, "extra": 1}, "unknown"),
    ({**VM_BRIDGE, "ap_pass": "short"}, "ap_pass: length"),
    ({**VM_BRIDGE, "api_token": "x" * 15}, "api_token: length"),
    ({**VM_BRIDGE, "api_token": "x" * 129}, "api_token: length"),
    ({**VM_BRIDGE, "ap_ssid": ""}, "ap_ssid: length"),
    ({**VM_BRIDGE, "ap_ssid": "x" * 33}, "ap_ssid: length"),
    ({**VM_BRIDGE, "hub_baud": 9599}, "hub_baud: must be"),
    ({**VM_BRIDGE, "hub_baud": 3000001}, "hub_baud: must be"),
    ({**VM_BRIDGE, "hub_baud": True}, "integer"),
    ({**VM_BRIDGE, "ap_ssid": 5}, "string"),
])
def test_vm_schema_rejection(cfg, needle):
    with pytest.raises(ep.SchemaError) as e:
        ep.validate_cfg("victormodem", "esp32s3_bridge5g", cfg)
    assert needle in str(e.value) and SECRET not in str(e.value)


def test_vm_4g_apn_ok():
    cfg = {"ap_ssid": "VM", "ap_pass": SECRET, "api_token": TOKEN,
           "apn": "", "apn_user": "", "apn_pass": ""}
    assert ep.validate_cfg("victormodem", "tsim7600_4g", cfg) == cfg
    with pytest.raises(ep.SchemaError):
        ep.validate_cfg("victormodem", "tsim7600_4g", {**cfg, "apn": "a" * 64})


@pytest.mark.parametrize("cfg", [
    {"pc_mac": "AA:BB:CC:DD:EE"}, {"pc_mac": "aa-bb-cc-dd-ee-ff"},
    {"pc_broadcast": "256.1.1.1"}, {"broker_port": 70000}, {"broker_port": "abc"},
    {"nope": "x"}, {}, {"ssid": "a\nb"}, {"node_id": ""}, {"pass": "x" * 64},
])
def test_pyra_schema_rejection(cfg):
    with pytest.raises(ep.SchemaError):
        ep.validate_cfg("pyra-claw", None, cfg)


def test_pyra_valid_formats():
    c = {"pc_mac": "AA:bb:CC:dd:EE:ff", "pc_broadcast": "192.168.1.255"}
    assert ep.validate_cfg("pyra-claw", None, c) == {**c, "pc_mac": "AA:BB:CC:DD:EE:FF"}
    d = {f["name"]: f.get("default") for f in ep.get_schema("pyra-claw")["fields"]}
    assert d["broker_port"] == 1883 and d["pc_broadcast"] == "255.255.255.255"


def test_unknown_project_or_env():
    with pytest.raises(ep.SchemaError):
        ep.validate_cfg("other", None, {"a": 1})
    with pytest.raises(ep.SchemaError):
        ep.validate_cfg("victormodem", "nope", VM_BRIDGE)


def test_reboot_and_factory_reset():
    resp, _ = board("pyra-claw")
    fake = FakeSerial(resp)
    assert ep.do_simple("/dev/ttyUSB0", "reboot", **session_kw(fake))["reply"]["ok"]
    assert fake.sent()[-1]["cmd"] == "reboot"
    with pytest.raises(ep.ProvisionError):
        ep.do_simple("/dev/ttyUSB0", "provision", **session_kw(fake))


# ── HTTP endpoints ──────────────────────────────────────────────────────────────

fastapi = pytest.importorskip("fastapi")
pytest.importorskip("httpx")


@pytest.fixture
def api(monkeypatch):
    from fastapi.testclient import TestClient
    import server
    state = {"fake": None}

    def install(responder, dead=False):
        state["fake"] = FakeSerial(responder, dead=dead)
        return state["fake"]

    orig = ep.Session.__init__

    def init(self, port, reset=False, **kw):
        clk = Clock()
        orig(self, port, reset=reset, serial_factory=lambda: state["fake"],
             clock=clk, sleep=clk.sleep)
    monkeypatch.setattr(ep.Session, "__init__", init)
    with TestClient(server.app) as c:
        c.install = install
        yield c


def test_api_hello_and_get(api):
    resp, _ = board("victormodem", "tsim7600_4g",
                    cfg={"ap_ssid": "VM", "ap_pass": SECRET, "api_token": TOKEN})
    api.install(resp)
    r = api.post("/api/esp32/provision/hello", json={"port": "/dev/ttyUSB0"})
    assert r.status_code == 200 and r.json()["schema"]["env"] == "tsim7600_4g"
    api.install(resp)
    r = api.post("/api/esp32/provision/get", json={"port": "/dev/ttyUSB0"})
    assert r.status_code == 200 and SECRET not in r.text and TOKEN not in r.text


def test_api_port_validation(api):
    for port in ["/dev/sda", "../../x", "COM3; rm -rf /", ""]:
        r = api.post("/api/esp32/provision/hello", json={"port": port})
        assert r.status_code == 400


def test_api_apply_schema_reject_no_secret_echo(api):
    resp, _ = board("victormodem", "esp32s3_bridge5g")
    api.install(resp)
    r = api.post("/api/esp32/provision/apply",
                 json={"port": "/dev/ttyACM0", "cfg": {"ap_pass": SECRET}})
    assert r.status_code == 422 and SECRET not in r.text
    api.install(resp)
    r = api.post("/api/esp32/provision/apply", json={"port": "/dev/ttyACM0", "cfg": SECRET})
    assert r.status_code == 422 and SECRET not in r.text


def test_api_apply_ok(api):
    resp, store = board("pyra-claw")
    api.install(resp)
    r = api.post("/api/esp32/provision/apply",
                 json={"port": "/dev/ttyUSB0", "cfg": {"hub_token": TOKEN}})
    assert r.status_code == 200 and store["last"] == {"hub_token": TOKEN}
    assert TOKEN not in r.text


def test_api_timeout_504(api):
    api.install(lambda c: [], dead=True)
    r = api.post("/api/esp32/provision/reboot", json={"port": "/dev/ttyUSB0"})
    assert r.status_code == 504


def test_api_factory_reset_needs_confirm(api):
    resp, _ = board("pyra-claw")
    for body in [{"port": "/dev/ttyUSB0"}, {"port": "/dev/ttyUSB0", "confirm": False}]:
        assert api.post("/api/esp32/provision/factory_reset", json=body).status_code == 400
    assert api.post("/api/esp32/provision/factory_reset",
                    json={"port": "/dev/ttyUSB0", "confirm": "yes"}).status_code == 422
    fake = api.install(resp)
    r = api.post("/api/esp32/provision/factory_reset",
                 json={"port": "/dev/ttyUSB0", "confirm": True})
    assert r.status_code == 200 and fake.sent()[-1]["cmd"] == "factory_reset"


@pytest.mark.parametrize("err,needle", [
    ("unknown_key:foo", "Unknown setting 'foo'"), ("bad_type:broker_port", "Wrong type"),
    ("bad_value:pc_mac", "Invalid value for 'pc_mac'"), ("unknown_cmd", "does not know"),
    ("cfg_not_object", "JSON object"), ("weird", "weird"),
])
def test_humanize_err(err, needle):
    assert needle in ep.humanize_err(err)


def test_pyra_bad_value_reply_is_readable_and_mac_upper():
    resp, store = board("pyra-claw", provision_reply={"v": 1, "ok": False, "err": "bad_value:pc_mac"})
    out = ep.do_apply("/dev/ttyUSB0", {"pc_mac": "aa:bb:cc:dd:ee:01"}, **session_kw(FakeSerial(resp)))
    assert store["last"] == {"pc_mac": "AA:BB:CC:DD:EE:01"}
    assert "Nothing was saved" in out["reply"]["err_text"]
