@echo off
:: Launch BakerPi Tool Installer as a native desktop application (Windows).
:: Opens the full tool UI inside a WebView2 window — no browser needed.
::
:: Usage:
::   run_app.bat                           PC mode: SSH to 172.16.0.1
::   run_app.bat --mode local              on-device mode
::   run_app.bat --host 192.168.7.1        custom Pi IP
::   run_app.bat --password raspberry      SSH password
::
:: Requires: Python 3.8+ and WebView2 Runtime (pre-installed on Windows 10/11)

setlocal
cd /d "%~dp0"

python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python not found. Install from https://www.python.org/downloads/
    pause
    exit /b 1
)

python -c "import fastapi, uvicorn, paramiko, webview" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing Python dependencies...
    pip install -r requirements.txt --quiet
)

echo [*] Starting BakerPi Tool Installer (native desktop app)...
python launcher.py %*
