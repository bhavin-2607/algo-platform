"""Locate project .env files without a machine-specific path."""
from pathlib import Path


def project_root() -> Path:
    # backend/app/core/env_files.py -> repo root
    return Path(__file__).resolve().parents[3]


def env_file_candidates() -> list[Path]:
    root = project_root()
    return [root / ".env", root / "backend" / ".env"]


def existing_env_files() -> list[Path]:
    return [path for path in env_file_candidates() if path.is_file()]
