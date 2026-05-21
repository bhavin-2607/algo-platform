"""
Strategy registry — maps engine_class strings (stored in DB) to Python classes.
Server-side only — never exposed via API.
"""
from app.strategy.base import BaseStrategy
from typing import Type

from app.strategy.engines.moving_average import MovingAverageCrossover
from app.strategy.engines.opening_range_fib import OpeningRangeFibonacci

STRATEGY_REGISTRY: dict[str, Type[BaseStrategy]] = {
    "moving_average_crossover": MovingAverageCrossover,
    "opening_range_fibonacci":  OpeningRangeFibonacci,
}


def get_strategy_class(engine_class: str) -> Type[BaseStrategy]:
    cls = STRATEGY_REGISTRY.get(engine_class)
    if not cls:
        raise ValueError(f"Unknown strategy engine: '{engine_class}'")
    return cls


def list_registered() -> list[str]:
    return list(STRATEGY_REGISTRY.keys())
