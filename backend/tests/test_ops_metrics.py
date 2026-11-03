import unittest
from unittest.mock import patch

from app.core.ops_metrics import OpsCollector, snapshot_from_values


class OpsMetricsTests(unittest.TestCase):
    def test_snapshot_flags(self):
        snap = snapshot_from_values(True, False, 3)
        self.assertEqual(snap, {"feed_stale": 1, "live_kill": 0, "order_rejects": 3})

    def test_collector_exposes_three_series(self):
        with patch("app.core.ops_metrics.read_ops_snapshot", return_value=snapshot_from_values(True, True, 2)):
            families = list(OpsCollector().collect())
        names = [family.name for family in families]
        self.assertEqual(names, ["algo_feed_stale", "algo_live_kill", "algo_order_rejects"])
        self.assertEqual(families[0].samples[0].value, 1)
        self.assertEqual(families[2].samples[0].value, 2)


if __name__ == "__main__":
    unittest.main()
