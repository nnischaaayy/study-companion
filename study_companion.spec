# study_companion.spec
# PyInstaller build spec for Study Companion
# Usage: pyinstaller study_companion.spec

import sys
from pathlib import Path

block_cipher = None

# ── Collect all hidden imports PyInstaller misses ─────────────────────────────
hidden_imports = [
    # FastAPI / uvicorn
    "uvicorn.logging",
    "uvicorn.loops",
    "uvicorn.loops.auto",
    "uvicorn.loops.asyncio",
    "uvicorn.protocols",
    "uvicorn.protocols.http",
    "uvicorn.protocols.http.auto",
    "uvicorn.protocols.http.h11_impl",
    "uvicorn.protocols.websockets",
    "uvicorn.protocols.websockets.auto",
    "uvicorn.lifespan",
    "uvicorn.lifespan.on",
    "uvicorn.lifespan.off",
    "fastapi",
    "starlette",
    "starlette.middleware",
    "starlette.middleware.cors",
    "starlette.responses",
    "starlette.routing",
    "anyio",
    "anyio._backends._asyncio",
    "h11",
    # Google Gemini
    "google.generativeai",
    "google.ai.generativelanguage_v1beta",
    "google.api_core",
    "google.auth",
    "google.auth.transport.requests",
    "grpc",
    # PyWebView
    "webview",
    "webview.platforms.winforms",
    "clr",
    # Windows
    "win32gui",
    "win32process",
    "win32con",
    "win32api",
    "pywintypes",
    "psutil",
    # Input
    "pynput",
    "pynput.keyboard",
    "pynput._util",
    "pynput._util.win32",
    # Image / screen
    "PIL",
    "PIL.Image",
    "mss",
    "mss.windows",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=[],
    datas=[
        ("web", "web"),
        ("version.py", "."),
        ("updater.py", "."),
    ],
    hiddenimports=hidden_imports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "matplotlib", "numpy", "pandas", "scipy", "tkinter",
        "PyQt5", "PyQt6", "wx", "gi",
    ],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="StudyCompanion",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,           # compress with UPX if available (smaller file)
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,      # no black terminal window — proper GUI app
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="study_companion.ico",   # app icon
    version=None,
    uac_admin=False,
)
