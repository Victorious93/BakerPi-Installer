#!/usr/bin/env python3
"""
P4wnP1 Tool Installer — Desktop Launcher
Cross-platform tkinter GUI that starts the FastAPI server and opens the browser.
Bundled into a standalone executable via PyInstaller.
"""

import os
import sys
import json
import socket
import threading
import subprocess
import webbrowser
import tkinter as tk
from tkinter import ttk, messagebox, simpledialog
from pathlib import Path
import time

# ── Resolve base path (works both from source and PyInstaller bundle) ─────────

if getattr(sys, "frozen", False):
    BASE_DIR = Path(sys._MEIPASS)
    APP_DIR = Path(sys.executable).parent
else:
    BASE_DIR = Path(__file__).parent.resolve()
    APP_DIR = BASE_DIR

SERVER_SCRIPT = BASE_DIR / "server.py"
ICON_PATH = BASE_DIR / "static" / "favicon.ico"

# ── Colors ────────────────────────────────────────────────────────────────────

BG = "#0d1117"
SURFACE = "#161b22"
BORDER = "#30363d"
GREEN = "#3fb950"
AMBER = "#d29922"
RED = "#f85149"
TEXT = "#c9d1d9"
MUTED = "#8b949e"
WHITE = "#f0f6fc"

# ── Server process ────────────────────────────────────────────────────────────

server_proc = None
server_thread = None
server_port = 8080


def find_free_port(start=8080):
    for p in range(start, start + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            try:
                s.bind(("127.0.0.1", p))
                return p
            except OSError:
                continue
    return start


def start_server(mode, host, user, port, password, key_file, srv_port, on_line):
    global server_proc
    cmd = [
        sys.executable if not getattr(sys, "frozen", False) else sys.executable,
        str(SERVER_SCRIPT),
        "--mode", mode,
        "--server-port", str(srv_port),
        "--no-browser",
    ]
    if mode == "ssh":
        cmd += ["--host", host, "--user", user, "--port", str(port)]
        if password:
            cmd += ["--password", password]
        if key_file:
            cmd += ["--key-file", key_file]

    env = os.environ.copy()
    # When frozen, make sure bundled libs are found
    if getattr(sys, "frozen", False):
        env["PYTHONPATH"] = str(BASE_DIR)

    server_proc = subprocess.Popen(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        bufsize=1,
        env=env,
    )
    for line in server_proc.stdout:
        on_line(line.rstrip())
    server_proc.wait()
    on_line(f"[Server stopped — exit {server_proc.returncode}]")


def stop_server():
    global server_proc
    if server_proc and server_proc.poll() is None:
        server_proc.terminate()
        try:
            server_proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            server_proc.kill()
    server_proc = None


# ── Main GUI ──────────────────────────────────────────────────────────────────

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("P4wnP1 Tool Installer")
        self.configure(bg=BG)
        self.resizable(True, True)
        self.minsize(560, 420)
        self.geometry("640x520")

        # Try to set icon
        if ICON_PATH.exists():
            try:
                self.iconbitmap(str(ICON_PATH))
            except Exception:
                pass

        self._running = False
        self._port = find_free_port()

        self._build_ui()
        self.protocol("WM_DELETE_WINDOW", self._on_close)

    # ── UI Construction ───────────────────────────────────────────────────────

    def _build_ui(self):
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(2, weight=1)

        # ── Header ────────────────────────────────────────────────────────────
        hdr = tk.Frame(self, bg=SURFACE, bd=0, highlightthickness=1,
                       highlightbackground=BORDER)
        hdr.grid(row=0, column=0, sticky="ew", padx=0, pady=0)

        tk.Label(hdr, text="⬡  P4wnP1 Tool Installer", font=("monospace", 14, "bold"),
                 bg=SURFACE, fg=WHITE, pady=12, padx=16).pack(side="left")

        self._status_dot = tk.Label(hdr, text="●", font=("monospace", 18),
                                    bg=SURFACE, fg=MUTED)
        self._status_dot.pack(side="right", padx=8)
        self._status_lbl = tk.Label(hdr, text="stopped", font=("monospace", 10),
                                    bg=SURFACE, fg=MUTED)
        self._status_lbl.pack(side="right", padx=0)

        # ── Mode / Connection ─────────────────────────────────────────────────
        cfg = tk.Frame(self, bg=BG, pady=10, padx=14)
        cfg.grid(row=1, column=0, sticky="ew")
        cfg.grid_columnconfigure(1, weight=1)

        tk.Label(cfg, text="Mode:", bg=BG, fg=MUTED,
                 font=("monospace", 10)).grid(row=0, column=0, sticky="w", padx=(0, 8))

        self._mode = tk.StringVar(value="ssh")
        mode_frame = tk.Frame(cfg, bg=BG)
        mode_frame.grid(row=0, column=1, sticky="w")
        for val, lbl in [("ssh", "SSH / PC mode"), ("local", "On-device mode")]:
            tk.Radiobutton(mode_frame, text=lbl, variable=self._mode, value=val,
                           bg=BG, fg=TEXT, selectcolor=SURFACE,
                           activebackground=BG, activeforeground=WHITE,
                           font=("monospace", 10),
                           command=self._on_mode_change).pack(side="left", padx=8)

        # SSH fields
        self._ssh_frame = tk.Frame(cfg, bg=BG)
        self._ssh_frame.grid(row=1, column=0, columnspan=3, sticky="ew", pady=(6, 0))
        self._ssh_frame.grid_columnconfigure(1, weight=1)

        fields = [
            ("Host:", "172.16.0.1"),
            ("User:", "root"),
            ("Port:", "22"),
            ("Password:", ""),
            ("Key file:", ""),
        ]
        self._ssh_vars = {}
        for i, (label, default) in enumerate(fields):
            key = label.strip(":").lower().replace(" ", "_")
            tk.Label(self._ssh_frame, text=label, bg=BG, fg=MUTED,
                     font=("monospace", 9), width=9, anchor="e"
                     ).grid(row=i, column=0, sticky="e", padx=(0, 6), pady=1)
            var = tk.StringVar(value=default)
            show = "*" if key == "password" else ""
            ent = tk.Entry(self._ssh_frame, textvariable=var, bg=SURFACE, fg=TEXT,
                           insertbackground=TEXT, relief="flat", bd=4, show=show,
                           font=("monospace", 10))
            ent.grid(row=i, column=1, sticky="ew", pady=1)
            self._ssh_vars[key] = var

        # Port row
        port_row = tk.Frame(cfg, bg=BG)
        port_row.grid(row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0))
        tk.Label(port_row, text="Web UI port:", bg=BG, fg=MUTED,
                 font=("monospace", 9)).pack(side="left")
        self._port_var = tk.StringVar(value=str(self._port))
        tk.Entry(port_row, textvariable=self._port_var, bg=SURFACE, fg=TEXT,
                 insertbackground=TEXT, relief="flat", bd=4, width=6,
                 font=("monospace", 10)).pack(side="left", padx=6)

        # Buttons
        btn_row = tk.Frame(cfg, bg=BG)
        btn_row.grid(row=3, column=0, columnspan=3, sticky="ew", pady=(10, 0))

        self._start_btn = tk.Button(
            btn_row, text="▶  Start Server", command=self._toggle,
            bg=GREEN, fg="#000", font=("monospace", 11, "bold"),
            relief="flat", padx=18, pady=6, cursor="hand2",
            activebackground="#2ea043", activeforeground="#000",
        )
        self._start_btn.pack(side="left")

        self._open_btn = tk.Button(
            btn_row, text="⧉  Open Browser", command=self._open_browser,
            bg=SURFACE, fg=TEXT, font=("monospace", 11),
            relief="flat", padx=14, pady=6, cursor="hand2",
            activebackground=BORDER, activeforeground=WHITE,
            state="disabled",
        )
        self._open_btn.pack(side="left", padx=8)

        self._url_lbl = tk.Label(btn_row, text="", bg=BG, fg=MUTED,
                                  font=("monospace", 9))
        self._url_lbl.pack(side="left")

        # ── Log output ────────────────────────────────────────────────────────
        log_frame = tk.Frame(self, bg=BG, padx=14, pady=0)
        log_frame.grid(row=2, column=0, sticky="nsew")
        log_frame.grid_rowconfigure(1, weight=1)
        log_frame.grid_columnconfigure(0, weight=1)

        tk.Label(log_frame, text="Server log", bg=BG, fg=MUTED,
                 font=("monospace", 9), anchor="w").grid(row=0, column=0, sticky="w")

        self._log = tk.Text(
            log_frame, bg=SURFACE, fg=TEXT, font=("monospace", 9),
            relief="flat", bd=0, wrap="word", state="disabled",
            highlightthickness=1, highlightbackground=BORDER,
        )
        self._log.grid(row=1, column=0, sticky="nsew", pady=(4, 14))
        self._log.tag_config("green", foreground=GREEN)
        self._log.tag_config("amber", foreground=AMBER)
        self._log.tag_config("red", foreground=RED)
        self._log.tag_config("muted", foreground=MUTED)

        sb = tk.Scrollbar(log_frame, command=self._log.yview, bg=SURFACE,
                          troughcolor=BG, bd=0, relief="flat")
        sb.grid(row=1, column=1, sticky="ns", pady=(4, 14))
        self._log["yscrollcommand"] = sb.set

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _on_mode_change(self):
        state = "normal" if self._mode.get() == "ssh" else "disabled"
        for child in self._ssh_frame.winfo_children():
            try:
                child.configure(state=state)
            except tk.TclError:
                pass

    def _toggle(self):
        if self._running:
            self._stop()
        else:
            self._start()

    def _start(self):
        try:
            self._port = int(self._port_var.get())
        except ValueError:
            self._port = 8080

        mode = self._mode.get()
        host = self._ssh_vars["host"].get()
        user = self._ssh_vars["user"].get()
        try:
            port = int(self._ssh_vars["port"].get())
        except ValueError:
            port = 22
        password = self._ssh_vars["password"].get() or None
        key_file = self._ssh_vars["key_file"].get() or None

        self._running = True
        self._set_status("starting…", AMBER)
        self._start_btn.config(text="■  Stop Server", bg=RED,
                               activebackground="#b91c1c")
        self._open_btn.config(state="disabled")
        self._log_clear()

        def run():
            start_server(mode, host, user, port, password, key_file,
                         self._port, self._on_log_line)
            self.after(0, self._on_server_done)

        self._srv_thread = threading.Thread(target=run, daemon=True)
        self._srv_thread.start()

        # Poll until server is up
        self.after(1200, self._check_up)

    def _check_up(self):
        if not self._running:
            return
        try:
            with socket.create_connection(("127.0.0.1", self._port), timeout=0.5):
                self._set_status(f"running  :  port {self._port}", GREEN)
                url = f"http://localhost:{self._port}"
                self._url_lbl.config(text=url, fg=GREEN)
                self._open_btn.config(state="normal")
                return
        except OSError:
            pass
        self.after(600, self._check_up)

    def _stop(self):
        self._running = False
        stop_server()
        self._start_btn.config(text="▶  Start Server", bg=GREEN,
                               activebackground="#2ea043", fg="#000")
        self._open_btn.config(state="disabled")
        self._url_lbl.config(text="")
        self._set_status("stopped", MUTED)

    def _on_server_done(self):
        if self._running:
            self._running = False
            self._start_btn.config(text="▶  Start Server", bg=GREEN,
                                   activebackground="#2ea043", fg="#000")
            self._open_btn.config(state="disabled")
            self._url_lbl.config(text="")
            self._set_status("stopped", MUTED)

    def _open_browser(self):
        webbrowser.open(f"http://localhost:{self._port}")

    def _set_status(self, text, color):
        self._status_lbl.config(text=text, fg=color)
        self._status_dot.config(fg=color)

    def _on_log_line(self, line):
        self.after(0, lambda: self._log_append(line))

    def _log_append(self, line):
        self._log.config(state="normal")
        tag = "green" if "INFO" in line or "started" in line.lower() else \
              "red"   if "ERROR" in line or "error" in line.lower() else \
              "amber" if "WARNING" in line or "warn" in line.lower() else \
              "muted" if not line.strip() else ""
        self._log.insert("end", line + "\n", tag)
        self._log.see("end")
        self._log.config(state="disabled")

    def _log_clear(self):
        self._log.config(state="normal")
        self._log.delete("1.0", "end")
        self._log.config(state="disabled")

    def _on_close(self):
        if self._running:
            stop_server()
        self.destroy()


# ── Entry point ───────────────────────────────────────────────────────────────

def main():
    app = App()
    app.mainloop()


if __name__ == "__main__":
    main()
