from datetime import date, datetime, timezone, timedelta
import unittest
import zoneinfo

from app.services.astro_service import (
    compute_kp_sub_lord,
    get_astro_snapshot,
    get_intraday_windows,
    get_planetary_telemetry,
    compute_active_aspects,
    get_astro_risk_multiplier,
    SPAN_NAKSHATRA,
    SPAN_PADA,
    NAKSHATRAS,
    SIGNS,
)
from app.schemas.astro import AstroMarketSignal, IntradayAstroResponse

IST = zoneinfo.ZoneInfo("Asia/Kolkata")


class AstroServiceTests(unittest.TestCase):
    def test_nakshatra_pada_boundary_divisions(self):
        """Verify mathematical integrity of the 27 Nakshatras and 4 Padas across 360 degrees."""
        # 0.0°: Ashwini Pada 1, Lord Ketu
        nak, lord, pada, sub = compute_kp_sub_lord(0.0)
        self.assertEqual(nak, "Ashwini")
        self.assertEqual(lord, "Ketu")
        self.assertEqual(pada, 1)
        self.assertEqual(sub, "Ketu")  # First sub in Ashwini must be Ketu

        # 3° 20' = 3.3333333°: Ashwini Pada 2
        nak, lord, pada, _ = compute_kp_sub_lord(3.35)
        self.assertEqual(nak, "Ashwini")
        self.assertEqual(pada, 2)

        # 13° 20' = 13.3333333°: Bharani Pada 1, Lord Venus
        nak, lord, pada, sub = compute_kp_sub_lord(13.34)
        self.assertEqual(nak, "Bharani")
        self.assertEqual(lord, "Venus")
        self.assertEqual(pada, 1)
        self.assertEqual(sub, "Venus")  # First sub in Bharani must be Venus

        # 359.9°: Revati Pada 4, Lord Mercury
        nak, lord, pada, _ = compute_kp_sub_lord(359.9)
        self.assertEqual(nak, "Revati")
        self.assertEqual(lord, "Mercury")
        self.assertEqual(pada, 4)

    def test_kp_sub_lord_vimshottari_sequence(self):
        """Verify that the KP Sub-Lords follow the Vimshottari cycle starting with the Nakshatra Lord."""
        # In Ashwini (Lord Ketu), the 9 subs must be:
        # 1. Ketu (span 7/120 * 13.3333° = 0.7778°) -> [0.0° to 0.7778°]
        # 2. Venus (span 20/120 * 13.3333° = 2.2222°) -> [0.7778° to 3.0000°]
        # 3. Sun (span 6/120 * 13.3333° = 0.6667°) -> [3.0000° to 3.6667°]
        # 4. Moon (span 10/120 * 13.3333° = 1.1111°) -> [3.6667° to 4.7778°]

        # Test at 0.5° (inside Ketu sub)
        _, _, _, sub1 = compute_kp_sub_lord(0.5)
        self.assertEqual(sub1, "Ketu")

        # Test at 1.5° (inside Venus sub)
        _, _, _, sub2 = compute_kp_sub_lord(1.5)
        self.assertEqual(sub2, "Venus")

        # Test at 3.2° (inside Sun sub)
        _, _, _, sub3 = compute_kp_sub_lord(3.2)
        self.assertEqual(sub3, "Sun")

        # Test at 4.0° (inside Moon sub)
        _, _, _, sub4 = compute_kp_sub_lord(4.0)
        self.assertEqual(sub4, "Moon")

    def test_planetary_telemetry_lahiri_positions(self):
        """Verify planetary telemetry output and Lahiri sidereal calculations."""
        ref_dt = datetime(2026, 11, 23, 10, 0, tzinfo=IST)
        telemetry = get_planetary_telemetry(ref_dt)

        self.assertEqual(len(telemetry), 12)  # 11 bodies + Ketu
        names = [p.name for p in telemetry]
        self.assertIn("Sun", names)
        self.assertIn("Moon", names)
        self.assertIn("Mars", names)
        self.assertIn("Rahu", names)
        self.assertIn("Ketu", names)

        # Verify Ketu is exactly 180 degrees opposite Rahu
        rahu = next(p for p in telemetry if p.name == "Rahu")
        ketu = next(p for p in telemetry if p.name == "Ketu")
        expected_ketu_lon = (rahu.longitude + 180.0) % 360.0
        self.assertAlmostEqual(ketu.longitude, expected_ketu_lon, places=3)

        # Verify Sun is in late Scorpio (around 216°)
        sun = next(p for p in telemetry if p.name == "Sun")
        self.assertEqual(sun.sign, "Scorpio")
        self.assertTrue(210.0 <= sun.longitude < 240.0)

    def test_aspects_calculation_and_orb_weighting(self):
        """Verify pairwise geometric aspects, orb intensity, and scoring."""
        ref_dt = datetime(2026, 11, 23, 10, 0, tzinfo=IST)
        telemetry = get_planetary_telemetry(ref_dt)
        aspects = compute_active_aspects(telemetry)

        # There should always be at least Rahu Opposition Ketu (180° exact)
        rahu_ketu_opp = next(
            (a for a in aspects if (a.body_a == "Rahu" and a.body_b == "Ketu") or (a.body_a == "Ketu" and a.body_b == "Rahu")),
            None,
        )
        self.assertIsNotNone(rahu_ketu_opp)
        self.assertEqual(rahu_ketu_opp.aspect_type, "OPPOSITION")
        self.assertAlmostEqual(rahu_ketu_opp.orb_deg, 0.0, places=2)
        self.assertTrue(rahu_ketu_opp.is_hard)

    def test_astro_snapshot_schema_and_regime(self):
        """Verify full AstroMarketSignal snapshot generation."""
        ref_dt = datetime(2026, 11, 23, 10, 0, tzinfo=IST)
        snapshot = get_astro_snapshot(ref_dt)

        self.assertIsInstance(snapshot, AstroMarketSignal)
        self.assertIn(snapshot.regime_bias, ["BULLISH_TAILWIND", "HIGH_VOLATILITY_CAUTION", "NEUTRAL_RANGE"])
        self.assertIsInstance(snapshot.volatility_alert, bool)
        self.assertIsInstance(snapshot.hard_aspect_score, float)
        self.assertIsInstance(snapshot.soft_aspect_score, float)
        self.assertIsInstance(snapshot.net_sentiment_score, float)
        self.assertIn(snapshot.risk_multiplier, [0.5, 1.0])

    def test_intraday_windows_scan_nse_session(self):
        """Verify scanning of NSE session (09:15-15:30 IST) for Moon transitions."""
        target_d = date(2026, 11, 23)
        res = get_intraday_windows(target_d)

        self.assertIsInstance(res, IntradayAstroResponse)
        self.assertEqual(res.date, "2026-11-23")
        self.assertEqual(res.session_open, "09:15 IST")
        self.assertEqual(res.session_close, "15:30 IST")
        self.assertGreater(res.total_windows, 0)

        # Verify all window timestamps fall within 09:15 to 15:30 IST
        for w in res.windows:
            dt = datetime.fromisoformat(w.timestamp)
            self.assertEqual(dt.date(), target_d)
            self.assertTrue(
                (dt.hour > 9 or (dt.hour == 9 and dt.minute >= 15)) and
                (dt.hour < 15 or (dt.hour == 15 and dt.minute <= 30))
            )
            self.assertIn(w.event_type, ["MOON_NAKSHATRA_SHIFT", "KP_SUB_LORD_SHIFT"])
            self.assertIn(w.weight, ["HIGH", "MEDIUM", "LOW"])

    def test_fastapi_endpoints(self):
        """Verify GET /api/v1/astro/snapshot and GET /api/v1/astro/intraday-windows."""
        from fastapi.testclient import TestClient
        from app.main import app

        client = TestClient(app)

        # 1. Test /api/v1/astro/snapshot
        snap_res = client.get("/api/v1/astro/snapshot")
        self.assertEqual(snap_res.status_code, 200)
        data = snap_res.json()
        self.assertIn("regime_bias", data)
        self.assertIn("planets", data)
        self.assertEqual(len(data["planets"]), 12)

        # 2. Test /api/v1/astro/intraday-windows
        win_res = client.get("/api/v1/astro/intraday-windows?date_str=2026-11-23")
        self.assertEqual(win_res.status_code, 200)
        win_data = win_res.json()
        self.assertEqual(win_data["date"], "2026-11-23")
        self.assertIn("windows", win_data)


if __name__ == "__main__":
    unittest.main()
