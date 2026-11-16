"""
Algo Trading Engine (Fibonacci Formula Batch)
=============================================
Automated execution engine powered by the Fibonacci formula batch.

Rules:
  - ALGO ON: Automated execution is active.
  - ALGO OFF: Manual trading mode (automated trading paused, manual BUY/SELL active).
  - ALGO BUY: When signal == "BUY" -> Enter BUY at Market Price.
  - Targets: Default target is T11.8 (or selected target). Exit on reaching target or SL
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
from app.models.terminal_column import FIBONACCI_FORMULA_COLUMNS

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
    Evaluates market ticks against active Fibonacci algo rows and executes orders.
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

        # Calculate live Fibonacci formulas for this symbol and tick
        fib_cols = [
            {**c, "formula": formula_for_book(c["name"], c["formula"], "option" if is_option else "equity")}
            for c in FIBONACCI_FORMULA_COLUMNS
        ]

        fib_vals = evaluate_columns_in_order(fib_cols, tick)
        open_val = float(tick.get("open") or ltp or 100.0)

        # Fibonacci calculations (Entry SQRT offset 0.015, SL 0.5%, Targets T1 - T9)
        fib_sig = str(fib_vals.get("signal") or fib_vals.get("ssig") or "BUY").upper()
        fib_is_buy = (fib_sig == "BUY")
        fib_sign = 1 if fib_is_buy else -1
        fib_mult = 100.0 if is_option else 1.0
        fib_ent = float(fib_vals.get("entry") or round((math.sqrt(open_val) + (0.015 if fib_is_buy else -0.015))**2, 2))
        fib_sl = float(fib_vals.get("sl") or round(fib_ent * (0.995 if fib_is_buy else 1.005), 2))

        t1 = float(fib_vals.get("t11.8") or fib_vals.get("t11_8") or round(fib_ent * (1 + fib_sign * 0.00118 * fib_mult), 2))
        t2 = float(fib_vals.get("t23.8") or fib_vals.get("t23_8") or round(fib_ent * (1 + fib_sign * 0.00238 * fib_mult), 2))
        t3 = float(fib_vals.get("t38.2") or fib_vals.get("t38_2") or round(fib_ent * (1 + fib_sign * 0.00382 * fib_mult), 2))
        t4 = float(fib_vals.get("t50") or round(fib_ent * (1 + fib_sign * 0.005 * fib_mult), 2))
        t5 = float(fib_vals.get("t61.8") or fib_vals.get("t61_8") or round(fib_ent * (1 + fib_sign * 0.00618 * fib_mult), 2))
        t6 = float(fib_vals.get("t78.6") or fib_vals.get("t78_6") or round(fib_ent * (1 + fib_sign * 0.00786 * fib_mult), 2))
        t7 = float(fib_vals.get("t100") or round(fib_ent * (1 + fib_sign * 0.01 * fib_mult), 2))
        t8 = float(fib_vals.get("t1.618") or fib_vals.get("t1_618") or round(fib_ent * (1 + fib_sign * 0.01618 * fib_mult), 2))
        t9 = float(fib_vals.get("t2.618") or fib_vals.get("t2_618") or round(fib_ent * (1 + fib_sign * 0.02618 * fib_mult), 2))

        for row in active_rows:
            try:
                await self._process_row(
                    row=row,
                    ltp=ltp,
                    signal=fib_sig,
                    entry_calc=fib_ent,
                    sl_calc=fib_sl,
                    t1=t1,
                    t2=t2,
                    t3=t3,
                    t4=t4,
                    t5=t5,
                    t6=t6,
                    t7=t7,
                    t8=t8,
                    t9=t9,
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
        t6: float = 0.0,
        t7: float = 0.0,
        t8: float = 0.0,
        t9: float = 0.0,
        db: AsyncSession = None,
    ):
        target_map = {
            "T1":     t1,
            "T11.8":  t1,
            "T11_8":  t1,
            "TGT1":   t1,
            "T2":     t2,
            "T23.8":  t2,
            "T23_8":  t2,
            "TGT2":   t2,
            "T3":     t3,
            "T38.2":  t3,
            "T38_2":  t3,
            "TGT3":   t3,
            "T4":     t4,
            "T50":    t4,
            "T5":     t5,
            "T61.8":  t5,
            "T61_8":  t5,
            "T6":     t6,
            "T78.6":  t6,
            "T78_6":  t6,
            "T7":     t7,
            "T100":   t7,
            "T8":     t8,
            "T1.618": t8,
            "T1_618": t8,
            "T9":     t9,
            "T2.618": t9,
            "T2_618": t9,
            "CUSTOM": float(row.custom_target or row.sell_tgt or 0.0),
        }
        if row.target_type == "CUSTOM" and row.custom_target and row.custom_target > 0:
            chosen_target = float(row.custom_target)
        else:
            chosen_target = target_map.get((row.target_type or "T1").upper(), t1)

        if chosen_target > 0:
            row.sell_tgt = chosen_target

        # ── 1. Check Entry (State: IDLE or WAITING_SIGNAL) ───────────────────
        if row.status in ("IDLE", "WAITING_SIGNAL") and row.trades_completed < row.number_of_trades:
            if signal == "BUY":
                # Execute Market BUY
                fill_price = await self._execute_order(row, side="BUY", price=ltp, db=db)
                if fill_price:
                    row.buy_price = fill_price
                    row.entry_level = entry_calc if entry_calc > 0 else fill_price
                    row.sell_tgt = chosen_target
                    row.stop_loss = sl_calc
                    row.status = "IN_POSITION"
                    row.last_signal = "BUY"
                    await db.commit()
                    logger.info(
                        f"[ALGO EXEC] BUY {row.symbol} qty={row.quantity} @ {fill_price:.2f} "
                        f"(TGT: {row.sell_tgt:.2f}, SL: {row.stop_loss:.2f}) [Trade {row.trades_completed + 1}/{row.number_of_trades}]"
                    )
                return

        # ── 2. Check Exit (State: IN_POSITION) ────────────────────────────────
        if row.status == "IN_POSITION":
            # Update live PnL
            if row.buy_price:
                row.pnl = round((ltp - row.buy_price) * row.quantity, 2)

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
                        f"[Completed {row.trades_completed}/{row.number_of_trades} trades]"
                    )

                    if row.trades_completed >= row.number_of_trades:
                        row.status = "COMPLETED"
                        row.is_algo_active = False  # Completed all planned trades
                    else:
                        # Waiting for price to return to entry price before repeating
                        row.status = "WAITING_RETURN"

                    await db.commit()
                return

        # ── 3. Check Return to Entry (State: WAITING_RETURN) ─────────────────
        if row.status == "WAITING_RETURN" and row.trades_completed < row.number_of_trades:
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
        adapter = get_broker_adapter(ba) if ba else None

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
