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

        # 1. Market tick with BUY signal and LTP = 2503 (at entry price 2503)
        with patch.object(engine, "_execute_order", new=AsyncMock(return_value=2503.0)) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=2503.0,
                    signal="BUY",
                    entry_calc=2503.0,
                    sl_calc=2490.0,
                    t1=2550.0,
                    t2=2580.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_awaited_once_with(
                row=row,
                side="BUY",
                price=2503.0,
                order_type="LIMIT",
                db=fake_db,
            )

        # Entered position at entry price
        self.assertEqual(row.status, "IN_POSITION")
        self.assertEqual(row.buy_price, 2503.0)
        self.assertEqual(row.sell_tgt, 2550.0)

        # 2. Market tick reaching target price 2550.0
        with patch.object(engine, "_execute_order", new=AsyncMock(return_value=2550.0)) as mock_exit:
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
            mock_exit.assert_awaited_once_with(
                row=row,
                side="SELL",
                price=2550.0,
                order_type="LIMIT",
                db=fake_db,
            )

        # Trade 1 completed, waiting for return to entry because number_of_trades = 2
        self.assertEqual(row.trades_completed, 1)
        self.assertEqual(row.status, "WAITING_RETURN")
        self.assertEqual(row.pnl, 470.0)  # (2550 - 2503) * 10

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

    def test_buy_only_mode_executes_at_entry_price_and_turns_algo_off(self):
        """Rule 1: BUY ONLY must buy at entry price (not LTP) and turn ALGO OFF, no auto sell."""
        import asyncio
        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="NIFTY 01 DEC 25900 CALL",
            exchange="NFO",
            segment="NSE_FNO",
            is_algo_active=True,
            trade_mode="BUY_ONLY",
            entry_type="FORMULA",
            number_of_trades=1,
            trades_completed=0,
            status="IDLE",
            target_type="TGT1",
            quantity=65,
        )
        fake_db = AsyncMock()

        # Tick 1: LTP (229.65) > entry_calc (208.8) -> must NOT trigger buy
        with patch.object(engine, "_execute_order", new=AsyncMock()) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=229.65,
                    signal="BUY",
                    entry_calc=208.8,
                    sl_calc=200.0,
                    t1=250.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_not_called()
            self.assertEqual(row.status, "IDLE")
            self.assertTrue(row.is_algo_active)

        # Tick 2: LTP touches entry price 208.8 -> must trigger BUY at 208.8 LIMIT and turn ALGO OFF
        with patch.object(engine, "_execute_order", new=AsyncMock(return_value=208.8)) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=208.8,
                    signal="BUY",
                    entry_calc=208.8,
                    sl_calc=200.0,
                    t1=250.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_awaited_once_with(
                row=row,
                side="BUY",
                price=208.8,
                order_type="LIMIT",
                db=fake_db,
            )
            self.assertEqual(row.status, "IN_POSITION")
            self.assertEqual(row.buy_price, 208.8)
            self.assertFalse(row.is_algo_active)  # ALGO OFF

        # Tick 3: Price rises above target 250.0 -> must NEVER auto sell in BUY_ONLY mode
        with patch.object(engine, "_execute_order", new=AsyncMock()) as mock_exit:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=260.0,
                    signal="BUY",
                    entry_calc=208.8,
                    sl_calc=200.0,
                    t1=250.0,
                    db=fake_db,
                )
            )
            mock_exit.assert_not_called()
            self.assertEqual(row.status, "IN_POSITION")

    def test_sell_only_mode_requires_holding_and_sells_at_target_price(self):
        """Rule 2: SELL ONLY requires holding shown in Algo Window and sells at target price."""
        import asyncio
        engine = BsaAlgoEngine.get_instance()
        row_no_holding = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="NIFTY 01 DEC 25900 CALL",
            exchange="NFO",
            segment="NSE_FNO",
            is_algo_active=True,
            trade_mode="SELL_ONLY",
            number_of_trades=1,
            trades_completed=0,
            status="IDLE",
            buy_price=None,
            target_type="CUSTOM",
            custom_target=200.0,
            quantity=65,
        )
        fake_db = AsyncMock()

        # Without holding, tick touching custom_target must NOT sell or transition to IN_POSITION
        with patch.object(engine, "_execute_order", new=AsyncMock()) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row_no_holding,
                    ltp=200.95,
                    signal="BUY",
                    entry_calc=208.8,
                    sl_calc=200.0,
                    t1=250.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_not_called()
            self.assertEqual(row_no_holding.status, "IDLE")

        # Now test with verified holding in Algo Window
        row_with_holding = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="NIFTY 01 DEC 25900 CALL",
            exchange="NFO",
            segment="NSE_FNO",
            is_algo_active=True,
            trade_mode="SELL_ONLY",
            number_of_trades=1,
            trades_completed=0,
            status="IN_POSITION",
            buy_price=208.6,
            target_type="CUSTOM",
            custom_target=210.55,
            quantity=65,
        )

        with patch.object(engine, "_execute_order", new=AsyncMock(return_value=210.55)) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row_with_holding,
                    ltp=210.55,
                    signal="BUY",
                    entry_calc=208.8,
                    sl_calc=200.0,
                    t1=250.0,
                    db=fake_db,
                )
            )
            # Sells at target price 210.55 (LIMIT order), not at arbitrary LTP
            mock_exec.assert_awaited_once_with(
                row=row_with_holding,
                side="SELL",
                price=210.55,
                order_type="LIMIT",
                db=fake_db,
            )
            self.assertEqual(row_with_holding.status, "COMPLETED")
            self.assertFalse(row_with_holding.is_algo_active)  # ALGO OFF
            self.assertEqual(row_with_holding.trades_completed, 1)

    def test_full_cycle_requires_buy_first_before_sell(self):
        """Rule 3: In FULL CYCLE, if BUY is not done it must NEVER initiate SELL."""
        import asyncio
        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="NIFTY 01 DEC 25900 CALL",
            exchange="NFO",
            segment="NSE_FNO",
            is_algo_active=True,
            trade_mode="FULL",
            entry_type="FORMULA",
            number_of_trades=1,
            trades_completed=0,
            status="IDLE",
            target_type="CUSTOM",
            custom_target=200.0,  # custom target closer to LTP
            quantity=65,
        )
        fake_db = AsyncMock()

        # Market is at 200.0 (touches custom_target 200.0), but formula entry is 190.0
        # FULL cycle must NOT initiate SELL! It requires BUY first.
        with patch.object(engine, "_execute_order", new=AsyncMock()) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=200.0,
                    signal="BUY",
                    entry_calc=190.0,
                    sl_calc=185.0,
                    t1=215.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_not_called()
            self.assertEqual(row.status, "IDLE")

        # Now price reaches formula entry 190.0 -> BUY is initiated
        with patch.object(engine, "_execute_order", new=AsyncMock(return_value=190.0)) as mock_buy:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=190.0,
                    signal="BUY",
                    entry_calc=190.0,
                    sl_calc=185.0,
                    t1=215.0,
                    db=fake_db,
                )
            )
            mock_buy.assert_awaited_once_with(
                row=row,
                side="BUY",
                price=190.0,
                order_type="LIMIT",
                db=fake_db,
            )
            self.assertEqual(row.status, "IN_POSITION")

        # After BUY is done, when price reaches custom_target 200.0 -> SELL is initiated
        with patch.object(engine, "_execute_order", new=AsyncMock(return_value=200.0)) as mock_sell:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=200.0,
                    signal="BUY",
                    entry_calc=190.0,
                    sl_calc=185.0,
                    t1=215.0,
                    db=fake_db,
                )
            )
            mock_sell.assert_awaited_once_with(
                row=row,
                side="SELL",
                price=200.0,
                order_type="LIMIT",
                db=fake_db,
            )
            self.assertEqual(row.status, "COMPLETED")
            self.assertFalse(row.is_algo_active)

    def test_sync_dhan_status_closed_position(self):
        """Test Dhan position sync correctly updates closed trades in Algo Window."""
        import asyncio
        engine = BsaAlgoEngine.get_instance()
        user_id = uuid.uuid4()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=user_id,
            symbol="NIFTY 01 DEC 25900 CALL",
            token="47855",
            exchange="NFO",
            segment="NSE_FNO",
            is_algo_active=True,
            trade_mode="FULL",
            status="IN_POSITION",
            buy_price=208.8,
            quantity=65,
            trades_completed=0,
            number_of_trades=1,
        )

        mock_broker_account = MagicMock()
        mock_broker_account.user_id = user_id
        mock_broker_account.is_active = True
        mock_broker_account.paper_trading = False
        mock_broker_account.broker_type = "DHAN"

        mock_adapter = MagicMock()
        mock_adapter.get_positions = AsyncMock(return_value=[{
            "securityId": "47855",
            "tradingSymbol": "NIFTY-Dec2026-25900-CE",
            "positionType": "CLOSED",
            "netQty": 0,
            "buyQty": 65,
            "sellQty": 65,
            "buyAvg": 208.6,
            "sellAvg": 210.55,
            "realizedProfit": 126.75,
        }])
        mock_adapter.get_order_book = AsyncMock(return_value=[])

        fake_db = AsyncMock()
        mock_res1 = MagicMock()
        mock_res1.scalars().all.return_value = [mock_broker_account]
        mock_res2 = MagicMock()
        mock_res2.scalars().all.return_value = [row]
        fake_db.execute.side_effect = [mock_res1, mock_res2]

        with patch("app.services.bsa_algo_engine.get_broker_adapter", return_value=mock_adapter):
            updated = asyncio.run(engine.sync_dhan_status(fake_db, user_id=user_id, force=True))
            self.assertEqual(updated, 1)
            self.assertEqual(row.status, "COMPLETED")
            self.assertFalse(row.is_algo_active)
            self.assertEqual(row.buy_price, 208.6)
            self.assertEqual(row.sell_tgt, 210.55)
            self.assertEqual(row.pnl, 126.75)
            self.assertEqual(row.trades_completed, 1)


if __name__ == "__main__":
    unittest.main()
