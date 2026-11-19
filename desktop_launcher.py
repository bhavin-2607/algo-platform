#!/usr/bin/env python3
"""Algo Platform - Native Standalone Desktop Executable Launcher."""

import os
import subprocess
import sys

root_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(root_dir, "backend")

if backend_dir not in sys.path:
    sys.path.insert(0, backend_dir)
if root_dir not in sys.path:
    sys.path.insert(0, root_dir)


def _ensure_runtime_environment():
    """Ensure required GUI and backend dependencies are importable; re-exec into backend venv if needed."""
    try:
        import customtkinter
        return
    except ImportError:
        pass

    # Search candidates for a virtual environment that has the required dependencies
    candidates = [
        os.path.join(backend_dir, ".venv", "bin", "python"),
        os.path.join(backend_dir, ".venv", "Scripts", "python.exe"),
        os.path.join(root_dir, ".venv", "bin", "python"),
        os.path.join(root_dir, ".venv", "Scripts", "python.exe"),
    ]

    current_exe = os.path.realpath(sys.executable)
    for cand in candidates:
        if os.path.isfile(cand) and os.path.realpath(cand) != current_exe:
            try:
                ret = subprocess.run(
                    [cand, "-c", "import customtkinter"],
                    stdout=subprocess.DEVNULL,
                    stderr=subprocess.DEVNULL,
                    timeout=5,
                )
                if ret.returncode == 0:
                    # Seamlessly re-exec using the configured environment
                    os.execv(cand, [cand] + sys.argv)
            except Exception:
                continue

    # If no candidate environment has customtkinter, provide clear diagnostics
    print("[ERROR] Required GUI package 'customtkinter' is missing.")
    print("Please install requirements using:")
    print("  pip install customtkinter pystray Pillow psutil pyinstaller")
    print("Or launch using the project backend environment:")
    print("  ./backend/.venv/bin/python desktop_launcher.py (macOS/Linux)")
    print("  backend\\venv\\Scripts\\python.exe desktop_launcher.py (Windows)")
    sys.exit(1)


_ensure_runtime_environment()

from launcher.app import main

if __name__ == "__main__":
    main()
