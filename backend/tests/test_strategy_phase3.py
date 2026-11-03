import unittest

from app.strategy.exits import live_start_block_reason, protective_prices, trail_stop
from app.strategy.registry import get_strategy_class, refresh_plugins


class ExitHelperTests(unittest.TestCase):
    def test_long_percents(self):
        sl, target = protective_prices("BUY", 100, sl_pct=1, target_pct=2)
        self.assertEqual((sl, target), (99.0, 102.0))

    def test_short_trail_only_moves_in_favor(self):
        peak, new_sl = trail_stop("SELL", 99, 100, 101, 1)
        self.assertEqual(peak, 99)
        self.assertEqual(new_sl, 99.99)
        peak, unchanged = trail_stop("SELL", 100, 99, 99.99, 1)
        self.assertIsNone(unchanged)


class LiveGateTests(unittest.TestCase):
    def test_paper_skips_the_live_flag(self):
        self.assertIsNone(live_start_block_reason(
            paper=True, live_enabled=False, catalogue_version="1",
            code_version="1", pinned_version=None, params_ok=True,
        ))

    def test_live_requires_enable_and_matching_version(self):
        self.assertIn("not enabled", live_start_block_reason(
            paper=False, live_enabled=False, catalogue_version="1",
            code_version="1", pinned_version="1", params_ok=True,
        ))
        self.assertIn("pinned", live_start_block_reason(
            paper=False, live_enabled=True, catalogue_version="2",
            code_version="2", pinned_version="1", params_ok=True,
        ))


class PluginTests(unittest.TestCase):
    def test_hold_flat_plugin_registers(self):
        errors = refresh_plugins()
        self.assertNotIn("hold_flat.py", errors)
        cls = get_strategy_class("hold_flat")
        self.assertEqual(cls.version, "1")
        self.assertIsNone(cls({"symbol": "RELIANCE", "exchange": "NSE", "quantity": 1}).generate_signal(None))


if __name__ == "__main__":
    unittest.main()
