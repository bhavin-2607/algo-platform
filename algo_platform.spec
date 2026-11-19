# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller build specification for Algo Platform Standalone Single-File Executable."""

import os
import sys
from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None
project_root = Path.cwd()

# Ensure backend directory is in sys.path during spec evaluation
backend_path = str(project_root / "backend")
if backend_path not in sys.path:
    sys.path.insert(0, backend_path)

# 1. Collect CustomTkinter assets
ctk_datas = []
try:
    ctk_datas = collect_data_files("customtkinter")
except Exception:
    pass

# 2. Project asset files and pre-built frontend distribution
datas = [
    ("launcher/assets", "launcher/assets"),
    ("backend/app/market/instruments.csv", "app/market"),
    ("backend/app", "app"),
]

# Include production frontend build if present
frontend_dist = project_root / "frontend" / "dist"
if frontend_dist.exists():
    datas.append(("frontend/dist", "frontend/dist"))

datas += ctk_datas

# 3. Explicit hidden imports for FastAPI, Uvicorn, Celery, and GUI
hiddenimports = [
    "customtkinter",
    "pystray",
    "PIL",
    "PIL.Image",
    "PIL.ImageDraw",
    "psutil",
    "dhanhq",
    "dotenv",
    "asyncpg",
    "passlib",
    "passlib.handlers",
    "passlib.handlers.bcrypt",
    "bcrypt",
    "jose",
    "jwt",
    "pyotp",
    "websockets",
    "prometheus_fastapi_instrumentator",
]

for pkg in ["app", "launcher", "uvicorn", "celery", "kombu", "fastapi", "sqlalchemy"]:
    try:
        hiddenimports += collect_submodules(pkg)
    except Exception:
        pass

if sys.platform == "win32":
    hiddenimports += [
        "pystray._win32",
        "ctypes",
        "ctypes.wintypes",
    ]
elif sys.platform == "darwin":
    hiddenimports += [
        "pystray._darwin",
        "AppKit",
        "Cocoa",
        "Quartz",
    ]

a = Analysis(
    ["desktop_launcher.py"],
    pathex=[str(project_root), str(project_root / "backend")],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["unittest.test", "pytest"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

icon_file = (project_root / "launcher" / "assets" / "app_icon.ico").resolve()

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="AlgoPlatformLauncher",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,  # Windowed GUI mode - no external CMD prompt
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=str(icon_file) if icon_file.exists() else None,
)
