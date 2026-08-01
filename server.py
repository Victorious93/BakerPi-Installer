#!/usr/bin/env python3
"""
P4wnP1 A.L.O.A. Tool Installer Server
Runs on PC (SSH mode) or on Pi Zero itself (local mode).
Serves a responsive web UI for selecting and installing tools.
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
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

# ── Paths ─────────────────────────────────────────────────────────────────────

BASE_DIR = Path(__file__).parent.resolve()
CATALOG_PATH = BASE_DIR / "tools" / "catalog.json"
SCRIPTS_DIR = BASE_DIR / "install_scripts"
STATIC_DIR = BASE_DIR / "static"

# ── Globals ───────────────────────────────────────────────────────────────────

app = FastAPI(title="P4wnP1 Tool Installer", version="1.0.0")
config: dict = {}
ssh_client: Optional[paramiko.SSHClient] = None
jobs: dict[str, dict] = {}  # job_id → {status, output, tool_ids}
log = logging.getLogger("installer")
_executor = ThreadPoolExecutor(max_workers=4)

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

def run_ssh(cmd: str) -> tuple[int, str]:
    """Execute command over SSH (PC mode)."""
    if not ssh_client:
        raise RuntimeError("SSH not connected")
    _, stdout, stderr = ssh_client.exec_command(cmd, timeout=300)
    rc = stdout.channel.recv_exit_status()
    return rc, stdout.read().decode() + stderr.read().decode()

def stream_ssh(cmd: str):
    """Yield output lines from an SSH command."""
    if not ssh_client:
        yield "[ERROR] SSH not connected\n"
        return
    _, stdout, stderr = ssh_client.exec_command(cmd, get_pty=True, timeout=300)
    for line in stdout:
        yield line
    rc = stdout.channel.recv_exit_status()
    yield f"\n[EXIT {rc}]\n"

def run_cmd(cmd: str) -> tuple[int, str]:
    if config.get("mode") == "local":
        return run_local(cmd)
    return run_ssh(cmd)

def stream_cmd(cmd: str):
    if config.get("mode") == "local":
        yield from stream_local(cmd)
    else:
        yield from stream_ssh(cmd)

# ── Status Check ──────────────────────────────────────────────────────────────

def check_tool_installed(tool: dict) -> bool:
    check = tool.get("check_cmd", "")
    if not check:
        return False
    try:
        rc, _ = run_cmd(check)
        return rc == 0
    except Exception:
        return False

def check_tool_installed_fast(tool: dict) -> bool:
    """Fast check using dpkg for packages, fallback to check_cmd."""
    pkg = tool.get("check_pkg", "")
    if pkg:
        try:
            rc, out = run_cmd(f"dpkg -l {pkg} 2>/dev/null | grep -q '^ii'")
            return rc == 0
        except Exception:
            pass
    return check_tool_installed(tool)

# ── SSH Connection ────────────────────────────────────────────────────────────

def connect_ssh(host: str, user: str, port: int, password: Optional[str], key_file: Optional[str]):
    global ssh_client
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
    client.connect(**kwargs)
    ssh_client = client
    log.info(f"SSH connected to {user}@{host}:{port}")

# ── Install / Update Logic ────────────────────────────────────────────────────

def _script_cmd(script: str, tool_id: str, mode_arg: str = "") -> str:
    """Build the shell command for a given install script, tool, and mode."""
    script_path = f"/usr/local/P4wnP1/tool_installer/install_scripts/{script}"
    local_path = str(SCRIPTS_DIR / script)
    suffix = f" {tool_id}" + (f" {mode_arg}" if mode_arg else "")
    if config.get("mode") == "local":
        return f"bash {local_path}{suffix}"
    return f"bash {script_path}{suffix}"

def get_install_cmd(tool: dict) -> str:
    """Returns the shell command to install a tool."""
    tool_id = tool["id"]
    script = tool.get("install_script", "")

    if tool.get("builtin"):
        return "echo 'Built-in — already available via P4wnP1 service.'"

    if not script:
        pkgs = tool.get("packages", [])
        if pkgs:
            return f"apt-get install -y --no-install-recommends {' '.join(pkgs)}"
        return f"echo 'No install method defined for {tool_id}'"

    return _script_cmd(script, tool_id)

def get_update_cmd(tool: dict) -> str:
    """Returns the shell command to update an already-installed tool."""
    tool_id = tool["id"]

    if tool.get("builtin"):
        return "echo 'Built-in — managed by the P4wnP1 service; no update needed.'"

    # Catalog-provided explicit update command takes priority
    explicit = tool.get("update_cmd", "")
    if explicit:
        return explicit

    script = tool.get("install_script", "")
    if script:
        # Pass "update" as the second argument; scripts handle git pull / pip upgrade
        return _script_cmd(script, tool_id, "update")

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
        return "echo 'Built-in — cannot be uninstalled here; managed by P4wnP1 service.'"

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

def _run_job_sync(job_id: str, tool_ids: list, catalog: dict, action: str):
    """Runs in a thread pool — blocks on subprocess I/O, does not touch the event loop."""
    tools_map = flat_tools(catalog)
    jobs[job_id]["status"] = "running"
    verb = {"update": "Updating", "uninstall": "Removing"}.get(action, "Installing")

    for tool_id in tool_ids:
        tool = tools_map.get(tool_id)
        if not tool:
            jobs[job_id]["output"].append(f"[SKIP] Unknown tool: {tool_id}\n")
            continue

        jobs[job_id]["output"].append(f"\n{'='*60}\n")
        jobs[job_id]["output"].append(f"{verb}: {tool['name']}\n")
        jobs[job_id]["output"].append(f"{'='*60}\n")

        if action == "update":
            cmd = get_update_cmd(tool)
        elif action == "uninstall":
            cmd = get_uninstall_cmd(tool)
        else:
            cmd = get_install_cmd(tool)
        jobs[job_id]["output"].append(f"$ {cmd}\n\n")

        try:
            for line in stream_cmd(cmd):
                jobs[job_id]["output"].append(line)
        except Exception as e:
            jobs[job_id]["output"].append(f"[ERROR] {e}\n")

    done_msg = {"update": "Update", "uninstall": "Removal"}.get(action, "Installation")
    jobs[job_id]["output"].append(f"\n[DONE] {done_msg} complete.\n")
    jobs[job_id]["status"] = "done"


def _spawn_job(job_id: str, tool_ids: list, catalog: dict, action: str):
    """Submit a job to the thread pool from an async endpoint."""
    loop = asyncio.get_running_loop()
    loop.run_in_executor(_executor, _run_job_sync, job_id, tool_ids, catalog, action)

# ── API Models ────────────────────────────────────────────────────────────────

class InstallRequest(BaseModel):
    tool_ids: list[str]

class UpdateRequest(BaseModel):
    tool_ids: list[str]

class UninstallRequest(BaseModel):
    tool_ids: list[str]

class SSHConnectRequest(BaseModel):
    host: str = "172.16.0.1"
    user: str = "root"
    port: int = 22
    password: Optional[str] = None
    key_file: Optional[str] = None

# ── Routes ────────────────────────────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def root():
    index = STATIC_DIR / "index.html"
    if index.exists():
        return index.read_text()
    return "<h1>P4wnP1 Tool Installer</h1><p>static/index.html not found.</p>"

@app.get("/api/catalog")
async def get_catalog():
    return load_catalog()

@app.get("/api/tools")
async def get_tools():
    """Returns all tools with their current install status."""
    catalog = load_catalog()
    tools_map = flat_tools(catalog)
    result = []
    for tool_id, tool in tools_map.items():
        t = dict(tool)
        t["installed"] = check_tool_installed_fast(tool)
        result.append(t)
    return result

@app.get("/api/tools/{tool_id}/status")
async def get_tool_status(tool_id: str):
    catalog = load_catalog()
    tools_map = flat_tools(catalog)
    tool = tools_map.get(tool_id)
    if not tool:
        raise HTTPException(status_code=404, detail="Tool not found")
    return {"tool_id": tool_id, "installed": check_tool_installed_fast(tool)}

@app.post("/api/install")
async def install_tools(req: InstallRequest):
    if not req.tool_ids:
        raise HTTPException(status_code=400, detail="No tool_ids provided")
    job_id = str(uuid.uuid4())
    catalog = load_catalog()
    jobs[job_id] = {"status": "pending", "output": [], "tool_ids": req.tool_ids,
                    "action": "install"}
    _spawn_job(job_id, req.tool_ids, catalog, "install")
    return {"job_id": job_id}

@app.post("/api/update")
async def update_tools(req: UpdateRequest):
    if not req.tool_ids:
        raise HTTPException(status_code=400, detail="No tool_ids provided")
    job_id = str(uuid.uuid4())
    catalog = load_catalog()
    jobs[job_id] = {"status": "pending", "output": [], "tool_ids": req.tool_ids,
                    "action": "update"}
    _spawn_job(job_id, req.tool_ids, catalog, "update")
    return {"job_id": job_id}

@app.post("/api/update-all")
async def update_all_installed():
    """Update every currently-installed tool in one job."""
    catalog = load_catalog()
    tools_map = flat_tools(catalog)
    installed_ids = [
        tid for tid, tool in tools_map.items()
        if not tool.get("builtin") and check_tool_installed_fast(tool)
    ]
    if not installed_ids:
        raise HTTPException(status_code=400, detail="No installed tools found")
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "output": [], "tool_ids": installed_ids,
                    "action": "update"}
    _spawn_job(job_id, installed_ids, catalog, "update")
    return {"job_id": job_id, "tool_ids": installed_ids}

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
    job_id = str(uuid.uuid4())
    jobs[job_id] = {"status": "pending", "output": [], "tool_ids": req.tool_ids,
                    "action": "uninstall"}
    _spawn_job(job_id, req.tool_ids, catalog, "uninstall")
    return {"job_id": job_id}

@app.get("/api/jobs/{job_id}/stream")
async def stream_job(job_id: str):
    """Server-sent events stream for install progress."""
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")

    async def event_generator():
        sent = 0
        while True:
            output = jobs[job_id]["output"]
            while sent < len(output):
                yield f"data: {json.dumps({'line': output[sent]})}\n\n"
                sent += 1
            if jobs[job_id]["status"] == "done":
                yield f"data: {json.dumps({'done': True})}\n\n"
                break
            await asyncio.sleep(0.1)

    return StreamingResponse(event_generator(), media_type="text/event-stream",
                             headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"})

@app.get("/api/jobs/{job_id}")
async def get_job(job_id: str):
    if job_id not in jobs:
        raise HTTPException(status_code=404, detail="Job not found")
    j = jobs[job_id]
    return {"job_id": job_id, "status": j["status"],
            "output": "".join(j["output"]), "tool_ids": j["tool_ids"],
            "action": j.get("action", "install")}

@app.get("/api/system")
async def get_system():
    """Returns Pi Zero system info."""
    try:
        rc, hostname = run_cmd("hostname")
        hostname = hostname.strip() if rc == 0 else "unknown"
        rc, uptime = run_cmd("uptime -p")
        uptime = uptime.strip() if rc == 0 else ""
        rc, cpu = run_cmd("grep -m1 'cpu MHz' /proc/cpuinfo | awk '{print $4}'")
        cpu = cpu.strip() if rc == 0 else ""
        rc, mem = run_cmd("free -h | awk 'NR==2{print $3\"/\"$2}'")
        mem = mem.strip() if rc == 0 else ""
        rc, disk = run_cmd("df -h / | awk 'NR==2{print $3\"/\"$2}'")
        disk = disk.strip() if rc == 0 else ""
        rc, arch = run_cmd("uname -m")
        arch = arch.strip() if rc == 0 else ""
        rc, os_ver = run_cmd("cat /etc/os-release | grep PRETTY_NAME | cut -d'\"' -f2")
        os_ver = os_ver.strip() if rc == 0 else ""
        rc, temp = run_cmd("cat /sys/class/thermal/thermal_zone0/temp 2>/dev/null | awk '{printf \"%.1f°C\", $1/1000}'")
        temp = temp.strip() if rc == 0 else ""
    except Exception as e:
        return {"error": str(e)}

    return {
        "hostname": hostname, "uptime": uptime, "cpu_mhz": cpu,
        "memory": mem, "disk": disk, "arch": arch, "os": os_ver,
        "temp": temp, "mode": config.get("mode"),
        "pi_host": config.get("host", "local"),
    }

@app.post("/api/ssh/connect")
async def ssh_connect(req: SSHConnectRequest):
    try:
        connect_ssh(req.host, req.user, req.port, req.password, req.key_file)
        return {"connected": True, "host": req.host}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/ssh/status")
async def ssh_status():
    if config.get("mode") == "local":
        return {"mode": "local", "connected": True}
    connected = ssh_client is not None and ssh_client.get_transport() is not None \
                and ssh_client.get_transport().is_active()
    return {"mode": "ssh", "connected": connected, "host": config.get("host", "")}

# ── Startup ───────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="P4wnP1 Tool Installer")
    parser.add_argument("--mode", choices=["local", "ssh"], default="local",
                        help="local: run on Pi Zero itself | ssh: connect to Pi Zero via SSH")
    parser.add_argument("--host", default="172.16.0.1", help="Pi Zero IP (SSH mode)")
    parser.add_argument("--user", default="root", help="SSH username")
    parser.add_argument("--port", type=int, default=22, help="SSH port")
    parser.add_argument("--password", default=None, help="SSH password")
    parser.add_argument("--key-file", default=None, help="SSH private key file")
    parser.add_argument("--server-port", type=int, default=8080, help="Web UI port")
    parser.add_argument("--no-browser", action="store_true", help="Don't open browser automatically")
    return parser.parse_args()

def main():
    args = parse_args()
    config["mode"] = args.mode
    config["host"] = args.host

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
        import threading
        threading.Thread(target=open_browser, daemon=True).start()

    log.info(f"Starting web UI on http://0.0.0.0:{args.server_port}")
    uvicorn.run(app, host="0.0.0.0", port=args.server_port, log_level="warning")

if __name__ == "__main__":
    main()
