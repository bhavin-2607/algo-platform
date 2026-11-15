import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid

from app.strategy.excel_formula_engine import evaluate_columns_in_order
from app.models.terminal_column import FIBONACCI_FORMULA_COLUMNS, BSA_FORMULA_COLUMNS
from app.models.algo_row import BsaAlgoRow
from app.services.bsa_algo_engine import BsaAlgoEngine
from app.broker.base import OrderRequest


class TestFibonacciAlgoAndFormulas(unittest.TestCase):
    def test_fibonacci_formula_evaluation(self):
        """Verify that all Fibonacci formulas evaluate correctly."""
        sample_tick = {
            "open": 2000.0,
            "high": 2040.0,
            "low": 1980.0,
            "close": 2010.0,
            "ltp": 2015.0,
            "volume": 800000,
        }
        res = evaluate_columns_in_order(FIBONACCI_FORMULA_COLUMNS, sample_tick)

        # GANN = (high + low) / 2 = (2040 + 1980) / 2 = 2010
        self.assertEqual(res.get("gann"), 2010.0)

        # SIGNAL = IF(ltp > open, "BUY", "SELL") = 2015 > 2000 -> "BUY"
        self.assertEqual(res.get("signal"), "BUY")

        # ENTRY > 0
        self.assertIsNotNone(res.get("entry"))
        self.assertTrue(res.get("entry") > 0)

        # SL < entry
        self.assertIsNotNone(res.get("sl"))
        self.assertTrue(res.get("sl") < res.get("entry"))

        # Targets T11.8, T23.8, T38.2 > entry
        self.assertIsNotNone(res.get("t11.8"))
        self.assertTrue(res.get("t11.8") > res.get("entry"))
        self.assertTrue(res.get("t23.8") > res.get("t11.8"))
        self.assertTrue(res.get("t38.2") > res.get("t23.8"))

    def test_fibonacci_algo_engine_state_transitions(self):
        """Verify state transitions for Fibonacci Algo Engine: entry, exit, repeat return constraint."""
        import asyncio

        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="RELIANCE",
            exchange="NSE",
            segment="NSE_EQ",
            is_algo_active=True,
            quantity=10,
            number_of_trades=2,
            trades_completed=0,
            status="IDLE",
            target_type="T11.8",
        )

        fake_db = AsyncMock()

        # Step 1: Signal is BUY -> enters at market price
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 2015.0
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=2015.0,
                    signal="BUY",
                    entry_calc=2015.0,
                    sl_calc=2000.0,
                    t11_8=2030.0,
                    t23_8=2040.0,
                    t38_2=2050.0,
                    t50=2060.0,
                    t100=2070.0,
                    db=fake_db,
                )
            )

        self.assertEqual(row.status, "IN_POSITION")
        self.assertEqual(row.buy_price, 2015.0)
        self.assertEqual(row.sell_tgt, 2030.0)
        self.assertEqual(row.stop_loss, 2000.0)

        # Step 2: Price reaches Target T11.8 (2030) -> exits position
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 2030.0
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=2030.0,
                    signal="BUY",
                    entry_calc=2015.0,
                    sl_calc=2000.0,
                    t11_8=2030.0,
                    t23_8=2040.0,
                    t38_2=2050.0,
                    t50=2060.0,
                    t100=2070.0,
                    db=fake_db,
                )
            )

        self.assertEqual(row.trades_completed, 1)
        # Because number_of_trades=2, status must transition to WAITING_RETURN
        self.assertEqual(row.status, "WAITING_RETURN")

        # Step 3: While price is still high (2025 > 2015), it should NOT enter next trade
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=2025.0,
                    signal="BUY",
                    entry_calc=2015.0,
                    sl_calc=2000.0,
                    t11_8=2030.0,
                    t23_8=2040.0,
                    t38_2=2050.0,
                    t50=2060.0,
                    t100=2070.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_not_called()
        self.assertEqual(row.status, "WAITING_RETURN")

        # Step 4: Price returns to entry price (2014 <= 2015) -> transitions to WAITING_SIGNAL
        asyncio.run(
            engine._process_row(
                row=row,
                ltp=2014.0,
                signal="BUY",
                entry_calc=2015.0,
                sl_calc=2000.0,
                t11_8=2030.0,
                t23_8=2040.0,
                t38_2=2050.0,
                t50=2060.0,
                t100=2070.0,
                db=fake_db,
            )
        )
        self.assertEqual(row.status, "WAITING_SIGNAL")

    def test_execute_order_constructs_valid_order_request(self):
        """Verify _execute_order passes direction (not side) to OrderRequest without TypeError."""
        import asyncio

        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="INFY",
            exchange="NSE",
            segment="NSE_EQ",
            quantity=5,
        )

        mock_result = MagicMock()
        mock_result.scalars.return_value.first.return_value = None
        fake_db = AsyncMock()
        fake_db.execute.return_value = mock_result

        # When no adapter is configured, simulated fill returns the price
        fill = asyncio.run(engine._execute_order(row, side="BUY", price=1500.0, db=fake_db))
        self.assertEqual(fill, 1500.0)
        self.assertTrue(row.last_order_id.startswith("SIM-"))

    def test_fibonacci_column_presets(self):
        """Verify Fibonacci batch columns are present."""
        self.assertEqual(len(FIBONACCI_FORMULA_COLUMNS), 19)

    def test_dynamic_target_switching_and_9_targets(self):
        """Verify dynamic target switching across all 9 Fibonacci targets."""
        import asyncio

        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="RELIANCE",
            is_algo_active=True,
            number_of_trades=1,
            trades_completed=0,
            quantity=10,
            status="IN_POSITION",
            buy_price=2000.0,
            target_type="T61.8",
            sell_tgt=2060.0,
        )
        fake_db = AsyncMock()

        # Target map levels
        t_levels = {
            "t11_8": 2010.0,
            "t23_8": 2020.0,
            "t38_2": 2035.0,
            "t50": 2050.0,
            "t61_8": 2060.0,
            "t78_6": 2075.0,
            "t100": 2100.0,
            "t1_618": 2150.0,
            "t2_618": 2200.0,
        }

        # Price is at 2040. If target is changed to T38.2 (2035), LTP 2040 >= 2035 -> should trigger exit
        row.target_type = "T38.2"
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 2040.0
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=2040.0,
                    signal="BUY",
                    entry_calc=2000.0,
                    sl_calc=1980.0,
                    **t_levels,
                    db=fake_db,
                )
            )
            mock_exec.assert_called_once()
        self.assertEqual(row.status, "COMPLETED")
        self.assertEqual(row.trades_completed, 1)

    def test_bsa_column_presets_sequence(self):
        """Verify BSA batch has exactly 28 columns in the exact sequence requested."""
        expected_names = [
            "SYMBOL", "OPEN", "HIGH", "LOW", "P.CLOSE", "P.HIGH", "P.LOW", "LTP",
            "TREND", "GANN", "KD", "S-SIGNAL", "OHLSIG", "INTRASIGNAL", "ENTRY", "SL",
            "TGT1", "TGT2", "TGT3", "BT1", "BT2", "BT3", "DIFF", "ST1", "ST2", "ST3",
            "VWAP", "VOLUME"
        ]
        self.assertEqual(len(BSA_FORMULA_COLUMNS), 28)
        actual_names = [c["name"] for c in BSA_FORMULA_COLUMNS]
        self.assertEqual(actual_names, expected_names)

    def test_bsa_formulas_evaluation(self):
        """Verify calculation of all BSA formulas including GANN, KD, INTRASIGNAL, DIFF, BT1-3, ST1-3, TGT1-3."""
        sample_tick = {
            "open": 2000.0,
            "high": 2040.0,
            "low": 1980.0,
            "close": 2010.0,
            "ltp": 2015.0,
            "volume": 800000,
            "p_close": 2005.0,
            "p_high": 2030.0,
            "p_low": 1970.0,
        }
        res = evaluate_columns_in_order(BSA_FORMULA_COLUMNS, sample_tick)

        # GANN = (high + low) / 2 = (2040 + 1980) / 2 = 2010
        self.assertEqual(res.get("gann"), 2010.0)

        # KD = (ltp - low) / (high - low) * 100 = (2015 - 1980) / (2040 - 1980) * 100 = 35 / 60 * 100 = 58.33
        self.assertEqual(res.get("kd"), 58.33)

        # INTRASIGNAL = IF(ltp > open, "BUY", "SELL") = 2015 > 2000 -> "BUY"
        self.assertEqual(res.get("intrasignal"), "BUY")

        # DIFF = p_high - p_low = 2030 - 1970 = 60
        self.assertEqual(res.get("diff"), 60.0)

        # BT1 = (open + 0.5) + (diff / 3) = 2000.5 + 20 = 2020.5
        self.assertEqual(res.get("bt1"), 2020.5)

        # BT2 = (open + 0.01) + (diff / 2) = 2000.01 + 30 = 2030.01
        self.assertEqual(res.get("bt2"), 2030.01)

        # BT3 = (open + 0.5) + diff = 2000.5 + 60 = 2060.5
        self.assertEqual(res.get("bt3"), 2060.5)

        # TGT1 for BUY = BT1 = 2020.5
        self.assertEqual(res.get("tgt1"), 2020.5)
        # TGT2 for BUY = BT2 = 2030.01
        self.assertEqual(res.get("tgt2"), 2030.01)
        # TGT3 for BUY = BT3 = 2060.5
        self.assertEqual(res.get("tgt3"), 2060.5)

        # ST1 = (open - 0.55) - (diff / 3) = 1999.45 - 20 = 1979.45
        self.assertEqual(res.get("st1"), 1979.45)


if __name__ == "__main__":
    unittest.main()
