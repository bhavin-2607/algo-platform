"""
Algo Trading Engine (Standard Formula Batch)
============================================
Automated execution engine powered by the standard 47-column formula batch.

Rules:
  - ALGO ON: Automated execution is active.
  - ALGO OFF: Manual trading mode (automated trading paused, manual BUY/SELL active).
  - ALGO BUY: When signal == "BUY" -> Enter BUY at Market Price.
  - Targets: Default target is TGT1 (or selected target). Exit on reaching target or SL
    (completing 1 trade = 1 buy + 1 sell).
  - Number of trades: 1 to 5 only.
  - Trade repeat rule: If number of trades > 1, repeat trade ONLY if price returns to entry price;
    otherwise no trade.
"""
import asyncio
import logging
import math
import re
from typing import Optional
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.algo_row import BsaAlgoRow
from app.models.user import User
from app.models.broker import BrokerAccount
from app.broker.factory import get_broker_adapter
from app.broker.base import OrderRequest
from app.strategy.excel_formula_engine import evaluate_columns_in_order, formula_for_book
from app.models.terminal_column import STANDARD_FORMULA_COLUMNS

logger = logging.getLogger(__name__)


def is_option_symbol(symbol: str, segment: Optional[str] = None) -> bool:
    """Robust detection for options and futures contracts."""
    s_upper = (symbol or "").upper().strip()
    seg_upper = (segment or "").upper().strip()
    if seg_upper in ("NSE_FNO", "NFO", "BSE_FNO", "BFO", "MCX", "OPTIDX", "OPTSTK", "FUTIDX", "FUTSTK"):
        return True
    if seg_upper in ("NSE_EQ", "BSE_EQ", "EQ"):
        return False
    if re.search(r'\b(CALL|PUT|CE|PE|FUT|OPT)\b', s_upper):
        return True
    if re.search(r'\d+\s*(CE|PE|CALL|PUT)\b', s_upper):
        return True
    return False


class BsaAlgoEngine:
    """
    Evaluates market ticks against active algo rows and executes orders.
    """
    _instance: Optional["BsaAlgoEngine"] = None

    def __init__(self):
        self._running = False
        self._db_lock = asyncio.Lock()

    @classmethod
    def get_instance(cls) -> "BsaAlgoEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def evaluate_tick_for_symbol(self, symbol: str, tick: dict, db: AsyncSession):
        """
        Evaluate an incoming tick for any active algo rows watching this symbol.
        """
        symbol_upper = symbol.upper().strip()
        ltp = float(tick.get("ltp") or 0)
        if ltp <= 0:
            return

        result = await db.execute(
            select(BsaAlgoRow).where(
                BsaAlgoRow.symbol == symbol_upper,
                BsaAlgoRow.is_algo_active == True,
            )
        )
        active_rows = result.scalars().all()
        if not active_rows:
            return

        is_option = any(r.segment in ("NSE_FNO", "NFO") for r in active_rows) or is_option_symbol(symbol_upper)

        # Calculate live standard formulas for this symbol and tick
        formula_cols = [
            {**c, "formula": formula_for_book(c["name"], c["formula"], "option" if is_option else "equity")}
            for c in STANDARD_FORMULA_COLUMNS
        ]

        vals = evaluate_columns_in_order(formula_cols, tick)
        open_val = float(tick.get("open") or ltp or 100.0)

        # Standard trading calculations (Entry SQRT offset 0.025 rounded to 0, SL 0.5%, Targets TGT1 - TGT5)
        calc_sig = str(vals.get("intrasignal") or vals.get("supersignal") or vals.get("ohlsignal") or vals.get("signal") or "BUY").upper()
        calc_is_buy = (calc_sig == "BUY")
        calc_ent = float(vals.get("entry") or round((math.sqrt(open_val) + (0.025 if calc_is_buy else -0.025))**2, 0))
        calc_sl = float(vals.get("sl") or round(calc_ent * (0.995 if calc_is_buy else 1.005), 2))

        t1 = float(vals.get("tgt1") or vals.get("bt1" if calc_is_buy else "st1") or 0.0)
        t2 = float(vals.get("tgt2") or vals.get("bt2" if calc_is_buy else "st2") or 0.0)
        t3 = float(vals.get("tgt3") or vals.get("bt3" if calc_is_buy else "st3") or 0.0)
        t4 = float(vals.get("tgt4") or vals.get("bt4" if calc_is_buy else "st4") or 0.0)
        t5 = float(vals.get("tgt5") or vals.get("bt5" if calc_is_buy else "st5") or 0.0)

        for row in active_rows:
            try:
                await self._process_row(
                    row=row,
                    ltp=ltp,
                    signal=calc_sig,
                    entry_calc=calc_ent,
                    sl_calc=calc_sl,
                    t1=t1,
                    t2=t2,
                    t3=t3,
                    t4=t4,
                    t5=t5,
                    db=db,
                )
            except Exception as e:
                logger.error(f"Error processing algo row {row.id} for {symbol_upper}: {e}")

    async def _process_row(
        self,
        row: BsaAlgoRow,
        ltp: float,
        signal: str,
        entry_calc: float,
        sl_calc: float,
        t1: float = 0.0,
        t2: float = 0.0,
        t3: float = 0.0,
        t4: float = 0.0,
        t5: float = 0.0,
        db: AsyncSession = None,
    ):
        target_map = {
            "T1":     t1,
            "TGT1":   t1,
            "T2":     t2,
            "TGT2":   t2,
            "T3":     t3,
            "TGT3":   t3,
            "T4":     t4,
            "TGT4":   t4,
            "T5":     t5,
            "TGT5":   t5,
            "CUSTOM": float(row.custom_target or row.sell_tgt or 0.0),
        }
        if row.target_type == "CUSTOM" and row.custom_target and row.custom_target > 0:
            chosen_target = float(row.custom_target)
        else:
            chosen_target = target_map.get((row.target_type or "TGT1").upper(), t1)

        if chosen_target > 0:
            row.sell_tgt = chosen_target

        trade_mode = getattr(row, "trade_mode", "FULL") or "FULL"
        entry_type = getattr(row, "entry_type", "FORMULA") or "FORMULA"
        custom_entry = getattr(row, "custom_entry", None)

        # In SELL_ONLY mode, if row is still in IDLE, immediately transition to IN_POSITION
        if trade_mode == "SELL_ONLY" and row.status in ("IDLE", "WAITING_SIGNAL"):
            row.status = "IN_POSITION"
            if chosen_target > 0:
                row.sell_tgt = chosen_target

        # ── 1. Check Entry (State: IDLE or WAITING_SIGNAL) ───────────────────
        if row.status in ("IDLE", "WAITING_SIGNAL") and trade_mode != "SELL_ONLY" and row.trades_completed < row.number_of_trades:
            # Determine if entry trigger condition is met
            entry_triggered = False
            entry_type_norm = (entry_type or "FORMULA").upper().strip()
            active_buy_price = entry_calc

            if entry_type_norm == "CUSTOM" and custom_entry and custom_entry > 0:
                # Custom Buy Trigger: executes when price dips to or touches the custom buy price
                active_buy_price = float(custom_entry)
                if ltp <= active_buy_price:
                    entry_triggered = True
            elif entry_type_norm in target_map:
                # Target Buy Trigger (T1 - T9 breakout or level reach)
                active_buy_price = float(target_map.get(entry_type_norm) or 0.0)
                if active_buy_price > 0:
                    if signal == "SELL":
                        if ltp <= active_buy_price:
                            entry_triggered = True
                    else:
                        if ltp >= active_buy_price:
                            entry_triggered = True
            else:
                # Default Formula Signal Trigger
                active_buy_price = entry_calc
                if signal == "BUY":
                    entry_triggered = True

            if entry_triggered:
                # Execute Market BUY
                fill_price = await self._execute_order(row, side="BUY", price=ltp, db=db)
                if fill_price:
                    row.buy_price = fill_price
                    row.entry_level = active_buy_price if active_buy_price > 0 else fill_price
                    row.sell_tgt = chosen_target
                    row.stop_loss = sl_calc
                    row.status = "IN_POSITION"
                    row.last_signal = "BUY"

                    # If BUY_ONLY, disarm algo immediately so exit is 100% manual
                    if trade_mode == "BUY_ONLY":
                        row.is_algo_active = False
                        logger.info(
                            f"[ALGO EXEC] BUY_ONLY {row.symbol} qty={row.quantity} @ {fill_price:.2f}. "
                            f"Algo disarmed for manual exit."
                        )
                    else:
                        logger.info(
                            f"[ALGO EXEC] BUY {row.symbol} qty={row.quantity} @ {fill_price:.2f} "
                            f"(TGT: {row.sell_tgt:.2f}, SL: {row.stop_loss:.2f}) [Trade {row.trades_completed + 1}/{row.number_of_trades}]"
                        )
                    await db.commit()
                return

        # ── 2. Check Exit (State: IN_POSITION) ────────────────────────────────
        if row.status == "IN_POSITION":
            # Update live PnL
            if row.buy_price:
                row.pnl = round((ltp - row.buy_price) * row.quantity, 2)

            # In BUY_ONLY mode, do not execute auto-exit (exit is manual)
            if trade_mode != "BUY_ONLY":
                hit_target = bool(row.sell_tgt and ltp >= row.sell_tgt)
                hit_sl = bool(row.stop_loss and ltp <= row.stop_loss)

                if hit_target or hit_sl:
                    reason = "TARGET HIT" if hit_target else "STOP LOSS HIT"
                    exit_fill = await self._execute_order(row, side="SELL", price=ltp, db=db)
                    if exit_fill:
                        row.trades_completed += 1
                        if row.buy_price:
                            row.pnl = round((exit_fill - row.buy_price) * row.quantity, 2)

                        logger.info(
                            f"[ALGO EXEC] SELL {row.symbol} qty={row.quantity} @ {exit_fill:.2f} ({reason}) "
                            f"[Mode: {trade_mode}, Completed {row.trades_completed}/{row.number_of_trades} trades]"
                        )

                        # If SELL_ONLY mode or reached max trades, complete and turn off algo
                        if trade_mode == "SELL_ONLY" or row.trades_completed >= row.number_of_trades:
                            row.status = "COMPLETED"
                            row.is_algo_active = False  # Completed
                        else:
                            # Waiting for price to return to entry price before repeating
                            row.status = "WAITING_RETURN"

                        await db.commit()
                    return

        # ── 3. Check Return to Entry (State: WAITING_RETURN) ─────────────────
        if row.status == "WAITING_RETURN" and trade_mode == "FULL" and row.trades_completed < row.number_of_trades:
            # Rule: Repeat trade ONLY if price returns to entry price
            ref_entry = row.entry_level or row.buy_price or entry_calc
            if ref_entry and ltp <= ref_entry:
                row.status = "WAITING_SIGNAL"
                logger.info(
                    f"[ALGO RETURN] {row.symbol} returned to entry {ref_entry:.2f} (current ltp: {ltp:.2f}). "
                    f"Ready for trade cycle {row.trades_completed + 1}/{row.number_of_trades}."
                )
                await db.commit()

    async def _execute_order(self, row: BsaAlgoRow, side: str, price: float, db: AsyncSession) -> Optional[float]:
        """
        Execute an order through the Dhan adapter (or paper simulated broker).
        Returns the fill price.
        """
        # Look up active broker account for user
        result = await db.execute(
            select(BrokerAccount).where(
                BrokerAccount.user_id == row.user_id,
                BrokerAccount.is_active == True,
            )
        )
        ba = result.scalars().first()
        adapter = None
        if ba:
            try:
                adapter = get_broker_adapter(ba)
            except Exception as e:
                logger.info(f"Live broker adapter not available ({e}); falling back to simulated paper execution.")
                adapter = None

        # Resolve Dhan security ID and exchange
        security_id = str(row.symbol)
        exchange = row.exchange or "NSE_EQ"
        try:
            import os
            import pandas as _pd
            csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "market", "instruments.csv"))
            if os.path.exists(csv_path):
                _df = _pd.read_csv(csv_path, usecols=["SYMBOL_NAME", "SECURITY_ID", "EXCH_ID"], dtype=str)
                _match = _df[(_df["SYMBOL_NAME"] == row.symbol) & (_df["EXCH_ID"] == "NSE")]
                if not _match.empty:
                    security_id = str(_match.iloc[0]["SECURITY_ID"]).strip()
                    exchange = "NSE_EQ"
        except Exception as e:
            logger.warning(f"Dhan security lookup failed for {row.symbol}: {e}")

        # Resolve price
        from app.market.market_poller import get_poller
        poller = get_poller()
        live = next((t for t in (poller._last_data or []) if t.get("symbol") == row.symbol), {})
        fill_price = float(price or live.get("ltp") or row.buy_price or 100.0)

        req = OrderRequest(
            symbol=security_id,
            exchange=exchange,
            direction=side.upper(),
            quantity=max(1, row.quantity),
            order_type="MARKET",
            product="MIS",
            price=fill_price,
        )

        try:
            if adapter:
                from app.services.dhan_fanout_engine import fanout_engine
                fanout_res = await fanout_engine.execute_fanout_order(
                    user_id=row.user_id,
                    base_order=req,
                    source="ALGO_AUTO",
                    db=db,
                )
                master_info = fanout_res.get("master") or {}
                if master_info.get("status") == "REJECTED":
                    logger.error(f"[ALGO EXEC ERROR] Dhan rejected {side} order for {row.symbol}: {master_info.get('error_message')}")
                    return None
                row.last_order_id = master_info.get("broker_order_id") or f"DHAN-{int(asyncio.get_event_loop().time()*1000)}"
                return fill_price
            else:
                # Simulated paper execution
                row.last_order_id = f"SIM-{int(asyncio.get_event_loop().time()*1000)}"
                return fill_price
        except Exception as e:
            logger.error(f"[ALGO EXEC ERROR] Failed placing {side} order for {row.symbol}: {e}")
            return None


algo_engine = BsaAlgoEngine.get_instance()
