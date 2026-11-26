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
        self._row_locks: dict[UUID, asyncio.Lock] = {}
        self._last_dhan_sync_time: dict[str, float] = {}

    @classmethod
    def get_instance(cls) -> "BsaAlgoEngine":
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    async def sync_dhan_status(self, db: AsyncSession, user_id: Optional[UUID] = None, force: bool = False) -> int:
        """
        Synchronize Algo Window rows with live Dhan orderbook and position status.
        Ensures the Algo Window row status strictly reflects true broker state:
        - If Dhan position is CLOSED (netQty=0, buyQty>0, sellQty>0) -> COMPLETED.
        - If Dhan position is OPEN (netQty>0) -> IN_POSITION with real buyAvg.
        - If Dhan recent order is REJECTED -> REJECTED and ALGO OFF.
        - If Dhan recent order is TRADED BUY -> IN_POSITION with real traded price.
        - If Dhan recent order is TRADED SELL -> COMPLETED and ALGO OFF.
        """
        user_key = str(user_id) if user_id else "all"
        now_ts = asyncio.get_event_loop().time()
        # Debounce: 2.0s cache unless forced
        if not force and (now_ts - self._last_dhan_sync_time.get(user_key, 0.0) < 2.0):
            return 0
        self._last_dhan_sync_time[user_key] = now_ts

        # Find active BrokerAccount
        stmt = select(BrokerAccount).where(BrokerAccount.is_active == True)
        if user_id:
            stmt = stmt.where(BrokerAccount.user_id == user_id)
        result = await db.execute(stmt)
        accounts = result.scalars().all()
        if not accounts:
            return 0

        # Select active live Dhan account (skip simulated/paper accounts)
        dhan_account = next(
            (
                a for a in accounts
                if not getattr(a, "paper_trading", False)
                and (
                    "DHAN" in str(getattr(a, "broker", "")).upper()
                    or "DHAN" in str(getattr(a, "broker_type", "")).upper()
                )
            ),
            None,
        )
        if not dhan_account:
            return 0

        try:
            adapter = get_broker_adapter(dhan_account)
            if not adapter:
                return 0

            # Fetch live positions and orders from Dhan
            positions_res, orders_res = await asyncio.gather(
                adapter.get_positions(),
                adapter.get_order_book(),
                return_exceptions=True,
            )

            pos_list = positions_res if isinstance(positions_res, list) else []
            order_list = orders_res if isinstance(orders_res, list) else []

            # Map positions by securityId and tradingSymbol
            pos_by_sec_id = {}
            pos_by_sym = {}
            for p in pos_list:
                sid = str(p.get("securityId") or "").strip()
                sym = str(p.get("tradingSymbol") or "").strip().upper()
                if sid:
                    pos_by_sec_id[sid] = p
                if sym:
                    pos_by_sym[sym] = p

            # Map orders by orderId and securityId (ordered chronologically)
            order_by_id = {}
            orders_by_sec_id = {}
            for o in order_list:
                oid = str(o.get("orderId") or "").strip()
                sid = str(o.get("securityId") or "").strip()
                if oid:
                    order_by_id[oid] = o
                if sid:
                    orders_by_sec_id.setdefault(sid, []).append(o)

            # Query algo rows
            row_stmt = select(BsaAlgoRow)
            if user_id:
                row_stmt = row_stmt.where(BsaAlgoRow.user_id == user_id)
            row_res = await db.execute(row_stmt)
            algo_rows = row_res.scalars().all()

            updated_count = 0
            for r in algo_rows:
                sec_id = str(r.token or "").strip()
                sym_u = (r.symbol or "").strip().upper()
                pos = pos_by_sec_id.get(sec_id) or pos_by_sym.get(sym_u)

                # 1. Check Dhan Position state
                if pos:
                    net_qty = int(pos.get("netQty") or 0)
                    buy_qty = int(pos.get("buyQty") or 0)
                    sell_qty = int(pos.get("sellQty") or 0)
                    buy_avg = float(pos.get("buyAvg") or pos.get("costPrice") or 0.0)
                    sell_avg = float(pos.get("sellAvg") or 0.0)
                    realized = float(pos.get("realizedProfit") or 0.0)

                    if net_qty == 0 and buy_qty > 0 and sell_qty > 0:
                        # Full round-trip trade closed on Dhan
                        if r.status != "COMPLETED" or r.is_algo_active:
                            r.status = "COMPLETED"
                            r.trades_completed = max(r.trades_completed, 1)
                            if buy_avg > 0:
                                r.buy_price = buy_avg
                            if sell_avg > 0:
                                r.sell_tgt = sell_avg
                            r.pnl = realized
                            r.is_algo_active = False
                            r.last_signal = "DHAN CLOSED"
                            updated_count += 1
                    elif net_qty > 0:
                        # Open holding in Dhan
                        if r.status != "IN_POSITION" or not r.buy_price:
                            r.status = "IN_POSITION"
                            if buy_avg > 0:
                                r.buy_price = buy_avg
                            r.quantity = net_qty
                            r.last_signal = "DHAN HOLDING"
                            if r.trade_mode == "BUY_ONLY":
                                r.is_algo_active = False
                            updated_count += 1

                # 2. Check Dhan Order state
                sec_orders = orders_by_sec_id.get(sec_id) or []
                latest_order = None
                if r.last_order_id and r.last_order_id in order_by_id:
                    latest_order = order_by_id[r.last_order_id]
                elif sec_orders:
                    latest_order = sec_orders[-1]

                if latest_order:
                    o_status = str(latest_order.get("orderStatus") or "").upper()
                    o_side = str(latest_order.get("transactionType") or "").upper()
                    o_price = float(latest_order.get("price") or 0.0)
                    oms_err = str(latest_order.get("omsErrorDescription") or "")

                    if o_status == "REJECTED":
                        if r.status in ("ORDER_PENDING", "EXIT_PENDING"):
                            r.status = "REJECTED"
                            r.is_algo_active = False
                            r.last_signal = f"REJECTED: {oms_err}"[:50]
                            updated_count += 1
                    elif o_status in ("PENDING", "TRANSIT"):
                        if o_side == "BUY" and r.status != "ORDER_PENDING":
                            r.status = "ORDER_PENDING"
                            updated_count += 1
                        elif o_side == "SELL" and r.status != "EXIT_PENDING":
                            r.status = "EXIT_PENDING"
                            updated_count += 1
                    elif o_status == "TRADED":
                        if o_side == "BUY" and r.status in ("ORDER_PENDING", "IDLE", "WAITING_SIGNAL"):
                            r.status = "IN_POSITION"
                            if o_price > 0:
                                r.buy_price = o_price
                            if r.trade_mode == "BUY_ONLY":
                                r.is_algo_active = False
                            updated_count += 1
                        elif o_side == "SELL" and r.status in ("EXIT_PENDING", "IN_POSITION"):
                            r.status = "COMPLETED"
                            r.trades_completed = max(r.trades_completed, 1)
                            r.is_algo_active = False
                            updated_count += 1

            if updated_count > 0:
                await db.commit()
            return updated_count
        except Exception as e:
            logger.warning(f"Dhan status sync failed: {e}")
            return 0

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
        row_lock = self._row_locks.setdefault(row.id, asyncio.Lock())
        if row_lock.locked():
            return

        async with row_lock:
            if not row.is_algo_active or row.status in ("ORDER_PENDING", "EXIT_PENDING"):
                return
            await self._process_row_guarded(
                row=row,
                ltp=ltp,
                signal=signal,
                entry_calc=entry_calc,
                sl_calc=sl_calc,
                t1=t1,
                t2=t2,
                t3=t3,
                t4=t4,
                t5=t5,
                db=db,
            )

    async def _process_row_guarded(
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

        # ── 1. Check Entry (State: IDLE or WAITING_SIGNAL) ───────────────────
        # RULE 3: In FULL CYCLE, if BUY is not done it must NEVER initiate SELL.
        # SELL_ONLY mode NEVER executes entry; it only manages an existing holding.
        if row.status in ("IDLE", "WAITING_SIGNAL") and trade_mode != "SELL_ONLY" and row.trades_completed < row.number_of_trades:
            entry_triggered = False
            entry_type_norm = (entry_type or "FORMULA").upper().strip()
            active_buy_price = float(entry_calc or 0.0)

            if entry_type_norm == "CUSTOM" and custom_entry and custom_entry > 0:
                # Custom Buy Trigger: executes when market touches or dips to custom entry price
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
                # RULE 1: BUY ONLY / FORMULA ENTRY
                # When BUY TARGET is set to ENTRY FORMULA, buy at the entry price and not the LTP.
                # Only triggers when signal is BUY and price reaches entry price (ltp <= active_buy_price).
                active_buy_price = float(entry_calc or 0.0)
                if active_buy_price > 0 and signal == "BUY" and ltp <= active_buy_price:
                    entry_triggered = True

            if entry_triggered and active_buy_price > 0:
                row.status = "ORDER_PENDING"
                await db.commit()

                # Execute BUY at entry price (LIMIT order at active_buy_price, not at LTP)
                try:
                    fill_price = await self._execute_order(
                        row=row,
                        side="BUY",
                        price=active_buy_price,
                        order_type="LIMIT",
                        db=db,
                    )
                except Exception as e:
                    row.status = "REJECTED"
                    row.last_signal = f"ERR: {str(e)[:40]}"
                    row.is_algo_active = False
                    await db.commit()
                    return

                if fill_price:
                    row.buy_price = fill_price
                    row.entry_level = active_buy_price
                    row.sell_tgt = chosen_target
                    row.stop_loss = sl_calc
                    row.status = "IN_POSITION"
                    row.last_signal = "BUY"

                    # RULE 1: If BUY_ONLY, disarm algo immediately so exit is 100% manual
                    if trade_mode == "BUY_ONLY":
                        row.is_algo_active = False
                        logger.info(
                            f"[ALGO EXEC] BUY_ONLY {row.symbol} qty={row.quantity} bought @ {fill_price:.2f}. "
                            f"Algo disarmed for manual exit (ALGO OFF)."
                        )
                    else:
                        logger.info(
                            f"[ALGO EXEC] BUY {row.symbol} qty={row.quantity} @ {fill_price:.2f} "
                            f"(TGT: {row.sell_tgt:.2f}, SL: {row.stop_loss:.2f}) [Trade {row.trades_completed + 1}/{row.number_of_trades}]"
                        )
                    await db.commit()
                else:
                    row.status = "IDLE"
                    await db.commit()
                return

        # ── 2. Check Exit (State: IN_POSITION) ────────────────────────────────
        # RULE 2: SELL ONLY works ONLY when current holding is shown in Algo Window (IN_POSITION with buy_price > 0).
        # RULE 3: FULL CYCLE requires BUY first; this exit block is reached ONLY if status is IN_POSITION.
        if row.status == "IN_POSITION" and row.buy_price is not None and row.buy_price > 0:
            # Update live PnL
            row.pnl = round((ltp - row.buy_price) * row.quantity, 2)

            # In BUY_ONLY mode, do not execute auto-exit (exit is manual)
            if trade_mode != "BUY_ONLY":
                effective_target = chosen_target if chosen_target > 0 else (row.sell_tgt or 0.0)
                hit_target = bool(effective_target > 0 and ltp >= effective_target)
                hit_sl = bool(row.stop_loss and row.stop_loss > 0 and ltp <= row.stop_loss)

                if hit_target or hit_sl:
                    reason = "TARGET HIT" if hit_target else "STOP LOSS HIT"
                    exit_price = effective_target if hit_target else row.stop_loss
                    row.status = "EXIT_PENDING"
                    await db.commit()

                    try:
                        # RULE 2: Sell at target price and not at LTP (LIMIT order at exit_price)
                        exit_fill = await self._execute_order(
                            row=row,
                            side="SELL",
                            price=exit_price,
                            order_type="LIMIT",
                            db=db,
                        )
                    except Exception as e:
                        row.status = "IN_POSITION"
                        row.last_signal = f"ERR: {str(e)[:40]}"
                        row.is_algo_active = False
                        await db.commit()
                        return

                    if exit_fill:
                        row.trades_completed += 1
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
                    else:
                        row.status = "IN_POSITION"
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

    async def _execute_order(
        self,
        row: BsaAlgoRow,
        side: str,
        price: float,
        order_type: str = "LIMIT",
        db: AsyncSession = None,
    ) -> Optional[float]:
        """
        Execute an order through the Dhan adapter (or paper simulated broker).
        Uses LIMIT orders at target/entry price by default, avoiding market slippage.
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

        # Resolve Dhan security ID and exchange segment
        security_id = str(row.token).strip() if (row.token and str(row.token).strip() not in ("0", "None", "")) else str(row.symbol)
        seg_str = str(row.segment or "").upper()
        exch_str = str(row.exchange or "").upper()
        if "MCX" in seg_str or exch_str == "MCX":
            exchange = "MCX_COMM"
        elif "BSE" in seg_str or "BFO" in seg_str or exch_str in ("BSE", "BFO"):
            exchange = "BSE_FNO" if is_option_symbol(row.symbol) else "BSE_EQ"
        elif is_option_symbol(row.symbol) or "FNO" in seg_str or exch_str == "NFO":
            exchange = "NSE_FNO"
        else:
            exchange = row.exchange or "NSE_EQ"

        if not row.token or str(row.token).strip() in ("0", "None", ""):
            try:
                from app.api.routes.market import resolve_dhan_instrument
                resolved = resolve_dhan_instrument(row.symbol, exchange, row.segment)
                if resolved and resolved.get("security_id"):
                    security_id = resolved["security_id"]
                    row.token = security_id
                    if resolved.get("segment"):
                        row.segment = resolved["segment"]
                    if resolved.get("exchange"):
                        row.exchange = resolved["exchange"]
            except Exception as e:
                logger.warning(f"Dhan security lookup failed for {row.symbol}: {e}")

        # Resolve price
        from app.market.market_poller import get_poller
        poller = get_poller()
        live = next((t for t in (poller._last_data or []) if t.get("symbol") == row.symbol), {})
        target_price = float(price or 0.0)
        ltp_price = float(live.get("ltp") or row.buy_price or 0.0)
        execution_price = target_price if target_price > 0 else ltp_price

        # Options and commodity derivatives default to MARGIN (Normal / Carryforward)
        # to ensure compatibility with Dhan RMS policies which restrict Intraday on certain derivative scrips.
        is_derivative = any(k in str(exchange) for k in ("MCX", "FNO", "COMM")) or is_option_symbol(row.symbol)
        algo_prod = "MARGIN" if is_derivative else "INTRADAY"

        from app.services.dhan_fanout_engine import resolve_lot_size
        contract_lot = resolve_lot_size(row.symbol, security_id)
        final_order_qty = max(1, row.quantity)
        if is_derivative and contract_lot > 1 and final_order_qty < contract_lot:
            final_order_qty = final_order_qty * contract_lot

        actual_order_type = (order_type or "LIMIT").upper()
        actual_price = round(execution_price, 2) if actual_order_type == "LIMIT" and execution_price > 0 else 0.0
        if actual_order_type == "LIMIT" and actual_price <= 0:
            actual_order_type = "MARKET"
            actual_price = 0.0

        req = OrderRequest(
            symbol=security_id,
            exchange=exchange,
            direction=side.upper(),
            quantity=final_order_qty,
            order_type=actual_order_type,
            product=algo_prod,
            price=actual_price,
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
                    err_msg = master_info.get("error_message") or "Broker rejected order"
                    logger.error(f"[ALGO EXEC ERROR] Dhan rejected {side} order for {row.symbol}: {err_msg}")
                    from app.core.alerts import raise_alert
                    await raise_alert("ALGO EXEC ERROR", f"Dhan rejected {side} order for {row.symbol}: {err_msg}")
                    raise RuntimeError(f"Dhan rejected {side} order for {row.symbol}: {err_msg}")
                row.last_order_id = master_info.get("broker_order_id") or f"DHAN-{int(asyncio.get_event_loop().time()*1000)}"
                fill_price = float(master_info.get("fill_price") or execution_price)
                return fill_price
            else:
                # Simulated paper execution
                row.last_order_id = f"SIM-{int(asyncio.get_event_loop().time()*1000)}"
                return execution_price
        except Exception as e:
            logger.error(f"[ALGO EXEC ERROR] Failed placing {side} order for {row.symbol}: {e}")
            raise


algo_engine = BsaAlgoEngine.get_instance()
