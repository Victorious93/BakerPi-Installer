#!/usr/bin/env python3
"""
BakerPi Tool Installer — native desktop application.

Runs the FastAPI/uvicorn server in-process (daemon thread) and shows the
full web UI inside a native desktop window via pywebview.  No browser needed.

Usage (from source):
    python launcher.py                          # on-device / local mode
    python launcher.py --mode ssh --host 172.16.0.1 --user root

The standalone binary (built by PyInstaller) works the same way.
"""

import sys
import os
import socket
import time
import threading
import argparse
from pathlib import Path

# ── Resolve paths (source tree or PyInstaller frozen bundle) ──────────────────

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
else:
    BASE_DIR = Path(__file__).parent.resolve()

sys.path.insert(0, str(BASE_DIR))

# ── Deferred imports (after path is set so server.py is importable) ───────────

import uvicorn       # noqa: E402
import webview      # noqa: E402

# ── Port helpers ──────────────────────────────────────────────────────────────

def find_free_port(start: int = 8080) -> int:
    for p in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def wait_for_port(port: int, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.3):
                return True
        except OSError:
            time.sleep(0.2)
    return False


# ── Loading splash (displayed while uvicorn starts) ───────────────────────────

LOADING_HTML = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0d1117;
    color: #e6edf3;
    font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    height: 100vh;
    gap: 20px;
    user-select: none;
  }
  .logo { width: 88px; height: 88px; border-radius: 16px; }
  h1 { font-size: 20px; font-weight: 600; color: #58a6ff; letter-spacing: -0.3px; }
  p  { font-size: 13px; color: #8b949e; }
  .spinner {
    width: 32px; height: 32px;
    border: 3px solid #30363d;
    border-top-color: #58a6ff;
    border-radius: 50%;
    animation: spin 0.75s linear infinite;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
</style>
</head>
<body>
  <div class="spinner"></div>
  <h1>BakerPi Tool Installer</h1>
  <p>Starting server — please wait…</p>
</body>
</html>"""

ERROR_HTML = """<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8">
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  body {
    background: #0d1117; color: #f85149;
    font-family: monospace; font-size: 14px;
    display: flex; align-items: center; justify-content: center;
    height: 100vh; text-align: center; flex-direction: column; gap: 12px;
  }
  p { color: #8b949e; font-size: 12px; }
</style>
</head>
<body>
  <span>Server failed to start.</span>
  <p>Check that nothing else is using port 8080, then relaunch the app.</p>
</body>
</html>"""


# ── Navigate once server is ready ─────────────────────────────────────────────

def _navigate(window: webview.Window, port: int) -> None:
    """Called by webview in a thread after the GUI loop starts."""
    if wait_for_port(port):
        window.load_url(f"http://127.0.0.1:{port}")
    else:
        window.load_html(ERROR_HTML)


# ── Entry point ───────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="BakerPi Tool Installer")
    parser.add_argument("--mode", choices=["local", "ssh"], default="local",
                        help="local: on-device | ssh: connect to Pi Zero via SSH")
    parser.add_argument("--host",        default="172.16.0.1")
    parser.add_argument("--user",        default="root")
    parser.add_argument("--port",        type=int, default=22)
    parser.add_argument("--password",    default=None)
    parser.add_argument("--key-file",    default=None, dest="key_file")
    parser.add_argument("--server-port", type=int,    default=0, dest="server_port",
                        help="Web UI port (0 = pick automatically)")
    args = parser.parse_args()

    srv_port = args.server_port or find_free_port()

    # Configure and optionally pre-connect the backend
    import server as srv
    srv.config["mode"] = args.mode
    srv.config["host"] = args.host

    if args.mode == "ssh":
        try:
            srv.connect_ssh(args.host, args.user, args.port,
                            args.password, args.key_file)
        except Exception:
            pass  # user can connect via the SSH panel inside the UI

    # Start uvicorn in a daemon thread (dies with the process)
    threading.Thread(
        target=uvicorn.run,
        kwargs=dict(app=srv.app, host="127.0.0.1", port=srv_port, log_level="warning"),
        daemon=True,
    ).start()

    # Create the native window — shows loading splash right away
    window = webview.create_window(
        title="BakerPi Tool Installer",
        html=LOADING_HTML,
        width=1280,
        height=820,
        min_size=(880, 600),
    )

    icon = str(BASE_DIR / "static" / "bakerpi-logo-256.png")
    webview.start(
        func=_navigate,
        args=(window, srv_port),
        icon=icon if os.path.exists(icon) else None,
    )


if __name__ == "__main__":
    main()
