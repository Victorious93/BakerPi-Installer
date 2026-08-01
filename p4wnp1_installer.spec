# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for BakerPi Tool Installer
#
# Build with:
#   pyinstaller p4wnp1_installer.spec --noconfirm
#
# Output: dist/P4wnP1_Installer   (Linux/macOS)
#         dist/P4wnP1_Installer.exe (Windows)

added_files = [
    ("server.py",       "."),
    ("static",          "static"),
    ("tools",           "tools"),
    ("install_scripts", "install_scripts"),
    ("requirements.txt", "."),
]

a = Analysis(
    ["launcher.py"],
    pathex=[],
    binaries=[],
    datas=added_files,
    hiddenimports=[
        "uvicorn.logging",
        "uvicorn.loops",
        "uvicorn.loops.auto",
        "uvicorn.protocols",
        "uvicorn.protocols.http",
        "uvicorn.protocols.http.auto",
        "uvicorn.protocols.websockets",
        "uvicorn.protocols.websockets.auto",
        "uvicorn.lifespan",
        "uvicorn.lifespan.on",
        "fastapi",
        "fastapi.responses",
        "fastapi.staticfiles",
        "starlette",
        "starlette.routing",
        "starlette.responses",
        "anyio",
        "anyio._backends._asyncio",
        "paramiko",
        "paramiko.transport",
        "cryptography",
        # pywebview platform backends (all included so frozen binary works everywhere)
        "webview",
        "webview.util",
        "webview.platforms",
        "webview.platforms.winforms",
        "webview.platforms.edgechromium",
        "webview.platforms.gtk",
        "webview.platforms.cocoa",
    ],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["matplotlib", "numpy", "PIL", "scipy", "pandas"],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="P4wnP1_Installer",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    icon="static/favicon.ico",
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)
