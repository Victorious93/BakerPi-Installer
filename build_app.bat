@echo off
:: Build BakerPi Tool Installer as a standalone Windows executable.
:: Output: dist\P4wnP1_Installer.exe
::
:: Requirements: Python 3.8+ in PATH

setlocal
cd /d "%~dp0"

echo [*] Installing dependencies...
pip install -r requirements.txt --quiet
pip install pyinstaller --quiet

echo [*] Building executable...
pyinstaller p4wnp1_installer.spec --clean --noconfirm

echo.
echo [OK] Build complete: dist\P4wnP1_Installer.exe
echo      You can now run the Inno Setup compiler on installer.iss
echo      to create a proper Windows installer package.
echo.
pause
