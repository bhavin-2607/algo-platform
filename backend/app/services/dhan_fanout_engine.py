"""
Dhan Order Fanout Engine
========================
Provides multi-account copy trading for DhanHQ broker accounts.
When a trade is triggered from the platform (Terminal, Watchlist, Algo Window, or Kill Switch),
this service executes the trade on the Master account and concurrently broadcasts matching
fixed-quantity orders to all active, enabled Child Dhan accounts.
"""
import asyncio
import json
import logging
import re
import uuid
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any
from uuid import UUID

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.broker.base import OrderRequest, OrderResponse
from app.broker.factory import get_broker_adapter
from app.models.broker import BrokerAccount
from app.models.copy_trade_log import CopyTradeLog
from app.core.redis_client import get_redis
from app.core.database import AsyncSessionLocal

logger = logging.getLogger(__name__)

# Cache for contract lot sizes to avoid repeated disk reads
LOT_SIZE_CACHE: Dict[str, int] = {}
_CSV_LOT_MAP: Dict[str, int] = {}
_CSV_LOT_MTIME: float = 0.0


def _get_csv_lot_map() -> Dict[str, int]:
    """Load and index exchange lot sizes directly from the official Dhan instruments master CSV."""
    global _CSV_LOT_MAP, _CSV_LOT_MTIME
    import os, csv
    csv_path = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "market", "instruments.csv"))
    if not os.path.exists(csv_path):
        return _CSV_LOT_MAP

    try:
        mtime = os.path.getmtime(csv_path)
        if _CSV_LOT_MAP and mtime == _CSV_LOT_MTIME:
            return _CSV_LOT_MAP

        new_map: Dict[str, int] = {}
        with open(csv_path, mode="r", encoding="utf-8", errors="ignore") as f:
            reader = csv.reader(f)
            header = next(reader, None)
            for r in reader:
                if len(r) > 11:
                    try:
                        lot = int(float(r[11]))
                        if lot > 0:
                            if r[2]:
                                new_map[r[2].strip()] = lot
                            if r[7]:
                                new_map[r[7].strip().upper()] = lot
                            disp = r[8].strip().upper() if len(r) > 8 and r[8] else ""
                            if disp:
                                new_map[disp] = lot
                                if " CALL" in disp:
                                    new_map[disp.replace(" CALL", " CE")] = lot
                                elif " CE" in disp:
                                    new_map[disp.replace(" CE", " CALL")] = lot
                                if " PUT" in disp:
                                    new_map[disp.replace(" PUT", " PE")] = lot
                                elif " PE" in disp:
                                    new_map[disp.replace(" PE", " PUT")] = lot
                    except (ValueError, TypeError):
                        pass
        _CSV_LOT_MAP = new_map
        _CSV_LOT_MTIME = mtime
    except Exception as e:
        logger.debug(f"Error loading CSV lot map: {e}")
    return _CSV_LOT_MAP


FREEZE_QTY_CACHE: Dict[str, int] = {}


def resolve_freeze_qty(symbol: str, security_id: Optional[str] = None) -> int:
    """Resolve exchange freeze quantity limit for F&O and Commodity contracts."""
    sym = (symbol or "").upper().strip()
    if sym in FREEZE_QTY_CACHE:
        return FREEZE_QTY_CACHE[sym]

    if "BANKNIFTY" in sym:
        limit = 900
    elif "FINNIFTY" in sym:
        limit = 1800
    elif "MIDCPNIFTY" in sym:
        limit = 4200
    elif "NIFTY" in sym:
        limit = 1800
    elif "SENSEX" in sym:
        limit = 1000
    elif "BANKEX" in sym:
        limit = 1000
    elif "CRUDEOIL" in sym:
        limit = 10000
    elif "NATURALGAS" in sym:
        limit = 25000
    elif "GOLD" in sym:
        limit = 1000
    elif "SILVER" in sym:
        limit = 1000
    else:
        limit = 50000

    FREEZE_QTY_CACHE[sym] = limit
    return limit


def resolve_lot_size(symbol: str, security_id: Optional[str] = None) -> int:
    """Resolve exchange contract lot size for F&O and Commodity contracts."""
    sym = (symbol or "").upper().strip()
    sec_id_str = str(security_id or "").strip()

    # Fast memory cache check
    if sec_id_str and sec_id_str in LOT_SIZE_CACHE:
        return LOT_SIZE_CACHE[sec_id_str]
    if sym and sym in LOT_SIZE_CACHE:
        return LOT_SIZE_CACHE[sym]

    # Dynamic lookup from official Dhan instruments master
    csv_lots = _get_csv_lot_map()
    if sec_id_str and sec_id_str in csv_lots:
        lot = csv_lots[sec_id_str]
        LOT_SIZE_CACHE[sec_id_str] = lot
        if sym:
            LOT_SIZE_CACHE[sym] = lot
        return lot
    if sym and sym in csv_lots:
        lot = csv_lots[sym]
        LOT_SIZE_CACHE[sym] = lot
        if sec_id_str:
            LOT_SIZE_CACHE[sec_id_str] = lot
        return lot

    # Fallback heuristics for Indian markets if master not yet cached or synthetic symbol
    if "BANKNIFTY" in sym:
        lot = 15
    elif "FINNIFTY" in sym:
        lot = 25
    elif "MIDCPNIFTY" in sym:
        lot = 50
    elif "NIFTY" in sym:
        lot = 25
    elif "SENSEX" in sym:
        lot = 20
    elif "BANKEX" in sym:
        lot = 15
    # MCX Commodity heuristics
    elif "CRUDEOILM" in sym:
        lot = 10
    elif "CRUDEOIL" in sym or "CRUDE" in sym:
        lot = 100
    elif "NATGASMINI" in sym or "NATURALGASM" in sym:
        lot = 250
    elif "NATURALGAS" in sym or "NATGAS" in sym:
        lot = 1250
    elif "GOLDM" in sym:
        lot = 10
    elif "GOLDPETAL" in sym:
        lot = 1
    elif "GOLD" in sym:
        lot = 100
    elif "SILVERMIC" in sym:
        lot = 1
    elif "SILVERM" in sym:
        lot = 5
    elif "SILVER" in sym:
        lot = 30
    elif "COPPER" in sym:
        lot = 2500
    elif "ZINC" in sym or "LEAD" in sym or "ALUMINIUM" in sym:
        lot = 5000
    else:
        lot = 1

    if sym:
        LOT_SIZE_CACHE[sym] = lot
    if sec_id_str:
        LOT_SIZE_CACHE[sec_id_str] = lot
    return lot


def is_fno_symbol(symbol: str, exchange: Optional[str] = None, segment: Optional[str] = None) -> bool:
    """Determine whether an instrument is a derivative (Option or Future)."""
    ex = (exchange or "").upper().strip()
    seg = (segment or "").upper().strip()
    if ex in ("NFO", "BFO", "MCX") or seg in ("NSE_FNO", "BSE_FNO", "MCX_COMM"):
        return True
    if seg in ("NSE_EQ", "BSE_EQ", "EQ"):
        return False
    sym = (symbol or "").upper().strip()
    if re.search(r"\b(CALL|PUT|CE|PE|FUT|OPT)\b", sym) or re.search(r"\d+\s*(CE|PE|CALL|PUT)\b", sym):
        return True
    return False


def calculate_child_quantity(
    child: BrokerAccount,
    symbol: str,
    exchange: str,
    segment: Optional[str] = None,
    security_id: Optional[str] = None,
) -> int:
    """Calculate the exact order quantity for a child account based on instrument type and settings."""
    if is_fno_symbol(symbol, exchange, segment):
        lot_size = resolve_lot_size(symbol, security_id)
        lots = max(1, child.fixed_lots_fno or 1)
        return lots * lot_size
    else:
        return max(1, child.fixed_qty_equity or 10)


class DhanFanoutEngine:
    _instance = None

    @classmethod
    def get_instance(cls) -> "DhanFanoutEngine":
        if cls._instance is None:
            cls._instance = DhanFanoutEngine()
        return cls._instance

    async def execute_fanout_order(
        self,
        user_id: UUID,
        base_order: OrderRequest,
        source: str = "MANUAL",
        db: Optional[AsyncSession] = None,
    ) -> Dict[str, Any]:
        """
        Execute an order on the Master account and concurrently copy to all active Child accounts.
        """
        batch_id = f"CPY-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}-{uuid.uuid4().hex[:6].upper()}"
        logger.info(f"[{batch_id}] Starting copy trading fan-out for user {user_id} ({base_order.direction} {base_order.quantity}x {base_order.symbol})")

        # Query all broker accounts for the user
        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BrokerAccount).where(BrokerAccount.user_id == user_id)
            )
            accounts = result.scalars().all()

        if not accounts:
            logger.warning(f"[{batch_id}] No broker accounts found for user {user_id}")
            return {
                "batch_id": batch_id,
                "status": "NO_ACCOUNTS",
                "message": "No broker accounts linked",
                "master": None,
                "children": [],
            }

        # Resolve Master account
        master = next((a for a in accounts if a.account_role == "MASTER" and a.is_active), None)
        if not master:
            # Fallback to first active account
            master = next((a for a in accounts if a.is_active), None)

        if not master:
            logger.warning(f"[{batch_id}] No active Master account available for user {user_id}")
            return {
                "batch_id": batch_id,
                "status": "NO_ACTIVE_MASTER",
                "message": "No active Master account found",
                "master": None,
                "children": [],
            }

        # Resolve Child accounts eligible for copy
        children = [
            a for a in accounts
            if a.id != master.id
            and a.account_role == "CHILD"
            and a.is_active
            and a.is_copy_enabled
        ]

        logger.info(f"[{batch_id}] Master account: {master.account_name or master.client_id} ({master.id}), Active children: {len(children)}")

        # 1. Execute on Master account
        master_log_data = await self._execute_single_account(
            account=master,
            order=base_order,
            role="MASTER",
            batch_id=batch_id,
            source=source,
            user_id=user_id,
        )

        # 2. Concurrently execute on all active Child accounts
        child_tasks = []
        for child in children:
            child_qty = calculate_child_quantity(
                child=child,
                symbol=base_order.symbol,
                exchange=base_order.exchange,
                segment=base_order.segment,
            )

            # Order type mapping: force MARKET if configured, else match master
            child_order_type = "MARKET" if child.force_market_order else base_order.order_type
            child_price = 0.0 if child_order_type == "MARKET" else (base_order.price or 0.0)
            child_trigger = 0.0 if child_order_type == "MARKET" else (base_order.trigger_price or 0.0)

            child_order = OrderRequest(
                symbol=base_order.symbol,
                exchange=base_order.exchange,
                segment=base_order.segment,
                direction=base_order.direction,
                order_type=child_order_type,
                quantity=child_qty,
                price=child_price,
                trigger_price=child_trigger,
                product=base_order.product,
                client_order_id=f"{batch_id[:16]}-C{str(child.id)[:4]}",
            )

            child_tasks.append(
                self._execute_single_account(
                    account=child,
                    order=child_order,
                    role="CHILD",
                    batch_id=batch_id,
                    source=source,
                    user_id=user_id,
                )
            )

        child_logs = []
        if child_tasks:
            results = await asyncio.gather(*child_tasks, return_exceptions=True)
            for res in results:
                if isinstance(res, Exception):
                    logger.error(f"[{batch_id}] Child execution exception: {res}")
                    child_logs.append({
                        "status": "EXCEPTION",
                        "error_message": str(res),
                    })
                elif isinstance(res, dict):
                    child_logs.append(res)

        # 3. Publish real-time notification to Redis
        try:
            redis = get_redis()
            payload = {
                "event": "COPY_TRADE_FANOUT",
                "batch_id": batch_id,
                "symbol": base_order.symbol,
                "direction": base_order.direction,
                "source": source,
                "master": master_log_data,
                "children": child_logs,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis.publish(f"copy_trading:{user_id}", json.dumps(payload))
        except Exception as e:
            logger.debug(f"Redis broadcast failed for copy trade: {e}")

        return {
            "batch_id": batch_id,
            "status": "COMPLETED",
            "master": master_log_data,
            "children": child_logs,
            "total_children_attempted": len(children),
            "total_children_succeeded": sum(1 for c in child_logs if c.get("status") == "FILLED"),
        }

    async def _execute_single_account(
        self,
        account: BrokerAccount,
        order: OrderRequest,
        role: str,
        batch_id: str,
        source: str,
        user_id: UUID,
    ) -> Dict[str, Any]:
        """Execute order on an individual account and record the execution log in DB."""
        name = account.account_name or f"{account.client_id} ({role})"
        status = "PENDING"
        fill_price = None
        filled_qty = 0
        order_id = None
        error_msg = None

        freeze_limit = resolve_freeze_qty(order.symbol)
        if order.quantity > freeze_limit:
            logger.warning(
                f"[{batch_id}] Order qty {order.quantity} for {order.symbol} exceeds exchange freeze limit {freeze_limit}."
            )

        try:
            adapter = get_broker_adapter(account)
            resp: OrderResponse = await adapter.place_order(order)
            if resp and resp.broker_order_id:
                status = "FILLED"
                order_id = resp.broker_order_id
                fill_price = getattr(resp, "fill_price", None) or order.price or 0.0
                filled_qty = getattr(resp, "filled_quantity", None) or order.quantity
            else:
                status = "REJECTED"
                error_msg = resp.message if resp else "Order placement returned empty response"
        except Exception as e:
            status = "REJECTED"
            error_msg = str(e)
            logger.error(f"[{batch_id}] Order placement failed for {name}: {e}")

        # Persist log in its own database session for full isolation
        async with AsyncSessionLocal() as session:
            log_entry = CopyTradeLog(
                user_id=user_id,
                batch_id=batch_id,
                broker_account_id=account.id,
                account_role=role,
                account_name=name,
                symbol=order.symbol,
                exchange=order.exchange or "NSE",
                direction=order.direction,
                order_type=order.order_type,
                requested_quantity=order.quantity,
                filled_quantity=filled_qty,
                fill_price=fill_price,
                broker_order_id=order_id,
                status=status,
                error_message=error_msg,
                source=source,
            )
            session.add(log_entry)
            await session.commit()

        return {
            "account_id": str(account.id),
            "account_name": name,
            "role": role,
            "client_id": account.client_id,
            "quantity": order.quantity,
            "status": status,
            "broker_order_id": order_id,
            "fill_price": fill_price,
            "error_message": error_msg,
        }

    async def emergency_square_off_all_accounts(self, user_id: UUID) -> Dict[str, Any]:
        """
        Emergency Kill Switch: Square off all open positions across all active Dhan accounts for this user.
        """
        batch_id = f"KILL-ALL-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
        logger.warning(f"[{batch_id}] EMERGENCY SQUARE OFF TRIGGERED for user {user_id}")

        async with AsyncSessionLocal() as session:
            result = await session.execute(
                select(BrokerAccount).where(
                    BrokerAccount.user_id == user_id,
                    BrokerAccount.is_active == True,
                )
            )
            accounts = result.scalars().all()

        if not accounts:
            return {"status": "NO_ACCOUNTS", "total_orders_placed": 0, "details": []}

        orders_placed = []
        for acc in accounts:
            name = acc.account_name or acc.client_id
            try:
                adapter = get_broker_adapter(acc)
                positions = await adapter.get_positions()
                for pos in (positions or []):
                    net_qty = int(pos.get("net_qty") or pos.get("quantity") or 0)
                    if net_qty != 0:
                        exit_side = "SELL" if net_qty > 0 else "BUY"
                        exit_qty = abs(net_qty)
                        sym = pos.get("symbol") or pos.get("security_id") or ""
                        exch = pos.get("exchange") or "NSE"
                        seg = pos.get("segment") or ("NSE_FNO" if is_fno_symbol(sym) else "NSE_EQ")

                        orig_prod = (
                            pos.get("product_type")
                            or pos.get("productType")
                            or pos.get("product")
                            or ("MARGIN" if (is_fno_symbol(sym) or "MCX" in str(exch)) else "INTRADAY")
                        ).upper()

                        exit_req = OrderRequest(
                            symbol=sym,
                            exchange=exch,
                            segment=seg,
                            direction=exit_side,
                            order_type="MARKET",
                            quantity=exit_qty,
                            product=orig_prod,
                            price=0.0,
                            client_order_id=f"KILL-{batch_id[:12]}-{str(acc.id)[:4]}",
                        )

                        res = await self._execute_single_account(
                            account=acc,
                            order=exit_req,
                            role=acc.account_role or "CHILD",
                            batch_id=batch_id,
                            source="KILL",
                            user_id=user_id,
                        )
                        orders_placed.append(res)
            except Exception as e:
                logger.error(f"[{batch_id}] Emergency square off failed on account {name}: {e}")

        # Broadcast event
        try:
            redis = get_redis()
            payload = {
                "event": "EMERGENCY_SQUARE_OFF_COMPLETED",
                "batch_id": batch_id,
                "orders_placed": orders_placed,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            }
            await redis.publish(f"copy_trading:{user_id}", json.dumps(payload))
        except Exception:
            pass

        return {
            "batch_id": batch_id,
            "status": "COMPLETED",
            "total_accounts": len(accounts),
            "total_orders_placed": len(orders_placed),
            "details": orders_placed,
        }


fanout_engine = DhanFanoutEngine.get_instance()
