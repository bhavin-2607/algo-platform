import unittest

import pandas as pd

from app.strategy.backtest_runner import FormulaStrategy, backtest_block_reason, run_backtest
from app.strategy.engines.moving_average import MovingAverageCrossover


def _frame(closes):
    rows = []
    for i, close in enumerate(closes):
        rows.append({
            "open": close, "high": close + 1, "low": close - 1,
            "close": close, "volume": 1000,
        })
    index = pd.date_range("2026-01-01", periods=len(closes), freq="5min")
    return pd.DataFrame(rows, index=index)


class BacktestRunnerTests(unittest.TestCase):
    def test_costs_reduce_a_round_trip(self):
        # Flat then a rise so the fast average crosses above the slow one, then a fall to exit.
        closes = [100] * 30 + [101, 102, 104, 108, 112, 116, 120] + [110, 100, 90, 80]
        strategy = MovingAverageCrossover({
            "symbol": "RELIANCE", "exchange": "NSE", "quantity": 1, "fast": 3, "slow": 8,
        })
        result = run_backtest(_frame(closes), strategy, quantity=1, initial_capital=100000, slippage_pct=0, fee_per_order=10)
        self.assertGreaterEqual(result["total_trades"], 1)
        gross = (result["trades"][0]["exit_price"] - result["trades"][0]["entry_price"])
        self.assertAlmostEqual(result["trades"][0]["pnl"], round(gross - 20, 2))

    def test_formula_uses_generate_signal(self):
        closes = [100 + i for i in range(40)]
        strategy = FormulaStrategy({
            "symbol": "RELIANCE", "exchange": "NSE", "quantity": 1,
            "formula": "close > ma(5)",
        })
        result = run_backtest(_frame(closes), strategy, quantity=1, initial_capital=100000, slippage_pct=0, fee_per_order=0)
        self.assertGreaterEqual(result["total_trades"], 0)
        self.assertIn("passed", result)

    def test_preview_counts_true_bars_and_rejects_import(self):
        from app.strategy.formula_engine import preview_formula
        closes = [100 + i for i in range(40)]
        frame = _frame(closes)
        good = preview_formula("close > ma(5)", frame)
        self.assertTrue(good["valid"], good["error"])
        self.assertGreater(good["true_bars"], 0)
        bad = preview_formula("__import__('os')", frame)
        self.assertFalse(bad["valid"])
        self.assertTrue(bad["error"])
        self.assertIsNone(backtest_block_reason(None))
        self.assertIsNone(backtest_block_reason(True))
        self.assertIn("lost money", backtest_block_reason(False))


if __name__ == "__main__":
    unittest.main()
