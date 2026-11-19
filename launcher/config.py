"""Configuration and asset path resolver for Algo Platform Launcher."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Dict, List, Optional


def get_app_root() -> Path:
    """Return application root directory (frozen executable directory or repo root)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent


def get_asset_path(filename: str = "") -> Path:
    """
    Resolve asset path supporting both development source and PyInstaller bundle.
    PyInstaller unpacks data to sys._MEIPASS at runtime.
    """
    if getattr(sys, "frozen", False) and hasattr(sys, "_MEIPASS"):
        base_dir = Path(sys._MEIPASS) / "launcher" / "assets"
    else:
        base_dir = Path(__file__).resolve().parent / "assets"

    if not filename:
        return base_dir
    return base_dir / filename


def get_env_paths() -> List[Path]:
    """Return all target .env file locations (root and backend)."""
    root = get_app_root()
    paths = [root / ".env", root / "backend" / ".env"]
    return [p for p in paths if p.exists() or p.parent.exists()]


def load_env_dict() -> Dict[str, str]:
    """Load all current configuration key-value pairs from .env."""
    env_vars: Dict[str, str] = {}
    for path in get_env_paths():
        if path.is_file():
            try:
                for line in path.read_text(encoding="utf-8").splitlines():
                    stripped = line.strip()
                    if stripped and not stripped.startswith("#") and "=" in stripped:
                        key, val = stripped.split("=", 1)
                        clean_key = key.strip().removeprefix("export ").strip()
                        clean_val = val.strip().strip('"').strip("'")
                        if clean_key:
                            env_vars[clean_key] = clean_val
            except Exception:
                pass
    return env_vars


def update_env_variable(key: str, value: str) -> None:
    """
    Atomically update or append an environment variable in both root and backend .env files.
    Preserves existing comments, order, and formatting.
    """
    clean_key = key.strip().removeprefix("export ").strip()
    formatted_val = f'{clean_key}="{value}"\n'

    for path in get_env_paths():
        lines: List[str] = []
        found = False

        if path.is_file():
            try:
                with open(path, "r", encoding="utf-8") as f:
                    for line in f:
                        stripped = line.strip()
                        if stripped.startswith(f"{clean_key}=") or stripped.startswith(f"export {clean_key}="):
                            lines.append(formatted_val)
                            found = True
                        else:
                            lines.append(line)
            except Exception:
                pass

        if not found:
            if lines and not lines[-1].endswith("\n"):
                lines.append("\n")
            lines.append(formatted_val)

        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.writelines(lines)
        except Exception:
            pass

    # Also update current process environment for immediate effect
    os.environ[clean_key] = str(value)
