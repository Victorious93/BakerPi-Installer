#!/usr/bin/env python3
"""
BakerPi Tool Installer Server
Runs on PC (SSH mode) or on Pi Zero itself (local mode).
Serves a responsive web UI for selecting and installing tools.
"""

import argparse
import asyncio
import json
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
import webbrowser
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Optional

import paramiko
import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from device_registry import (
    DEFAULT_DEVICE_ID, Device, DeviceError, DeviceNotFound, DeviceRegistry,
    build_default_device,
)
from profile_registry import (
    Profile, ProfileError, ProfileNotFound, ProfileRegistry,
)

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.resolve()
CATALOG_PATH = BASE_DIR / "tools" / "catalog.json"
SCRIPTS_DIR = BASE_DIR / "install_scripts"
STATIC_DIR = BASE_DIR / "static"

# ── Globals ───────────────────────────────────────────────────────────────────

app = FastAPI(title="BakerPi Tool Installer", version="1.0.0")
config: dict = {}  # CLI-provided single target: mode / host / user / port / key_file
registry = DeviceRegistry(default_factory=lambda: build_default_device(config))
profiles = ProfileRegistry(known_tools=lambda: catalog_tool_ids())  # fleet install profiles
ssh_clients: dict[str, paramiko.SSHClient] = {}  # device_id → live SSH client
_ssh_creds: dict[str, dict] = {}  # device_id → {password, key_file}; memory only, never persisted
jobs: dict[str, dict] = {}  # job_id → {status, action, tool_ids, devices, events, ...}
log = logging.getLogger("installer")
_executor = ThreadPoolExecutor(max_workers=16)  # install jobs run one task per target device

# ── Catalog ───────────────────────────────────────────────────────────────────

def load_catalog() -> dict:
    with open(CATALOG_PATH) as f:
        return json.load(f)

def flat_tools(catalog: dict) -> dict[str, dict]:
    """Returns dict of tool_id → tool (with category info merged in)."""
    result = {}
    for cat in catalog["categories"]:
        for tool in cat["tools"]:
            result[tool["id"]] = {**tool, "category_id": cat["id"], "category_name": cat["name"]}
    return result

def catalog_tool_ids() -> set[str]:
    return set(flat_tools(load_catalog()))

# ── Command Execution ─────────────────────────────────────────────────────────

def run_local(cmd: str) -> tuple[int, str]:
    """Execute command locally (on-device mode)."""
    proc = subprocess.run(
        cmd, shell=True, capture_output=True, text=True, timeout=300
    )
    return proc.returncode, proc.stdout + proc.stderr

def stream_local(cmd: str):
    """Yield output lines from a local command."""
    proc = subprocess.Popen(
        cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, bufsize=1
    )
    for line in proc.stdout:
        yield line
    proc.wait()
    yield f"\n[EXIT {proc.returncode}]\n"

def _live_client(device_id: str) -> Optional[paramiko.SSHClient]:
    client = ssh_clients.get(device_id)
    transport = client.get_transport() if client else None
    return client if transport is not None and transport.is_active() else None

def device_connected(device: Device) -> bool:
    return True if device.is_local else _live_client(device.id) is not None

def run_ssh(cmd: str, device: Optional[Device] = None) -> tuple[int, str]:
    """Execute command over SSH (PC mode)."""
    device = device or registry.default_device()
    client = _live_client(device.id)
    if not client:
        raise RuntimeError(f"SSH not connected ({device.label})")
    _, stdout, stderr = client.exec_command(cmd, timeout=300)
    rc = stdout.channel.recv_exit_status()
    return rc, stdout.read().decode() + stderr.read().decode()

def stream_ssh(cmd: str, device: Optional[Device] = None):
    """Yield output lines from an SSH command."""
    device = device or registry.default_device()
    client = _live_client(device.id)
    if not client:
        yield "[ERROR] SSH not connected\n"
        return
    _, stdout, stderr = client.exec_command(cmd, get_pty=True, timeout=300)
    for line in stdout:
        yield line
    rc = stdout.channel.recv_exit_status()
    yield f"\n[EXIT {rc}]\n"

def run_cmd(cmd: str, device: Optional[Device] = None) -> tuple[int, str]:
    """Run a command on `device` (default: the CLI-provided target)."""
    device = device or registry.default_device()
    if device.is_local:
        return run_local(cmd)
    return run_ssh(cmd, device)

def stream_cmd(cmd: str, device: Optional[Device] = None):
    device = device or registry.default_device()
    if device.is_local:
        yield from stream_local(cmd)
    else:
        yield from stream_ssh(cmd, device)

# ── Status Check ──────────────────────────────────────────────────────────────

def check_tool_installed(tool: dict, device: Optional[Device] = None) -> bool:
    check = tool.get("check_cmd", "")
    if not check:
        return False
    try:
        rc, _ = run_cmd(check, device)
        return rc == 0
    except Exception:
        return False

def check_tool_installed_fast(tool: dict, device: Optional[Device] = None) -> bool:
    """Fast check using dpkg for packages, fallback to check_cmd."""
    pkg = tool.get("check_pkg", "")
    if pkg:
        try:
            rc, out = run_cmd(f"dpkg -l {pkg} 2>/dev/null | grep -q '^ii'", device)
            return rc == 0
        except Exception:
            pass
    return check_tool_installed(tool, device)

# ── SSH Connection ────────────────────────────────────────────────────────────

def _drop_client(device_id: str) -> None:
    client = ssh_clients.pop(device_id, None)
    if client:
        try:
            client.close()
        except Exception:
            pass

def connect_ssh(host: str, user: str, port: int, password: Optional[str],
                key_file: Optional[str], device_id: str = DEFAULT_DEVICE_ID):
    """Open an SSH connection for `device_id` (default: the CLI-provided target)."""
    client = paramiko.SSHClient()
    client.set_missing_host_key_policy(paramiko.AutoAddPolicy())
    kwargs = dict(hostname=host, username=user, port=port, timeout=15)
    if key_file:
        kwargs["key_filename"] = key_file
    elif password:
        kwargs["password"] = password
    else:
        # Try agent / default key
        pass
    _ssh_creds[device_id] = {"password": password, "key_file": key_file}
    client.connect(**kwargs)
    _drop_client(device_id)
    ssh_clients[device_id] = client
    log.info(f"SSH connected to {user}@{host}:{port}")

def ensure_connected(device: Device) -> None:
    """Make sure `device` has a live connection, reconnecting with remembered
    in-memory credentials / key / agent if needed. Raises on failure."""
    if device_connected(device):
        return
    creds = _ssh_creds.get(device.id, {})
    connect_ssh(device.host, device.user, device.port, creds.get("password"),
                creds.get("key_file") or device.key_file, device.id)

# ── Install / Update Logic ────────────────────────────────────────────────────

def _script_cmd(script: str, tool_id: str, mode_arg: str = "",
                device: Optional[Device] = None) -> str:
    """Build the shell command for a given install script, tool, and mode."""
    script_path = f"/usr/local/BakerPi/tool_installer/install_scripts/{script}"
    local_path = str(SCRIPTS_DIR / script)
    suffix = f" {tool_id}" + (f" {mode_arg}" if mode_arg else "")
    device = device or registry.default_device()
    if device.is_local:
        return f"bash {local_path}{suffix}"
    return f"bash {script_path}{suffix}"

def get_install_cmd(tool: dict, device: Optional[Device] = None) -> str:
    """Returns the shell command to install a tool."""
    tool_id = tool["id"]
    script = tool.get("install_script", "")

    if tool.get("builtin"):
        return "echo 'Built-in — already available via BakerPi core service.'"

    if not script:
        pkgs = tool.get("packages", [])
        if pkgs:
            return f"apt-get install -y --no-install-recommends {' '.join(pkgs)}"
        return f"echo 'No install method defined for {tool_id}'"

    return _script_cmd(script, tool_id, device=device)

def get_update_cmd(tool: dict, device: Optional[Device] = None) -> str:
    """Returns the shell command to update an already-installed tool."""
    tool_id = tool["id"]

    if tool.get("builtin"):
        return "echo 'Built-in — managed by the BakerPi core service; no update needed.'"

    # Catalog-provided explicit update command takes priority
    explicit = tool.get("update_cmd", "")
    if explicit:
        return explicit

    script = tool.get("install_script", "")
    if script:
        # Pass "update" as the second argument; scripts handle git pull / pip upgrade
        return _script_cmd(script, tool_id, "update", device)

    # apt packages: refresh lists then upgrade only the named packages
    pkgs = tool.get("packages", [])
    if pkgs:
        pkg_list = " ".join(pkgs)
        return (f"apt-get update -qq && "
                f"apt-get install -y --only-upgrade --no-install-recommends {pkg_list}")

    return f"echo 'No update method defined for {tool_id}'"

def get_uninstall_cmd(tool: dict) -> str:
    """Returns the shell command to remove a tool."""
    import re
    tool_id = tool["id"]

    if tool.get("builtin"):
        return "echo 'Built-in — cannot be uninstalled here; managed by BakerPi core service.'"

    # Catalog-provided explicit uninstall command takes priority
    explicit = tool.get("uninstall_cmd", "")
    if explicit:
        return explicit

    # apt packages: purge and autoremove
    pkgs = tool.get("packages", [])
    if pkgs:
        pkg_list = " ".join(pkgs)
        return f"apt-get remove -y {pkg_list} && apt-get autoremove -y"

    # Infer from check_cmd:
    check = tool.get("check_cmd", "")

    # pip-installed: "python3 -c 'import foo'"
    m = re.search(r"import\s+([\w.]+)", check)
    if m:
        mod = m.group(1).split(".")[0]
        return f"pip3 uninstall -y {mod} 2>/dev/null || true"

    # git-cloned to /opt/<dir>: "ls /opt/foo" or "test -d /opt/foo"
    m = re.search(r"/opt/([\w_-]+)", check)
    if m:
        opt_dir = f"/opt/{m.group(1)}"
        return (f"systemctl disable --now $(basename {opt_dir}) 2>/dev/null || true; "
                f"rm -rf {opt_dir}")

    return (f"echo 'No automated uninstall for {tool_id}. "
            f"Check /opt/, pip list, and dpkg -l to locate installed files.'")

_EXIT_RE = re.compile(r"\[EXIT (-?\d+)\]")

def _new_job(action: str, targets: list[tuple[Device, list[str]]]) -> str:
    """Register a job with one independent run per target device."""
    job_id = str(uuid.uuid4())
    all_tools: list[str] = []
    for _, ids in targets:
        all_tools += [t for t in ids if t not in all_tools]
    jobs[job_id] = {
        "status": "pending", "action": action, "tool_ids": all_tools,
        "events": [],  # ordered {device, line} / {device, device_status} for SSE
        "devices": {
            d.id: {"id": d.id, "label": d.label, "tool_ids": ids,
                   "status": "pending", "failed": False, "output": []}
            for d, ids in targets
        },
        "_remaining": len(targets), "_lock": threading.Lock(),
    }
    return job_id

def _run_device_job(job_id: str, device: Device, tool_ids: list, catalog: dict, action: str):
    """One device's share of a job. Runs in a thread pool — blocks on subprocess/SSH
    I/O, does not touch the event loop. Devices of the same job run in parallel."""
    job = jobs[job_id]
    run = job["devices"][device.id]

    def emit(line: str):
        run["output"].append(line)
        job["events"].append({"device": device.id, "line": line})

    def set_status(status: str):
        run["status"] = status
        job["events"].append({"device": device.id, "device_status": status})

    try:
        tools_map = flat_tools(catalog)
        set_status("running")
        job["status"] = "running"
        verb = {"update": "Updating", "uninstall": "Removing"}.get(action, "Installing")
        failed = False

        try:
            ensure_connected(device)
            connected = True
        except Exception as e:
            connected = False
            failed = True
            emit(f"[ERROR] Could not connect to {device.label}: {e}\n")

        for tool_id in tool_ids if connected else []:
            tool = tools_map.get(tool_id)
            if not tool:
                emit(f"[SKIP] Unknown tool: {tool_id}\n")
                continue

            emit(f"\n{'='*60}\n")
            emit(f"{verb}: {tool['name']}\n")
            emit(f"{'='*60}\n")

            if action == "update":
                cmd = get_update_cmd(tool, device)
            elif action == "uninstall":
                cmd = get_uninstall_cmd(tool)
            else:
                cmd = get_install_cmd(tool, device)
            emit(f"$ {cmd}\n\n")

            try:
                for line in stream_cmd(cmd, device):
                    emit(line)
                    m = _EXIT_RE.search(line)
                    if m and int(m.group(1)) != 0:
                        failed = True
            except Exception as e:
                failed = True
                emit(f"[ERROR] {e}\n")

        if connected:
            done_msg = {"update": "Update", "uninstall": "Removal"}.get(action, "Installation")
            emit(f"\n[DONE] {done_msg} " + ("finished with errors.\n" if failed else "complete.\n"))
        run["failed"] = failed
        set_status("failed" if failed else "done")
    except Exception as e:  # never leave the job hanging
        run["failed"] = True
        emit(f"[ERROR] {e}\n")
        set_status("failed")
    finally:
        with job["_lock"]:
            job["_remaining"] -= 1
            if job["_remaining"] == 0:
                job["status"] = "done"


def _spawn_job(job_id: str, tool_ids_by_device: dict, devices: list[Device],
               catalog: dict, action: str):
    """Submit one task per target device to the thread pool from an async endpoint."""
    loop = asyncio.get_running_loop()
    for dev in devices:
        loop.run_in_executor(_executor, _run_device_job, job_id, dev,
                             tool_ids_by_device[dev.id], catalog, action)

# ── API Models ────────────────────────────────────────────────────────────────

class TargetMixin(BaseModel):
    """Optional device targeting. Precedence: device_ids > device_id > current
    selection (which falls back to the built-in default device)."""
    device_id: Optional[str] = None
    device_ids: Optional[list[str]] = None

class InstallRequest(TargetMixin):
    tool_ids: list[str]

class UpdateRequest(TargetMixin):
    tool_ids: list[str]

class UpdateAllRequest(TargetMixin):
    pass

class UninstallRequest(TargetMixin):
    tool_ids: list[str]

class SSHConnectRequest(BaseModel):
    host: str = "172.16.0.1"
    user: str = "root"
    port: int = 22
    password: Optional[str] = None
    key_file: Optional[str] = None
    device_id: Optional[str] = None  # connect a registry device instead of the default target

class VNCRequest(BaseModel):
    geometry: str = "1280x800"
    display: int = 1
    device_id: Optional[str] = None

class DeviceIn(BaseModel):
    label: Optional[str] = None
    type: Optional[str] = None  # ssh | local | usb-rndis
    host: Optional[str] = None
    user: Optional[str] = None
    port: Optional[int] = None
    key_file: Optional[str] = None

class DeviceConnectRequest(BaseModel):
    password: Optional[str] = None  # kept in memory for this session only
    key_file: Optional[str] = None

class SelectDevicesRequest(BaseModel):
    device_ids: list[str]

class ProfileIn(BaseModel):
    name: Optional[str] = None
    description: Optional[str] = None
    tool_ids: Optional[list[str]] = None

class ApplyProfileRequest(TargetMixin):
    pass

# ── Device helpers ────────────────────────────────────────────────────────────

def _model_dict(model: BaseModel, **kw) -> dict:
    return model.model_dump(**kw) if hasattr(model, "model_dump") else model.dict(**kw)

def _device_or_404(device_id: Optional[str] = None) -> Device:
    """Single target: explicit id, else the primary device of the current selection."""
    try:
        return registry.get(device_id) if device_id else registry.primary()
    except DeviceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

def _targets_or_404(req: Optional[TargetMixin]) -> list[Device]:
    try:
        return registry.resolve(req.device_id if req else None,
                                req.device_ids if req else None)
    except DeviceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

def _device_view(device: Device, selected: Optional[list[str]] = None) -> dict:
    selected = registry.get_selected_ids() if selected is None else selected
    d = device.to_dict()
    d["connected"] = device_connected(device)
    d["selected"] = device.id in selected
    d["primary"] = bool(selected) and selected[0] == device.id
    return d

def _target_ref(device: Device) -> dict:
    return {"id": device.id, "label": device.label}

def _profile_view(profile: Profile) -> dict:
    d = profile.to_dict()
    d["unknown_tool_ids"] = profiles.unknown_tools(profile)
    return d

def _fallback_host(device: Device) -> str:
    return config.get("host", "172.16.0.1") if device.is_local else device.host

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return index.read_text()
    return "<h1>BakerPi Tool Installer</h1><p>static/index.html not found.</p>"

@app.get("/api/catalog")
async def get_catalog():
    return load_catalog()

@app.get("/api/tools")
async def get_tools(device_id: Optional[str] = None):
    """Returns all tools with their current install status on the target device
    (default: the primary selected device)."""
    device = _device_or_404(device_id)
    catalog = load_catalog()
    tools_map = flat_tools(catalog)
    result = []
    for tool_id, tool in tools_map.items():
        t = dict(tool)
        t["installed"] = check_tool_installed_fast(tool, device)
        result.append(t)
    return result

@app.get("/api/tools/{tool_id}/status")
async def get_tool_status(tool_id: str, device_id: Optional[str] = None):
    device = _device_or_404(device_id)
    catalog = load_catalog()
    tools_map = flat_tools(catalog)
    tool = tools_map.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"tool_id": tool_id, "installed": check_tool_installed_fast(tool, device),
            "device_id": device.id}

def _start_job(action: str, tool_ids: list[str], devices: list[Device]) -> dict:
    catalog = load_catalog()
    by_device = {d.id: list(tool_ids) for d in devices}
    job_id = _new_job(action, [(d, by_device[d.id]) for d in devices])
    _spawn_job(job_id, by_device, devices, catalog, action)
    return {"job_id": job_id, "devices": [_target_ref(d) for d in devices]}

@app.post("/api/install")
async def install_tools(req: InstallRequest):
    if not req.tool_ids:
        raise HTTPException(status_code=400, detail="No tool_ids provided")
    return _start_job("install", req.tool_ids, _targets_or_404(req))

@app.post("/api/update")
async def update_tools(req: UpdateRequest):
    if not req.tool_ids:
        raise HTTPException(status_code=400, detail="No tool_ids provided")
    return _start_job("update", req.tool_ids, _targets_or_404(req))

@app.post("/api/update-all")
async def update_all_installed(req: Optional[UpdateAllRequest] = None):
    """Update every currently-installed tool, per target device, in one job."""
    devices = _targets_or_404(req)
    catalog = load_catalog()
    tools_map = flat_tools(catalog)

    def installed_on(device: Device) -> list[str]:
        try:
            ensure_connected(device)
        except Exception:
            return []
        return [tid for tid, tool in tools_map.items()
                if not tool.get("builtin") and check_tool_installed_fast(tool, device)]

    loop = asyncio.get_running_loop()
    found = await asyncio.gather(*[loop.run_in_executor(_executor, installed_on, d)
                                   for d in devices])
    by_device = {d.id: ids for d, ids in zip(devices, found) if ids}
    skipped = [_target_ref(d) for d in devices if d.id not in by_device]
    if not by_device:
        raise HTTPException(status_code=400, detail="No installed tools found")
    targets = [d for d in devices if d.id in by_device]
    job_id = _new_job("update", [(d, by_device[d.id]) for d in targets])
    _spawn_job(job_id, by_device, targets, catalog, "update")
    return {"job_id": job_id, "tool_ids": jobs[job_id]["tool_ids"],
            "devices": [_target_ref(d) for d in targets], "skipped_devices": skipped}

@app.post("/api/uninstall")
async def uninstall_tools(req: UninstallRequest):
    if not req.tool_ids:
        raise HTTPException(status_code=400, detail="No tool_ids provided")
    catalog = load_catalog()
    tools_map = flat_tools(catalog)
    # Refuse to uninstall builtins
    blocked = [tid for tid in req.tool_ids if tools_map.get(tid, {}).get("builtin")]
    if blocked:
        raise HTTPException(status_code=400, detail=f"Cannot uninstall built-in tools: {blocked}")
    return _start_job("uninstall", req.tool_ids, _targets_or_404(req))

@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """Server-sent events stream for install progress.

    Events: {"device", "line"} log output, {"device", "device_status"} per-device
    status changes, and a final {"done": true, "devices": {id: status}}.
    """
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        sent = 0
        job = jobs[job_id]
        while True:
            finished = job["status"] == "done"  # read before draining: no lost tail events
            events = job["events"]
            while sent < len(events):
                yield f"data: {json.dumps(events[sent])}\n\n"
                sent += 1
            if finished:
                summary = {did: r["status"] for did, r in job["devices"].items()}
                yield f"data: {json.dumps({'done': True, 'devices': summary})}\n\n"
                break
            await asyncio.sleep(0.1)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    j = jobs[job_id]
    runs = list(j["devices"].values())
    if len(runs) == 1:
        output = "".join(runs[0]["output"])
    else:
        output = "".join(f"### {r['label']}\n" + "".join(r["output"]) + "\n" for r in runs)
    return {"job_id": job_id, "status": j["status"], "output": output,
            "tool_ids": j["tool_ids"], "action": j.get("action", "install"),
            "profile": j.get("profile"),
            "devices": [{"id": r["id"], "label": r["label"], "status": r["status"],
                         "tool_ids": r["tool_ids"], "output": "".join(r["output"])}
                        for r in runs]}

@app.get("/api/system")
async def get_system(device_id: Optional[str] = None):
    """Returns Pi Zero system info for the target device (default: primary selected)."""
    device = _device_or_404(device_id)
    who = {"device_id": device.id, "device_label": device.label,
           "device_type": device.type}
    try:
        rc, hostname = run_cmd("hostname", device)
        hostname = hostname.strip() if rc == 0 else "unknown"
        rc, uptime = run_cmd("uptime -p", device)
        uptime = uptime.strip() if rc == 0 else ""
        rc, cpu = run_cmd("grep -m1 'cpu MHz' /proc/cpuinfo | awk '{print $4}'", device)
        cpu = cpu.strip() if rc == 0 else ""
        rc, mem = run_cmd("free -h | awk 'NR==2{print $3\"/\"$2}'", device)
        mem = mem.strip() if rc == 0 else ""
        rc, disk = run_cmd("df -h / | awk 'NR==2{print $3\"/\"$2}'", device)
        disk = disk.strip() if rc == 0 else ""
        rc, arch = run_cmd("uname -m", device)
        arch = arch.strip() if rc == 0 else ""
        rc, os_ver = run_cmd("cat /etc/os-release | grep PRETTY_NAME | cut -d'\"' -f2", device)
        os_ver = os_ver.strip() if rc == 0 else ""
        rc, temp = run_cmd("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{printf \"%.1f°C\", $1/1000}'", device)
        temp = temp.strip() if rc == 0 else ""
    except Exception as e:
        return {"error": str(e), **who}

    return {
        "hostname": hostname, "uptime": uptime, "cpu_mhz": cpu,
        "memory": mem, "disk": disk, "arch": arch, "os": os_ver,
        "temp": temp, "mode": "local" if device.is_local else "ssh",
        "pi_host": device.host if not device.is_local
                   else (config.get("host", "local") if device.id == DEFAULT_DEVICE_ID else "local"),
        **who,
    }

# ── Device registry ───────────────────────────────────────────────────────────
# NOTE: parallel multi-device execution is implemented for install/update/
# uninstall/update-all jobs (one task per selected device). Status views
# (/api/tools, /api/system, VNC) are single-device: they follow the primary
# (first) selected device, or an explicit ?device_id=.

@app.get("/api/devices")
async def list_devices():
    selected = registry.get_selected_ids()
    return {"devices": [_device_view(d, selected) for d in registry.list()],
            "selected": selected, "primary": selected[0]}

@app.post("/api/devices", status_code=201)
async def add_device(req: DeviceIn):
    try:
        dev = registry.add(**_model_dict(req, exclude_none=True))
    except DeviceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _device_view(dev)

@app.get("/api/devices/selected")
async def get_selected_devices():
    selected = registry.get_selected_ids()
    return {"selected": selected, "primary": selected[0],
            "devices": [_device_view(registry.get(i), selected) for i in selected]}

@app.put("/api/devices/selected")
async def set_selected_devices(req: SelectDevicesRequest):
    try:
        selected = registry.set_selected(req.device_ids)
    except DeviceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DeviceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return {"selected": selected, "primary": selected[0],
            "devices": [_device_view(registry.get(i), selected) for i in selected]}

@app.get("/api/devices/{device_id}")
async def get_device(device_id: str):
    return _device_view(_device_or_404(device_id))

@app.put("/api/devices/{device_id}")
async def update_device(device_id: str, req: DeviceIn):
    try:
        before = registry.get(device_id)
        # explicit nulls clear optional fields; omitted keys stay untouched
        dev = registry.update(device_id, **_model_dict(req, exclude_unset=True))
    except DeviceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DeviceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    conn = lambda d: (d.type, d.host, d.user, d.port, d.key_file)
    if conn(before) != conn(dev):
        _drop_client(device_id)  # connection settings changed: reconnect explicitly
    return _device_view(dev)

@app.delete("/api/devices/{device_id}")
async def remove_device(device_id: str):
    try:
        registry.remove(device_id)
    except DeviceNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except DeviceError as e:
        raise HTTPException(status_code=400, detail=str(e))
    _drop_client(device_id)
    _ssh_creds.pop(device_id, None)
    selected = registry.get_selected_ids()
    return {"removed": device_id, "selected": selected, "primary": selected[0]}

@app.post("/api/devices/{device_id}/connect")
def connect_device(device_id: str, req: Optional[DeviceConnectRequest] = None):
    """Open the SSH connection for a registry device. Sync endpoint: runs in the
    thread pool so the 15 s connect timeout cannot block the event loop."""
    device = _device_or_404(device_id)
    if device.is_local:
        return {"connected": True, "device_id": device.id}
    creds = _ssh_creds.get(device.id, {})
    password = req.password if req and req.password else creds.get("password")
    key_file = (req.key_file if req and req.key_file else None) \
        or creds.get("key_file") or device.key_file
    try:
        connect_ssh(device.host, device.user, device.port, password, key_file, device.id)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    return {"connected": True, "device_id": device.id, "host": device.host}

@app.post("/api/ssh/connect")
async def ssh_connect(req: SSHConnectRequest):
    """Legacy single-target connect. Without `device_id` it (re)points the
    built-in default target at host/user/port and connects it."""
    try:
        if req.device_id:
            device = _device_or_404(req.device_id)
            connect_ssh(device.host, device.user, device.port, req.password,
                        req.key_file or device.key_file, device.id)
            return {"connected": True, "host": device.host, "device_id": device.id}
        connect_ssh(req.host, req.user, req.port, req.password, req.key_file)
        config.update(host=req.host, user=req.user, port=req.port,
                      key_file=req.key_file)
        return {"connected": True, "host": req.host}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ssh/status")
async def ssh_status(device_id: Optional[str] = None):
    device = _device_or_404(device_id) if device_id else registry.default_device()
    if device.is_local:
        return {"mode": "local", "connected": True}
    return {"mode": "ssh", "connected": device_connected(device), "host": device.host}

# ── Fleet install profiles ────────────────────────────────────────────────────
# A profile is a named, ordered list of catalog tool ids. Applying one reuses the
# normal install job machinery (_start_job): one task per target device, one log
# tab per device, failures isolated per device.

@app.get("/api/profiles")
async def list_profiles():
    return {"profiles": [_profile_view(p) for p in profiles.list()]}

@app.post("/api/profiles", status_code=201)
async def add_profile(req: ProfileIn):
    try:
        prof = profiles.add(**_model_dict(req, exclude_none=True))
    except ProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _profile_view(prof)

@app.get("/api/profiles/{profile_id}")
async def get_profile(profile_id: str):
    try:
        return _profile_view(profiles.get(profile_id))
    except ProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.put("/api/profiles/{profile_id}")
async def update_profile(profile_id: str, req: ProfileIn):
    try:
        # explicit nulls clear optional fields; omitted keys stay untouched
        prof = profiles.update(profile_id, **_model_dict(req, exclude_unset=True))
    except ProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ProfileError as e:
        raise HTTPException(status_code=400, detail=str(e))
    return _profile_view(prof)

@app.delete("/api/profiles/{profile_id}")
async def remove_profile(profile_id: str):
    try:
        profiles.remove(profile_id)
    except ProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    return {"removed": profile_id}

@app.post("/api/profiles/{profile_id}/apply")
async def apply_profile(profile_id: str, req: Optional[ApplyProfileRequest] = None):
    """Install every tool of a profile on the target device(s).

    Targets resolve exactly like /api/install: ``device_ids`` > ``device_id`` >
    current selection > built-in default device.
    """
    try:
        prof = profiles.get(profile_id)
    except ProfileNotFound as e:
        raise HTTPException(status_code=404, detail=str(e))
    unknown = profiles.unknown_tools(prof)
    if unknown:
        raise HTTPException(
            status_code=400,
            detail=f"Profile {prof.name!r} references tools missing from the catalog: "
                   + ", ".join(unknown))
    devices = _targets_or_404(req)
    started = _start_job("install", list(prof.tool_ids), devices)
    jobs[started["job_id"]]["profile"] = {"id": prof.id, "name": prof.name}
    return {**started, "profile": {"id": prof.id, "name": prof.name},
            "tool_ids": list(prof.tool_ids)}

# ── VNC Service Control ───────────────────────────────────────────────────────

@app.get("/api/services/vnc/status")
async def vnc_status(device_id: Optional[str] = None):
    device = _device_or_404(device_id)
    rc, _ = run_cmd("pgrep -x Xtigervnc 2>/dev/null || pgrep -x Xvnc 2>/dev/null", device)
    running = rc == 0
    host = ""
    if running:
        rc2, ip = run_cmd("hostname -I 2>/dev/null | awk '{print $1}'", device)
        host = ip.strip() if rc2 == 0 else _fallback_host(device)
    return {"running": running, "host": host, "port": 5901, "display": ":1"}

_GEOMETRY_RE = re.compile(r"^\d{2,5}x\d{2,5}$")

@app.post("/api/services/vnc/start")
async def vnc_start(req: VNCRequest):
    # geometry is interpolated into a shell command (possibly run over SSH):
    # accept only WIDTHxHEIGHT digits to prevent command injection
    if not _GEOMETRY_RE.fullmatch(req.geometry):
        raise HTTPException(status_code=400, detail="geometry must look like 1280x800")
    device = _device_or_404(req.device_id)
    run_cmd(f"vncserver -kill :{req.display} 2>/dev/null; true", device)
    rc, out = run_cmd(
        f"vncserver :{req.display} -geometry {req.geometry} -depth 24 -localhost no 2>&1",
        device,
    )
    if rc != 0 and "desktop" not in out.lower() and "starting" not in out.lower():
        raise HTTPException(status_code=500, detail=out.strip() or "vncserver failed to start")
    rc2, ip = run_cmd("hostname -I 2>/dev/null | awk '{print $1}'", device)
    host = ip.strip() if rc2 == 0 else _fallback_host(device)
    port = 5900 + req.display
    return {"started": True, "host": host, "port": port,
            "display": f":{req.display}", "geometry": req.geometry}

@app.post("/api/services/vnc/stop")
async def vnc_stop(device_id: Optional[str] = None):
    device = _device_or_404(device_id)
    run_cmd("vncserver -kill :1 2>/dev/null; pkill -x Xtigervnc 2>/dev/null; pkill -x Xvnc 2>/dev/null; true", device)
    return {"stopped": True}

# ── Startup ───────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="BakerPi Tool Installer")
    parser.add_argument("--mode", choices=["local", "ssh"], default="local",
                        help="local: run on Pi Zero itself | ssh: connect to Pi Zero via SSH")
    parser.add_argument("--host", default="172.16.0.1", help="Pi Zero IP (SSH mode)")
    parser.add_argument("--user", default="root", help="SSH username")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--password", default=None, help="SSH password")
    parser.add_argument("--key-file", default=None, help="SSH private key file")
    parser.add_argument("--devices-file", default=None,
                        help="Device registry JSON (default: per-user config dir, "
                             "or $BAKERPI_DEVICES_FILE)")
    parser.add_argument("--profiles-file", default=None,
                        help="Fleet install profiles JSON (default: per-user config dir, "
                             "or $BAKERPI_PROFILES_FILE)")
    parser.add_argument("--server-port", type=int, default=8080, help="Web UI port")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    return parser.parse_args()

def main():
    args = parse_args()
    config.update(mode=args.mode, host=args.host, user=args.user,
                  port=args.port, key_file=args.key_file)
    if args.devices_file:
        registry.path = Path(args.devices_file).expanduser()
    if args.profiles_file:
        profiles.path = Path(args.profiles_file).expanduser()

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")

    if args.mode == "ssh":
        log.info(f"SSH mode: connecting to {args.user}@{args.host}:{args.port}")
        try:
            connect_ssh(args.host, args.user, args.port, args.password, args.key_file)
            log.info("SSH connected successfully.")
        except Exception as e:
            log.warning(f"SSH connection failed: {e}")
            log.warning("You can connect later via the web UI at /api/ssh/connect")

    if not args.no_browser and args.mode != "local":
        # Open browser after short delay
        def open_browser():
            time.sleep(1.5)
            webbrowser.open(f"http://localhost:{args.server_port}")
        threading.Thread(target=open_browser, daemon=True).start()

    log.info(f"Starting web UI on http://0.0.0.0:{args.server_port}")
    uvicorn.run(app, host="0.0.0.0", port=args.server_port, log_level="warning")

if __name__ == "__main__":
    main()
