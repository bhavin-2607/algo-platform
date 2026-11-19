import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid

from app.strategy.excel_formula_engine import evaluate_columns_in_order, formula_for_book
from app.models.terminal_column import FIBONACCI_FORMULA_COLUMNS
from app.models.algo_row import BsaAlgoRow
from app.services.bsa_algo_engine import BsaAlgoEngine, is_option_symbol
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

    def test_options_target_scaling_and_algo_matching(self):
        """
        Verify that option contracts (such as AUBANK 23 NOV 950 CALL) scale targets
        properly (100x equity percentage), yielding exact matches between Watchlist and Algo Window.
        """
        # Symbol detection
        self.assertTrue(is_option_symbol("AUBANK 23 NOV 950 CALL"))
        self.assertTrue(is_option_symbol("NIFTY 17 NOV 25300 CALL"))
        self.assertTrue(is_option_symbol("NIFTY 17 NOV 25300 PUT"))
        self.assertTrue(is_option_symbol("BHARTIARTL 23 NOV 2200 CALL"))
        self.assertTrue(is_option_symbol("NIFTY 25000 CE"))
        self.assertTrue(is_option_symbol("BANKNIFTY 52000 PE"))
        self.assertFalse(is_option_symbol("RELIANCE"))
        self.assertFalse(is_option_symbol("ICICI BANK"))
        self.assertFalse(is_option_symbol("NIFTY"))

        # Option contract tick data for AUBANK 23 NOV 950 CALL from user screenshot
        aubank_tick = {
            "symbol": "AUBANK 23 NOV 950 CALL",
            "open": 24.35,
            "high": 26.45,
            "low": 22.08,
            "close": 24.50,
            "ltp": 26.45,
        }

        # Apply option scaling to Fibonacci formulas
        option_cols = [
            {**c, "formula": formula_for_book(c["name"], c["formula"], "option")}
            for c in FIBONACCI_FORMULA_COLUMNS
        ]
        res = evaluate_columns_in_order(option_cols, aubank_tick)

        # Check values matching user screenshot:
        # SIGNAL: BUY
        self.assertEqual(res.get("signal"), "BUY")
        # ENTRY: 24.5
        self.assertEqual(res.get("entry"), 24.5)
        # SL: 24.38
        self.assertEqual(res.get("sl"), 24.38)

        # Targets T1 through T9:
        # T1 (11.8%): 24.5 * 1.118 = 27.391 -> 27.39
        self.assertEqual(res.get("t11.8"), 27.39)
        # T2 (23.8%): 24.5 * 1.238 = 30.331 -> 30.33
        self.assertEqual(res.get("t23.8"), 30.33)
        # T3 (38.2%): 24.5 * 1.382 = 33.859 -> 33.86
        self.assertEqual(res.get("t38.2"), 33.86)
        # T4 (50.0%): 24.5 * 1.500 = 36.75
        self.assertEqual(res.get("t50"), 36.75)
        # T5 (61.8%): 24.5 * 1.618 = 39.641 -> 39.64
        self.assertEqual(res.get("t61.8"), 39.64)
        # T6 (78.6%): 24.5 * 1.786 = 43.757 -> 43.76
        self.assertEqual(res.get("t78.6"), 43.76)
        # T7 (100%): 24.5 * 2.000 = 49.00
        self.assertEqual(res.get("t100"), 49.00)
        # T8 (161.8%): 24.5 * 2.618 = 64.141 -> 64.14
        self.assertEqual(res.get("t1.618"), 64.14)
        # T9 (261.8%): 24.5 * 3.618 = 88.641 -> 88.64
        self.assertEqual(res.get("t2.618"), 88.64)

        # Verify that BsaAlgoEngine process_row sets sell_tgt to 27.39 when T1 is selected
        import asyncio
        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="AUBANK 23 NOV 950 CALL",
            exchange="NFO",
            segment="NSE_FNO",
            is_algo_active=True,
            target_type="T1",
        )
        fake_db = AsyncMock()
        asyncio.run(
            engine._process_row(
                row=row,
                ltp=26.45,
                signal="BUY",
                entry_calc=24.5,
                sl_calc=24.38,
                t1=res.get("t11.8"),
                t2=res.get("t23.8"),
                t3=res.get("t38.2"),
                t4=res.get("t50"),
                t5=res.get("t61.8"),
                t6=res.get("t78.6"),
                t7=res.get("t100"),
                t8=res.get("t1.618"),
                t9=res.get("t2.618"),
                db=fake_db,
            )
        )
        self.assertEqual(row.sell_tgt, 27.39)

    def test_options_sell_signal_directional_targets(self):
        """Verify SELL signal decrements targets below entry, matching user screenshot for NIFTY 17 NOV 25300 CALL."""
        nifty_sell_tick = {
            "symbol": "NIFTY 17 NOV 25300 CALL",
            "open": 85.45,
            "high": 92.85,
            "low": 64.03,
            "close": 85.17,
            "ltp": 81.15,
        }
        option_cols = [
            {**c, "formula": formula_for_book(c["name"], c["formula"], "option")}
            for c in FIBONACCI_FORMULA_COLUMNS
        ]
        res = evaluate_columns_in_order(option_cols, nifty_sell_tick)
        self.assertEqual(res.get("signal"), "SELL")
        self.assertEqual(res.get("entry"), 85.17)
        self.assertEqual(res.get("sl"), 85.6)
        self.assertEqual(res.get("t11.8"), 75.12)
        self.assertEqual(res.get("t23.8"), 64.9)
        self.assertEqual(res.get("t38.2"), 52.64)
        self.assertEqual(res.get("t50"), 42.59)
        self.assertEqual(res.get("t61.8"), 32.53)
        self.assertEqual(res.get("t78.6"), 18.23)
        self.assertEqual(res.get("t100"), 0.0)
        self.assertEqual(res.get("t1.618"), -52.64)
        self.assertEqual(res.get("t2.618"), -137.81)

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
            target_type="T1",
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
                    t1=2030.0,
                    t2=2040.0,
                    t3=2050.0,
                    t4=2060.0,
                    t7=2070.0,
                    db=fake_db,
                )
            )

        self.assertEqual(row.status, "IN_POSITION")
        self.assertEqual(row.buy_price, 2015.0)
        self.assertEqual(row.sell_tgt, 2030.0)
        self.assertEqual(row.stop_loss, 2000.0)

        # Step 2: Price reaches Target T1 (2030) -> exits position
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 2030.0
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=2030.0,
                    signal="BUY",
                    entry_calc=2015.0,
                    sl_calc=2000.0,
                    t1=2030.0,
                    t2=2040.0,
                    t3=2050.0,
                    t4=2060.0,
                    t7=2070.0,
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
                    t1=2030.0,
                    t2=2040.0,
                    t3=2050.0,
                    t4=2060.0,
                    t7=2070.0,
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
                t1=2030.0,
                t2=2040.0,
                t3=2050.0,
                t4=2060.0,
                t7=2070.0,
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
            target_type="T5",
            sell_tgt=2060.0,
        )
        fake_db = AsyncMock()

        # Target map levels
        t_levels = {
            "t1": 2010.0,
            "t2": 2020.0,
            "t3": 2035.0,
            "t4": 2050.0,
            "t5": 2060.0,
            "t6": 2075.0,
            "t7": 2100.0,
            "t8": 2150.0,
            "t9": 2200.0,
        }

        # Price is at 2040. If target is changed to T3 (2035), LTP 2040 >= 2035 -> should trigger exit
        row.target_type = "T3"
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

    def test_bsa_algo_custom_target(self):
        """Verify that BsaAlgoRow with target_type='CUSTOM' executes and exits at custom target price."""
        import asyncio

        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="TCS",
            exchange="NSE",
            segment="NSE_EQ",
            is_algo_active=True,
            quantity=10,
            number_of_trades=1,
            trades_completed=0,
            status="IDLE",
            target_type="CUSTOM",
            custom_target=3550.0,
        )
        fake_db = AsyncMock()

        # Step 1: Entry
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 3500.0
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=3500.0,
                    signal="BUY",
                    entry_calc=3501.50,
                    sl_calc=3483.99,
                    t1=3520.0,
                    t2=3530.0,
                    t3=3540.0,
                    db=fake_db,
                )
            )

        self.assertEqual(row.status, "IN_POSITION")
        self.assertEqual(row.buy_price, 3500.0)
        self.assertEqual(row.sell_tgt, 3550.0)

        # Step 2: Exit when ltp reaches custom target (3550.0)
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 3550.0
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=3550.0,
                    signal="BUY",
                    entry_calc=3501.50,
                    sl_calc=3483.99,
                    t1=3520.0,
                    t2=3530.0,
                    t3=3540.0,
                    db=fake_db,
                )
            )

        self.assertEqual(row.status, "COMPLETED")
        self.assertEqual(row.trades_completed, 1)
        self.assertEqual(row.pnl, 500.0)  # (3550 - 3500) * 10

    def test_algo_buy_only_mode(self):
        """Verify BUY_ONLY mode executes buy and disarms algo for manual exit."""
        import asyncio
        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="INFY",
            exchange="NSE",
            segment="NSE_EQ",
            is_algo_active=True,
            trade_mode="BUY_ONLY",
            quantity=50,
            number_of_trades=1,
            trades_completed=0,
            status="IDLE",
            target_type="T1",
        )
        fake_db = AsyncMock()

        # Step 1: Buy executes on signal
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 1800.0
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=1800.0,
                    signal="BUY",
                    entry_calc=1800.0,
                    sl_calc=1790.0,
                    t1=1820.0,
                    db=fake_db,
                )
            )

        self.assertEqual(row.status, "IN_POSITION")
        self.assertEqual(row.buy_price, 1800.0)
        self.assertFalse(row.is_algo_active)  # Disarmed for manual exit

        # Step 2: In BUY_ONLY, when LTP reaches target, it does NOT execute auto-sell
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=1850.0,
                    signal="BUY",
                    entry_calc=1800.0,
                    sl_calc=1790.0,
                    t1=1820.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_not_called()

    def test_algo_sell_only_mode(self):
        """Verify SELL_ONLY mode skips buy and executes auto-sell when target is reached for existing position."""
        import asyncio
        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="AUBANK 23 NOV 950 CALL",
            exchange="NFO",
            segment="NSE_FNO",
            is_algo_active=True,
            trade_mode="SELL_ONLY",
            buy_price=24.50,
            quantity=100,
            number_of_trades=1,
            trades_completed=0,
            status="IN_POSITION",
            target_type="CUSTOM",
            custom_target=27.50,
        )
        fake_db = AsyncMock()

        # When price reaches target (27.50), SELL executes immediately
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 27.50
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=27.50,
                    signal="BUY",
                    entry_calc=24.50,
                    sl_calc=24.38,
                    t1=27.39,
                    db=fake_db,
                )
            )
            mock_exec.assert_called_once()

        self.assertEqual(row.status, "COMPLETED")
        self.assertFalse(row.is_algo_active)
        self.assertEqual(row.pnl, 300.0)  # (27.50 - 24.50) * 100

    def test_algo_custom_buy_entry_price(self):
        """Verify custom entry price triggers BUY when price touches or dips to the custom entry level."""
        import asyncio
        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="SBIN",
            exchange="NSE",
            segment="NSE_EQ",
            is_algo_active=True,
            trade_mode="FULL",
            entry_type="CUSTOM",
            custom_entry=800.0,
            quantity=20,
            number_of_trades=1,
            trades_completed=0,
            status="IDLE",
            target_type="T1",
        )
        fake_db = AsyncMock()

        # 1. Price is 805.0 (> 800.0 custom entry) -> no buy
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=805.0,
                    signal="BUY",
                    entry_calc=805.0,
                    sl_calc=800.0,
                    t1=815.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_not_called()
        self.assertEqual(row.status, "IDLE")

        # 2. Price touches 800.0 (<= 800.0 custom entry) -> BUY triggers!
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 800.0
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=800.0,
                    signal="BUY",
                    entry_calc=805.0,
                    sl_calc=795.0,
                    t1=815.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_called_once()

        self.assertEqual(row.status, "IN_POSITION")
        self.assertEqual(row.buy_price, 800.0)

    def test_algo_target_level_buy_entry(self):
        """Verify that BsaAlgoRow with entry_type='T2' executes BUY when price reaches T2 level."""
        import asyncio

        engine = BsaAlgoEngine.get_instance()
        row = BsaAlgoRow(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            symbol="INFY",
            exchange="NSE",
            segment="NSE_EQ",
            is_algo_active=True,
            trade_mode="FULL",
            entry_type="T2",
            quantity=15,
            number_of_trades=1,
            trades_completed=0,
            status="IDLE",
            target_type="T4",
        )
        fake_db = AsyncMock()

        # 1. Price is 815.0 (< 820.0 T2 target) -> no buy
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=815.0,
                    signal="BUY",
                    entry_calc=800.0,
                    sl_calc=795.0,
                    t1=810.0,
                    t2=820.0,
                    t3=830.0,
                    t4=840.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_not_called()
        self.assertEqual(row.status, "IDLE")

        # 2. Price reaches 820.0 (>= 820.0 T2 target) -> BUY triggers!
        with patch.object(engine, "_execute_order", new_callable=AsyncMock) as mock_exec:
            mock_exec.return_value = 820.0
            asyncio.run(
                engine._process_row(
                    row=row,
                    ltp=820.0,
                    signal="BUY",
                    entry_calc=800.0,
                    sl_calc=795.0,
                    t1=810.0,
                    t2=820.0,
                    t3=830.0,
                    t4=840.0,
                    db=fake_db,
                )
            )
            mock_exec.assert_called_once()

        self.assertEqual(row.status, "IN_POSITION")
        self.assertEqual(row.buy_price, 820.0)
        self.assertEqual(row.entry_level, 820.0)

    def test_get_dhan_positions_endpoint(self):
        """Verify that get_dhan_positions handles account lookups and broker adapter calls cleanly without NameError."""
        import asyncio
        from app.api.routes.terminal import get_dhan_positions
        from app.models.user import User

        fake_user = User(id=uuid.uuid4(), email="test@example.com", username="testuser")
        fake_db = AsyncMock()

        # Case 1: No accounts found
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        fake_db.execute.return_value = mock_result

        res = asyncio.run(get_dhan_positions(current_user=fake_user, db=fake_db))
        self.assertEqual(res["positions"], [])
        self.assertIn("No active broker account linked", res["message"])

        # Case 2: Active account exists and adapter returns positions
        mock_acc = MagicMock()
        mock_acc.account_role = "MASTER"
        mock_acc.is_active = True
        mock_acc.account_name = "Master Acc"
        mock_acc.client_id = "110022"
        mock_acc.paper_trading = False

        mock_result.scalars.return_value.all.return_value = [mock_acc]

        mock_adapter = AsyncMock()
        mock_adapter.get_positions.return_value = [
            {
                "tradingSymbol": "RELIANCE",
                "exchangeSegment": "NSE_EQ",
                "securityId": "2885",
                "netQty": 10,
                "buyAvg": 2500.0,
                "ltp": 2520.0,
                "unrealizedProfit": 200.0,
            }
        ]

        with patch("app.api.routes.terminal.get_broker_adapter", return_value=mock_adapter):
            res = asyncio.run(get_dhan_positions(current_user=fake_user, db=fake_db))
            self.assertEqual(len(res["positions"]), 1)
            self.assertEqual(res["positions"][0]["symbol"], "RELIANCE")
            self.assertEqual(res["positions"][0]["net_qty"], 10)
            self.assertEqual(res["positions"][0]["side"], "BUY")
            self.assertFalse(res["is_paper"])

    def test_mcx_column_settings_and_reorder_request(self):
        """Verify ColumnCreate, ApplyBatchRequest, and ColumnReorderRequest support MCX and column reordering."""
        import asyncio
        from app.api.routes.terminal import (
            ColumnCreate,
            ApplyBatchRequest,
            ColumnReorderRequest,
            ColumnOrderItem,
            reorder_columns,
        )

        # 1. MCX formula for book uses unscaled commodity formula
        base_f = '=IF(signal="BUY",ROUND(entry+(entry*0.118%),2),ROUND(entry-(entry*0.118%),2))'
        mcx_f = formula_for_book("T11.8", base_f, "mcx")
        self.assertEqual(mcx_f, base_f)

        # 2. ColumnCreate allows "mcx"
        col = ColumnCreate(name="MCX_TARGET", formula="=high*1.01", book="mcx")
        self.assertEqual(col.book, "mcx")

        # 3. ApplyBatchRequest allows "mcx" and "all"
        batch_mcx = ApplyBatchRequest(batch="Fibonacci Formula", book="mcx")
        self.assertEqual(batch_mcx.book, "mcx")
        batch_all = ApplyBatchRequest(batch="Fibonacci Formula", book="all")
        self.assertEqual(batch_all.book, "all")

        # 4. Reorder endpoint logic
        fake_db = AsyncMock()
        mock_col1 = MagicMock(id=uuid.uuid4(), col_order=0)
        mock_col2 = MagicMock(id=uuid.uuid4(), col_order=1)

        async def fake_execute(stmt):
            res = MagicMock()
            res.scalar_one_or_none.return_value = mock_col1
            return res

        fake_db.execute = AsyncMock(side_effect=fake_execute)
        fake_user = MagicMock(id=uuid.uuid4(), role="admin")

        req = ColumnReorderRequest(orders=[
            ColumnOrderItem(id=str(mock_col1.id), col_order=5),
        ])
        res = asyncio.run(reorder_columns(req, current_user=fake_user, db=fake_db))
        self.assertEqual(res["status"], "ok")
        self.assertEqual(res["updated"], 1)
        self.assertEqual(mock_col1.col_order, 5)


if __name__ == "__main__":
    unittest.main()
