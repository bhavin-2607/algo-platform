import unittest

from app.broker.order_ops import client_order_id_for
from app.core.config import settings
from app.core.trading_mode import synthetic_blocked
from app.strategy.excel_formula_engine import validate_formula_excel
from app.strategy.formula_engine import validate_formula
from app.strategy.safe_expr import FormulaError, evaluate_expression


class SafeExprTests(unittest.TestCase):
    def test_arithmetic_and_calls(self):
        value = evaluate_expression("ma(20) > 10 and close < 30", {
            "ma": lambda period: period,
            "close": 21,
        })
        self.assertTrue(value)

    def test_rejects_attribute_access(self):
        with self.assertRaises(FormulaError):
            evaluate_expression("os.system('id')", {})

    def test_rejects_unknown_call(self):
        with self.assertRaises(FormulaError):
            evaluate_expression("__import__('os')", {})

    def test_rejects_lambda(self):
        with self.assertRaises(FormulaError):
            evaluate_expression("(lambda: 1)()", {})

    def test_rejects_huge_power(self):
        with self.assertRaises(FormulaError):
            evaluate_expression("2 ** 99", {})

    def test_formula_engine_accepts_indicator_rule(self):
        ok, err = validate_formula("close > ma(20) AND rsi(14) < 70")
        self.assertTrue(ok, err)

    def test_formula_engine_rejects_import(self):
        ok, err = validate_formula("__import__('os').system('id')")
        self.assertFalse(ok)
        self.assertTrue(err)

    def test_excel_if(self):
        ok, msg = validate_formula_excel('=IF(ltp>open,"UP","DOWN")')
        self.assertTrue(ok, msg)
        self.assertIn("UP", msg)

    def test_excel_rejects_import(self):
        ok, msg = validate_formula_excel("=__import__('os')")
        self.assertFalse(ok)
        self.assertTrue(msg)


class TradingGateTests(unittest.TestCase):
    def test_synthetic_blocked_follows_live_flag(self):
        previous = settings.LIVE_TRADING_ENABLED
        try:
            settings.LIVE_TRADING_ENABLED = False
            self.assertFalse(synthetic_blocked())
            settings.LIVE_TRADING_ENABLED = True
            self.assertTrue(synthetic_blocked())
        finally:
            settings.LIVE_TRADING_ENABLED = previous

    def test_client_order_id_is_stable_and_short(self):
        first = client_order_id_for("map", "2026-11-03T09:20", "RELIANCE", "BUY")
        second = client_order_id_for("map", "2026-11-03T09:20", "RELIANCE", "BUY")
        other = client_order_id_for("map", "2026-11-03T09:25", "RELIANCE", "BUY")
        self.assertEqual(first, second)
        self.assertNotEqual(first, other)
        self.assertLessEqual(len(first), 30)


if __name__ == "__main__":
    unittest.main()
