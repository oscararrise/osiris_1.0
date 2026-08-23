from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from django.test import SimpleTestCase

from .vladimir_analytics import (
    _choose_comparison_metric,
    _correlation,
    _distribution_profile,
    _hourly_profile,
    _percentile,
)


class VladimirAnalyticsTests(SimpleTestCase):
    def setUp(self):
        self.start = datetime(2026, 8, 20, 0, 0, tzinfo=ZoneInfo("America/Bogota"))

    def _series(self, values):
        return [
            {
                "measured_at": self.start + timedelta(hours=index),
                "value": value,
                "sample_count": 1,
            }
            for index, value in enumerate(values)
        ]

    def test_percentile_uses_linear_interpolation(self):
        values = [1.0, 2.0, 3.0, 4.0, 5.0]
        self.assertEqual(_percentile(values, 0.5), 3.0)
        self.assertEqual(_percentile(values, 0.25), 2.0)
        self.assertEqual(_percentile(values, 0.75), 4.0)

    def test_correlation_detects_strong_positive_relationship(self):
        primary = self._series([1, 2, 3, 4, 5])
        secondary = self._series([2, 4, 6, 8, 10])
        result = _correlation(primary, secondary)
        self.assertAlmostEqual(result["coefficient"], 1.0, places=6)
        self.assertIn("Muy fuerte", result["strength"])
        self.assertEqual(len(result["pairs"]), 5)

    def test_correlation_only_uses_overlapping_buckets(self):
        primary = self._series([1, 2, 3, 4])
        secondary = self._series([4, 3, 2, 1])
        secondary[0]["measured_at"] = self.start - timedelta(hours=1)
        result = _correlation(primary, secondary)
        self.assertEqual(len(result["pairs"]), 3)

    def test_distribution_profile_flags_iqr_outlier(self):
        series = self._series([10, 10, 11, 10, 9, 10, 11, 10, 50])
        profile = _distribution_profile(series)
        self.assertEqual(profile["median"], 10.0)
        self.assertGreaterEqual(profile["outlier_count"], 1)
        self.assertTrue(profile["histogram"])

    def test_hourly_profile_preserves_all_24_hours(self):
        profile = _hourly_profile(self._series([10, 20, 30]))
        self.assertEqual(len(profile), 24)
        self.assertEqual(profile[0]["average"], 10.0)
        self.assertEqual(profile[1]["average"], 20.0)
        self.assertIsNone(profile[6]["average"])

    def test_comparison_metric_never_reuses_primary_metric(self):
        metrics = [
            {"id": "soil_moisture", "name": "Soil moisture", "probe_no": 1},
            {"id": "temperature", "name": "Temperature", "probe_no": 1},
        ]
        selected = _choose_comparison_metric(
            metrics,
            "soil_moisture",
            1,
            "soil_moisture",
            "1",
        )
        self.assertEqual(selected["id"], "temperature")
