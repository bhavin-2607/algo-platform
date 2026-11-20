import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid
import math

from app.strategy.excel_formula_engine import evaluate_columns_in_order, formula_for_book, evaluate_formula
from app.models.terminal_column import STANDARD_FORMULA_COLUMNS
from app.models.algo_row import BsaAlgoRow
from app.services.bsa_algo_engine import BsaAlgoEngine, is_option_symbol
from app.broker.base import OrderRequest


class TestStandardAlgoAndFormulas(unittest.TestCase):
    def test_standard_column_presets(self):
        """Verify standard batch columns are present with exactly 47 columns in order."""
        self.assertEqual(len(STANDARD_FORMULA_COLUMNS), 47)
        names = [c["name"] for c in STANDARD_FORMULA_COLUMNS]
        expected_start = ["SYMBOL", "TREND", "LTP", "OPEN", "HIGH", "LOW", "P_CLOSE", "GANN", "OHLSIGNAL", "SUPERSIGNAL", "INTRASIGNAL", "ENTRY", "SL", "TGT1", "TGT2", "TGT3", "TGT4", "TGT5"]
        self.assertEqual(names[:len(expected_start)], expected_start)
        self.assertIn("DIFF", names)
        self.assertIn("BT1", names)
        self.assertIn("ST1", names)
        self.assertIn("PP", names)
        self.assertIn("VWAP", names)
        self.assertIn("KD", names)
        self.assertIn("BELOWSELL-ABOVEBUY", names)
        self.assertIn("ABOVEBUY-BELOWSELL", names)
        self.assertIn("POSSIBLE_TGT", names)
        self.assertIn("S1", names)
        self.assertIn("R1", names)

    def test_standard_formula_evaluation(self):
        """Verify that all core standard formulas evaluate correctly against tick data."""
        sample_tick = {
            "open": 2500.0,
            "high": 2550.0,
            "low": 2480.0,
            "close": 2510.0,
            "ltp": 2520.0,
            "volume": 1000000.0,
            "p_close": 2490.0,
            "p_high": 2530.0,
            "p_low": 2470.0,
        }
        res = evaluate_columns_in_order(STANDARD_FORMULA_COLUMNS, sample_tick)

        # 1. TREND: (2530 + 2470 + 2490) / 3 = 2496.67 <= 2520 -> "UP"
        self.assertEqual(res.get("trend"), "UP")

        # 2. GANN: (2550 + 2480) / 2 = 2515.0
        self.assertEqual(res.get("gann"), 2515.0)

        # 3. OHLSIGNAL: open != low and open != high -> ""
        self.assertEqual(res.get("ohlsignal"), "")

        # 4. SUPERSIGNAL: open > p_close (2500 > 2490) and ltp > open (2520 > 2500) -> "BUY"
        self.assertEqual(res.get("supersignal"), "BUY")

        # 5. INTRASIGNAL: ltp > open (2520 > 2500) -> "BUY"
        self.assertEqual(res.get("intrasignal"), "BUY")

        # 6. ENTRY: round((sqrt(2500) + 0.025)^2, 0) = round(50.025^2, 0) = 2503.0
        self.assertEqual(res.get("entry"), 2503.0)

        # 7. SL: 2503 - (2503 * 0.005) = 2490.485 -> 2490.48 or 2490.49
        self.assertAlmostEqual(res.get("sl"), 2490.48, delta=0.05)

        # 13. DIFF: 2530 - 2470 = 60.0
        self.assertEqual(res.get("diff"), 60.0)

        # 14. BT1: (2500 + 0.1) + (60 / 3) = 2520.1
        self.assertEqual(res.get("bt1"), 2520.1)

        # 15. BT2: (2520.1 + 0.1) + (60 / 2) = 2550.2
        self.assertEqual(res.get("bt2"), 2550.2)

        # 19. ST1: (2500 - 0.1) - (60 / 3) = 2479.9
        self.assertEqual(res.get("st1"), 2479.9)

        # 8-12. Targets: INTRASIGNAL is BUY, so TGT1..TGT5 == BT1..BT5
        self.assertEqual(res.get("tgt1"), res.get("bt1"))
        self.assertEqual(res.get("tgt2"), res.get("bt2"))

        # 24. PP: (2530 + 2470 + 2490) / 3 = 2496.67
        self.assertAlmostEqual(res.get("pp"), 2496.67, delta=0.02)

        # 34. R1: 2 * 2496.67 - 2470 = 2523.34
        self.assertAlmostEqual(res.get("r1"), 2523.33, delta=0.1)

        # 33. S1: 2 * 2496.67 - 2530 = 2463.34
        self.assertAlmostEqual(res.get("s1"), 2463.33, delta=0.1)

        # 27. KD: (2520 - 2480) / (2550 - 2480) * 100 = 40 / 70 * 100 = 57.14
        self.assertAlmostEqual(res.get("kd"), 57.14, delta=0.02)

        # 28. BELOWSELL-ABOVEBUY: 2530 - (2530 * 0.001) = 2527.47
        self.assertAlmostEqual(res.get("belowsell_abovebuy"), 2527.47, delta=0.05)

        # 29. ABOVEBUY-BELOWSELL: 2470 + (2470 * 0.001) = 2472.47
        self.assertAlmostEqual(res.get("abovebuy_belowsell"), 2472.47, delta=0.05)

        # 38. VWAPSIGNAL: ltp > vwap
        self.assertIn(res.get("vwapsignal"), ("BUY", "SELL"))

    def test_algo_engine_state_transitions(self):
        """Verify state transitions for Algo Engine: entry, target exit, return to entry."""
        import asyncio
        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="RELIANCE",
            exchange="NSE",
            segment="NSE_EQ",
            is_algo_active=True,
            trade_mode="FULL",
            number_of_trades=2,
            trades_completed=0,
            status="IDLE",
            target_type="TGT1",
            quantity=10,
        )
        fake_db = AsyncMock()

        # 1. Market tick with BUY signal and LTP = 2520
        with patch.object(engine, "_execute_order", new=AsyncMock(return_value=2520.0)):
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=2520.0,
                    signal="BUY",
                    entry_calc=2503.0,
                    sl_calc=2490.0,
                    t1=2550.0,
                    t2=2580.0,
                    db=fake_db,
                )
            )

        # Entered position
        self.assertEqual(row.status, "IN_POSITION")
        self.assertEqual(row.buy_price, 2520.0)
        self.assertEqual(row.sell_tgt, 2550.0)

        # 2. Market tick reaching target price 2550.0
        with patch.object(engine, "_execute_order", new=AsyncMock(return_value=2550.0)):
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=2550.0,
                    signal="BUY",
                    entry_calc=2503.0,
                    sl_calc=2490.0,
                    t1=2550.0,
                    db=fake_db,
                )
            )

        # Trade 1 completed, waiting for return to entry because number_of_trades = 2
        self.assertEqual(row.trades_completed, 1)
        self.assertEqual(row.status, "WAITING_RETURN")
        self.assertEqual(row.pnl, 300.0)  # (2550 - 2520) * 10

        # 3. Price returns to entry price (2503.0) -> transitions back to WAITING_SIGNAL
        asyncio.run(
            engine._process_row(
                row=row,
                ltp=2500.0,
                signal="BUY",
                entry_calc=2503.0,
                sl_calc=2490.0,
                t1=2550.0,
                db=fake_db,
            )
        )
        self.assertEqual(row.status, "WAITING_SIGNAL")


if __name__ == "__main__":
    unittest.main()
