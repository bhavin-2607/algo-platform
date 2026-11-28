import unittest
from app.api.routes.market import _search_instruments_sync, resolve_exchange_segment, _scrip_frame


class TestUnrestrictedSymbolSearch(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.df = _scrip_frame()

    def test_total_instruments_loaded(self):
        """Scrip master must contain all market instruments (>200,000)."""
        self.assertGreater(len(self.df), 200000)

    def test_sensex_index_search(self):
        """Searching SENSEX must rank the BSE spot index first with segment IDX_I."""
        results = _search_instruments_sync("SENSEX", limit=10)
        self.assertTrue(len(results) > 0)
        top = results[0]
        self.assertEqual(top["symbol"], "SENSEX")
        self.assertEqual(top["exchange_segment"], "IDX_I")
        self.assertEqual(top["exchange"], "BSE")
        self.assertEqual(top["security_id"], "51")

    def test_sensex_futures_search(self):
        """Searching SENSEX FUT must return BSE F&O futures contracts."""
        results = _search_instruments_sync("SENSEX FUT", limit=5)
        self.assertTrue(len(results) > 0)
        top = results[0]
        self.assertIn("FUT", top["symbol"])
        self.assertEqual(top["exchange_segment"], "BSE_FNO")
        self.assertEqual(top["exchange"], "BSE")

    def test_sensex_options_search(self):
        """Searching SENSEX 80000 CE must return SENSEX option contracts."""
        results = _search_instruments_sync("SENSEX 80000 CE", limit=5)
        self.assertTrue(len(results) > 0)
        top = results[0]
        self.assertIn("80000", top["symbol"])
        self.assertEqual(top["exchange_segment"], "BSE_FNO")
        self.assertEqual(top["exchange"], "BSE")

    def test_equity_cash_search(self):
        """Searching TCS must return NSE cash equity first, then BSE, then futures."""
        results = _search_instruments_sync("TCS", limit=10)
        self.assertTrue(len(results) >= 2)
        nse_eq = results[0]
        self.assertEqual(nse_eq["symbol"], "TCS")
        self.assertEqual(nse_eq["exchange_segment"], "NSE_EQ")
        self.assertEqual(nse_eq["exchange"], "NSE")
        self.assertEqual(nse_eq["series"], "EQ")

        bse_eq = results[1]
        self.assertEqual(bse_eq["symbol"], "TCS")
        self.assertEqual(bse_eq["exchange_segment"], "BSE_EQ")
        self.assertEqual(bse_eq["exchange"], "BSE")

    def test_mcx_commodity_search(self):
        """Searching GOLD must return MCX near-month commodity futures."""
        results = _search_instruments_sync("GOLD", limit=5)
        self.assertTrue(len(results) > 0)
        top = results[0]
        self.assertTrue(top["symbol"].startswith("GOLD"))
        self.assertIn("FUT", top["symbol"])
        self.assertEqual(top["exchange_segment"], "MCX_COMM")
        self.assertEqual(top["exchange"], "MCX")

    def test_currency_derivatives_search(self):
        """Searching USDINR must return currency contracts with *_CURR segment."""
        results = _search_instruments_sync("USDINR", limit=5)
        self.assertTrue(len(results) > 0)
        top = results[0]
        self.assertTrue(top["symbol"].startswith("USDINR"))
        self.assertIn(top["exchange_segment"], ("BSE_CURR", "NSE_CURR"))

    def test_nifty_option_strike_search(self):
        """Searching NIFTY 24500 CE must return Nifty call options sorted by expiry."""
        results = _search_instruments_sync("NIFTY 24500 CE", limit=5)
        self.assertTrue(len(results) > 0)
        top = results[0]
        self.assertTrue(top["symbol"].startswith("NIFTY"))
        self.assertIn("24500", top["symbol"])
        self.assertEqual(top["exchange_segment"], "NSE_FNO")
        self.assertEqual(top["exchange"], "NSE")


if __name__ == "__main__":
    unittest.main()
