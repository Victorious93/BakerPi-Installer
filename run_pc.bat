@echo off
:: Launch BakerPi Tool Installer in PC/SSH mode on Windows.
:: Connects to the Pi Zero via SSH over USB RNDIS (172.16.0.1) and opens
:: the web UI in your browser at http://localhost:8080.
::
:: Usage:
::   run_pc.bat                           defaults: root@172.16.0.1
::   run_pc.bat --password raspberry
::   run_pc.bat --host 192.168.7.1        CDC-ECM hosts
::   run_pc.bat --key-file C:\Users\Me\.ssh\id_rsa
::   run_pc.bat --server-port 9090        change web UI port

setlocal

cd /d "%~dp0"

:: Check Python
python --version >nul 2>&1
if errorlevel 1 (
    echo [!] Python not found. Install from https://www.python.org/downloads/
    pause
    exit /b 1
)

:: Install deps if needed
python -c "import fastapi, uvicorn, paramiko" >nul 2>&1
if errorlevel 1 (
    echo [*] Installing Python dependencies...
    pip install -r requirements.txt --quiet
)

echo [*] Starting BakerPi Tool Installer (SSH/PC mode)...
echo [*] Will open browser at http://localhost:8080
echo [*] Press Ctrl+C to stop.
echo.

python server.py --mode ssh %*
