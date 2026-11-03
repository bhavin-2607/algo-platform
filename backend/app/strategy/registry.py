"""
Strategy registry — maps engine_class strings (stored in DB) to Python classes.

Built-in engines are registered here. Extra engines are loaded from the
repo strategy/ directory. A file that fails validation is skipped.
"""
from app.strategy.base import BaseStrategy
from typing import Type

from app.strategy.engines.moving_average import MovingAverageCrossover
from app.strategy.engines.opening_range_fib import OpeningRangeFibonacci
from app.strategy.plugins import PLUGIN_ERRORS, discover_plugins

STRATEGY_REGISTRY: dict[str, Type[BaseStrategy]] = {
    "moving_average_crossover": MovingAverageCrossover,
    "opening_range_fibonacci":  OpeningRangeFibonacci,
}


def refresh_plugins() -> dict[str, str]:
    """Reload strategy/*.py. Built-in ids cannot be replaced by a plugin."""
    stale = [key for key, cls in STRATEGY_REGISTRY.items() if cls.__module__.startswith("strategy_plugin_")]
    for key in stale:
        STRATEGY_REGISTRY.pop(key, None)
    for engine_id, cls in discover_plugins().items():
        if engine_id in ("moving_average_crossover", "opening_range_fibonacci"):
            PLUGIN_ERRORS[engine_id] = "Plugin cannot replace a built-in engine"
            continue
        STRATEGY_REGISTRY[engine_id] = cls
    return dict(PLUGIN_ERRORS)


def get_strategy_class(engine_class: str) -> Type[BaseStrategy]:
    cls = STRATEGY_REGISTRY.get(engine_class)
    if not cls:
        raise ValueError(f"Unknown strategy engine: '{engine_class}'")
    return cls


def list_registered() -> list[str]:
    return list(STRATEGY_REGISTRY.keys())


refresh_plugins()
