"""Load strategy engines dropped into the repo strategy/ directory."""
from __future__ import annotations

import importlib.util
import logging
from pathlib import Path
from typing import Type

from app.strategy.base import BaseStrategy

logger = logging.getLogger(__name__)

PLUGIN_ERRORS: dict[str, str] = {}


def plugin_dir() -> Path:
    from app.core.env_files import project_root

    return project_root() / "strategy"


def load_plugin_file(path: Path) -> tuple[str, Type[BaseStrategy]] | None:
    """Import one engine file. Returns (engine_id, class) or None when it is not an engine."""
    spec = importlib.util.spec_from_file_location(f"strategy_plugin_{path.stem}", path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load {path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    found: list[Type[BaseStrategy]] = []
    for value in vars(module).values():
        if isinstance(value, type) and issubclass(value, BaseStrategy) and value is not BaseStrategy:
            found.append(value)
    if not found:
        return None
    if len(found) > 1:
        raise ValueError(f"{path.name} defines more than one strategy class")
    cls = found[0]
    engine_id = getattr(cls, "engine_id", "") or ""
    if not engine_id:
        raise ValueError(f"{cls.__name__} is missing engine_id")
    if not getattr(cls, "version", ""):
        raise ValueError(f"{engine_id} is missing version")
    sample = {"symbol": "RELIANCE", "exchange": "NSE", "quantity": 1, "fast": 9, "slow": 21}
    instance = cls(sample)
    if not instance.validate_params():
        raise ValueError(f"{engine_id} failed validate_params on the sample contract")
    return engine_id, cls


def discover_plugins() -> dict[str, Type[BaseStrategy]]:
    """Scan strategy/*.py. A bad file is recorded and skipped."""
    PLUGIN_ERRORS.clear()
    root = plugin_dir()
    found: dict[str, Type[BaseStrategy]] = {}
    if not root.is_dir():
        return found
    for path in sorted(root.glob("*.py")):
        if path.name.startswith("_"):
            continue
        try:
            loaded = load_plugin_file(path)
        except Exception as exc:
            PLUGIN_ERRORS[path.name] = str(exc)
            logger.warning("Strategy plugin %s rejected: %s", path.name, exc)
            continue
        if loaded is None:
            continue
        engine_id, cls = loaded
        if engine_id in found:
            PLUGIN_ERRORS[path.name] = f"Duplicate engine_id {engine_id}"
            continue
        found[engine_id] = cls
    return found
