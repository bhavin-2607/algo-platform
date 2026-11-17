import unittest
from unittest.mock import AsyncMock, patch, MagicMock
import uuid

from app.models.broker import BrokerAccount, BrokerName
from app.broker.base import OrderRequest, OrderResponse
from app.services.dhan_fanout_engine import (
    resolve_lot_size,
    is_fno_symbol,
    calculate_child_quantity,
    DhanFanoutEngine,
)


class TestDhanCopyTrading(unittest.IsolatedAsyncioTestCase):

    def test_is_fno_symbol(self):
        """Verify derivative identification for Options, Futures, and Equities."""
        self.assertTrue(is_fno_symbol("NIFTY 17 NOV 25300 CALL"))
        self.assertTrue(is_fno_symbol("BANKNIFTY 23 NOV 52000 PE"))
        self.assertTrue(is_fno_symbol("AUBANK 23 NOV 950 CALL"))
        self.assertTrue(is_fno_symbol("RELIANCE24NOVFUT", exchange="NFO"))
        self.assertTrue(is_fno_symbol("NIFTY25000CE"))
        self.assertFalse(is_fno_symbol("RELIANCE", exchange="NSE", segment="NSE_EQ"))
        self.assertFalse(is_fno_symbol("ICICIBANK", exchange="NSE", segment="NSE_EQ"))

    def test_lot_size_resolution(self):
        """Verify lot size resolution for index and stock derivatives."""
        self.assertEqual(resolve_lot_size("NIFTY 25000 CE"), 25)
        self.assertEqual(resolve_lot_size("BANKNIFTY 52000 PE"), 15)
        self.assertEqual(resolve_lot_size("FINNIFTY 23500 CE"), 25)
        self.assertEqual(resolve_lot_size("MIDCPNIFTY 12000 PE"), 50)

    def test_child_quantity_calculation(self):
        """Verify fixed quantity calculation for equities and fixed lots for F&O."""
        child_acc = BrokerAccount(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            broker=BrokerName.dhan,
            client_id="CHILD123",
            account_role="CHILD",
            fixed_qty_equity=50,
            fixed_lots_fno=2,
        )

        # Equity order -> returns fixed_qty_equity
        equity_qty = calculate_child_quantity(
            child=child_acc,
            symbol="RELIANCE",
            exchange="NSE",
            segment="NSE_EQ",
        )
        self.assertEqual(equity_qty, 50)

        # NIFTY Option -> 2 lots * 25 = 50
        nifty_qty = calculate_child_quantity(
            child=child_acc,
            symbol="NIFTY 25000 CE",
            exchange="NFO",
            segment="NSE_FNO",
        )
        self.assertEqual(nifty_qty, 50)

        # BANKNIFTY Option -> 2 lots * 15 = 30
        bn_qty = calculate_child_quantity(
            child=child_acc,
            symbol="BANKNIFTY 52000 PE",
            exchange="NFO",
            segment="NSE_FNO",
        )
        self.assertEqual(bn_qty, 30)

    @patch("app.services.dhan_fanout_engine.get_broker_adapter")
    async def test_fanout_execution_success(self, mock_get_adapter):
        """Verify fanout engine executes on Master and concurrently duplicates to Child accounts."""
        user_id = uuid.uuid4()
        master_id = uuid.uuid4()
        child1_id = uuid.uuid4()
        child2_id = uuid.uuid4()

        master = BrokerAccount(
            id=master_id,
            user_id=user_id,
            broker=BrokerName.dhan,
            client_id="MASTER_01",
            account_role="MASTER",
            account_name="Master Account",
            is_active=True,
            paper_trading=True,
        )
        child1 = BrokerAccount(
            id=child1_id,
            user_id=user_id,
            broker=BrokerName.dhan,
            client_id="CHILD_01",
            account_role="CHILD",
            account_name="Child Account 1",
            is_active=True,
            is_copy_enabled=True,
            paper_trading=True,
            fixed_qty_equity=25,
            force_market_order=True,
        )
        child2 = BrokerAccount(
            id=child2_id,
            user_id=user_id,
            broker=BrokerName.dhan,
            client_id="CHILD_02",
            account_role="CHILD",
            account_name="Child Account 2",
            is_active=True,
            is_copy_enabled=True,
            paper_trading=True,
            fixed_qty_equity=100,
            force_market_order=True,
        )

        mock_adapter = MagicMock()
        mock_adapter.place_order = AsyncMock(side_effect=[
            OrderResponse(broker_order_id="ORD-MASTER-001", status="PLACED"),
            OrderResponse(broker_order_id="ORD-CHILD-001", status="PLACED"),
            OrderResponse(broker_order_id="ORD-CHILD-002", status="PLACED"),
        ])
        mock_get_adapter.return_value = mock_adapter

        engine = DhanFanoutEngine.get_instance()

        # Mock database queries
        mock_session = AsyncMock()
        mock_session.add = MagicMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [master, child1, child2]
        mock_session.execute.return_value = mock_result

        with patch("app.services.dhan_fanout_engine.AsyncSessionLocal") as mock_session_local, \
             patch("app.services.dhan_fanout_engine.get_redis") as mock_redis:
            mock_session_local.return_value.__aenter__.return_value = mock_session
            mock_redis_client = MagicMock()
            mock_redis_client.publish = AsyncMock()
            mock_redis.return_value = mock_redis_client

            order_req = OrderRequest(
                symbol="TCS",
                exchange="NSE",
                segment="NSE_EQ",
                direction="BUY",
                order_type="MARKET",
                quantity=10,
                price=3500.0,
            )

            res = await engine.execute_fanout_order(
                user_id=user_id,
                base_order=order_req,
                source="MANUAL",
            )

            self.assertEqual(res["status"], "COMPLETED")
            self.assertEqual(res["master"]["broker_order_id"], "ORD-MASTER-001")
            self.assertEqual(len(res["children"]), 2)
            self.assertEqual(res["total_children_succeeded"], 2)

    async def test_admin_get_active_dhan_credentials(self):
        """Verify _get_active_dhan_credentials successfully queries BrokerName.dhan without invalid enum error."""
        from app.api.routes.admin import _get_active_dhan_credentials

        mock_db = AsyncMock()
        mock_acc = BrokerAccount(
            id=uuid.uuid4(),
            user_id=uuid.uuid4(),
            broker=BrokerName.dhan,
            client_id="1100354422",
            account_role="MASTER",
            account_name="Primary Dhan",
            is_active=True,
        )
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = [mock_acc]
        mock_db.execute.return_value = mock_result

        client_id, token, name = await _get_active_dhan_credentials(mock_db)
        self.assertEqual(client_id, "1100354422")
        self.assertEqual(name, "Primary Dhan")


if __name__ == "__main__":
    unittest.main()
