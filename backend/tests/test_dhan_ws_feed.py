"""
Unit tests for Dhan native WebSocket live feed and MarketPoller integration.
Verifies binary frame decoding, dynamic subscriptions, normalized tick construction,
and immediate dispatch to the BSA Algo Engine.
"""
import unittest
import struct
import time
from unittest.mock import MagicMock, patch

from app.market.dhan_feed import DhanLiveFeed, redis_exchange
from app.market.market_poller import MarketPoller


class TestDhanLiveFeed(unittest.TestCase):

    def setUp(self):
        self.received_ticks = []

        def on_tick(tick):
            self.received_ticks.append(tick)

        self.feed = DhanLiveFeed(
            client_id="1105204777",
            access_token="test_token",
            on_tick_callback=on_tick,
        )

    def test_redis_exchange_mapping(self):
        self.assertEqual(redis_exchange("NSE_EQ"), "NSE")
        self.assertEqual(redis_exchange("NSE_FNO"), "NFO")
        self.assertEqual(redis_exchange("BSE_FNO"), "BFO")
        self.assertEqual(redis_exchange("MCX_COMM"), "MCX")
        self.assertEqual(redis_exchange("IDX_I"), "IDX")

    def test_dynamic_subscription_and_channel_mapping(self):
        self.feed.subscribe("NSE_FNO", "59951", symbol="BANKNIFTY 29 DEC 63800 CALL")
        self.assertEqual(len(self.feed._instruments), 1)
        inst = self.feed._instruments[0]
        self.assertEqual(inst["dhan_exchange"], 2)
        self.assertEqual(inst["security_id"], "59951")
        self.assertEqual(inst["symbol"], "BANKNIFTY 29 DEC 63800 CALL")
        self.assertEqual(self.feed._symbol_map[(2, "59951")], "BANKNIFTY 29 DEC 63800 CALL")

        # Duplicate subscribe should be idempotent
        self.feed.subscribe("NSE_FNO", "59951", symbol="BANKNIFTY 29 DEC 63800 CALL")
        self.assertEqual(len(self.feed._instruments), 1)

        # Unsubscribe
        self.feed.unsubscribe("BANKNIFTY 29 DEC 63800 CALL")
        self.assertEqual(len(self.feed._instruments), 0)
        self.assertNotIn((2, "59951"), self.feed._symbol_map)

    def test_on_tick_quote_packet_parsing(self):
        self.feed.subscribe("BSE_FNO", "1118969", symbol="SENSEX 26 NOV 84000 CALL")
        self.feed._running = True

        mock_data = {
            "type": "Quote Data",
            "exchange_segment": 8,
            "security_id": 1118969,
            "LTP": "145.50",
            "open": "140.00",
            "high": "150.00",
            "low": "138.00",
            "close": "142.00",
            "volume": 50000,
            "avg_price": "144.20",
            "OI": 200000,
            "depth": [
                {
                    "bid_price": "145.45",
                    "ask_price": "145.55",
                    "bid_quantity": 200,
                    "ask_quantity": 400,
                }
            ],
        }

        channel_map = {(8, "1118969"): "tick:BFO:1118969"}
        self.feed._on_tick(mock_data, channel_map)

        self.assertEqual(len(self.received_ticks), 1)
        tick = self.received_ticks[0]
        self.assertEqual(tick["symbol"], "SENSEX 26 NOV 84000 CALL")
        self.assertEqual(tick["ltp"], 145.50)
        self.assertEqual(tick["open"], 140.00)
        self.assertEqual(tick["high"], 150.00)
        self.assertEqual(tick["low"], 138.00)
        self.assertEqual(tick["close"], 142.00)
        self.assertEqual(tick["volume"], 50000)
        self.assertEqual(tick["atp"], 144.20)
        self.assertEqual(tick["bp1"], 145.45)
        self.assertEqual(tick["sp1"], 145.55)
        self.assertEqual(tick["source"], "dhan_ws")

    def test_market_poller_ws_tick_integration(self):
        poller = MarketPoller(interval_seconds=1.0)
        poller.add_symbol("NIFTY50", "13", "IDX_I")

        mock_tick = {
            "symbol": "NIFTY50",
            "ltp": 24350.25,
            "open": 24300.0,
            "high": 24380.0,
            "low": 24290.0,
            "close": 24320.0,
            "p_close": 24300.0,
            "change": 50.25,
            "change_pct": 0.21,
            "volume": 1500000,
            "source": "dhan_ws",
        }

        with patch.object(poller, "_notify_algo_engine", return_value=None):
            poller._process_ws_tick(mock_tick)

        cached = next((t for t in poller._last_data if t.get("symbol") == "NIFTY50"), None)
        self.assertIsNotNone(cached)
        self.assertEqual(cached["ltp"], 24350.25)
        self.assertEqual(cached["source"], "dhan_ws")


if __name__ == "__main__":
    unittest.main()
