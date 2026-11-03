import unittest

from app.market.history import resolve_security


class HistoryResolveTests(unittest.TestCase):
    def test_reliance_equity_uses_underlying_symbol(self):
        row = resolve_security("RELIANCE", "NSE")
        self.assertEqual(row["security_id"], "2885")
        self.assertEqual(row["exchange_segment"], "NSE_EQ")
        self.assertEqual(row["instrument"], "EQUITY")


if __name__ == "__main__":
    unittest.main()
