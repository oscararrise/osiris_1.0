from datetime import UTC, datetime

from django.test import SimpleTestCase

from .models import AgronomicRelationshipAlert
from .relationship_detail import (
    _alert_evaluation,
    _align_series,
    _analysis_summary,
    _compare,
    _find_temperature_humidity_pair,
    _pearson_correlation,
    _vpd_kpa,
)


class RelationshipDiagnosticsTests(SimpleTestCase):
    def test_align_series_groups_timestamps_and_keeps_source_times(self):
        variables = [
            {"key": "sensor-a::temperature:0"},
            {"key": "sensor-b::humidity:0"},
        ]
        series = {
            "sensor-a::temperature:0": [
                {"measured_at": "2026-09-06T12:00:15+00:00", "value": 24.0},
                {"measured_at": "2026-09-06T12:04:10+00:00", "value": 26.0},
            ],
            "sensor-b::humidity:0": [
                {"measured_at": "2026-09-06T12:03:40+00:00", "value": 70.0},
            ],
        }

        rows = _align_series(variables, series, 300)

        self.assertEqual(len(rows), 1)
        self.assertAlmostEqual(rows[0]["values"]["sensor-a::temperature:0"], 25.0)
        self.assertAlmostEqual(rows[0]["values"]["sensor-b::humidity:0"], 70.0)
        self.assertEqual(
            rows[0]["source_times"]["sensor-a::temperature:0"],
            "2026-09-06T12:04:10+00:00",
        )
        self.assertEqual(
            rows[0]["source_times"]["sensor-b::humidity:0"],
            "2026-09-06T12:03:40+00:00",
        )

    def test_vpd_calculation_for_25c_and_60_percent_rh(self):
        value = _vpd_kpa(25.0, 60.0)
        self.assertIsNotNone(value)
        self.assertAlmostEqual(value, 1.267, places=2)

    def test_vpd_rejects_invalid_relative_humidity(self):
        self.assertIsNone(_vpd_kpa(25.0, 120.0))

    def test_temperature_humidity_pair_ignores_soil_metrics(self):
        variables = [
            {
                "key": "a::soil_temperature:0",
                "metric_id": "soil_temperature",
                "name": "Soil Temperature",
                "available": True,
            },
            {
                "key": "b::air_temperature:0",
                "metric_id": "air_temperature",
                "name": "Air Temperature",
                "available": True,
            },
            {
                "key": "c::relative_humidity:0",
                "metric_id": "relative_humidity",
                "name": "Relative Humidity",
                "available": True,
            },
        ]

        temperature, humidity = _find_temperature_humidity_pair(variables)

        self.assertEqual(temperature["key"], "b::air_temperature:0")
        self.assertEqual(humidity["key"], "c::relative_humidity:0")

    def test_pressure_and_temperature_do_not_enable_vpd(self):
        variables = [
            {
                "key": "a::atmospheric_pressure:0",
                "metric_id": "atmospheric_pressure",
                "name": "Atmospheric Pressure",
                "available": True,
            },
            {
                "key": "a::temperature:0",
                "metric_id": "temperature",
                "name": "Temperature",
                "available": True,
            },
        ]

        self.assertIsNone(_find_temperature_humidity_pair(variables))

        rows = [
            {
                "measured_at": "2026-09-06T12:00:00+00:00",
                "values": {
                    "a::atmospheric_pressure:0": 1008.0,
                    "a::temperature:0": 24.0,
                },
                "source_times": {},
            },
            {
                "measured_at": "2026-09-06T12:05:00+00:00",
                "values": {
                    "a::atmospheric_pressure:0": 1009.0,
                    "a::temperature:0": 25.0,
                },
                "source_times": {},
            },
        ]
        analysis = _analysis_summary(variables, rows, None)
        vpd = next(item for item in analysis["capabilities"] if item["key"] == "vpd")

        self.assertFalse(vpd["available"])
        self.assertIn("humedad relativa", vpd["reason"])

    def test_pearson_correlation_describes_aligned_pairs(self):
        self.assertAlmostEqual(
            _pearson_correlation([(1.0, 2.0), (2.0, 4.0), (3.0, 6.0)]),
            1.0,
        )
        self.assertIsNone(_pearson_correlation([(1.0, 2.0), (2.0, 4.0)]))

    def test_alert_operators(self):
        self.assertTrue(_compare(30.0, "gt", 28.0))
        self.assertTrue(_compare(28.0, "gte", 28.0))
        self.assertTrue(_compare(20.0, "lt", 21.0))
        self.assertTrue(_compare(20.0, "lte", 20.0))
        self.assertFalse(_compare(None, "gt", 1.0))

    def test_alert_preview_requires_fresh_synchronized_data(self):
        alert = AgronomicRelationshipAlert(
            variable_a_key="a::temperature:0",
            operator_a="gt",
            threshold_a=28.0,
            variable_b_key="b::humidity:0",
            operator_b="gt",
            threshold_b=85.0,
            logic="and",
            duration_minutes=10,
        )
        now = datetime(2026, 9, 6, 12, 15, tzinfo=UTC)
        rows = [
            {
                "measured_at": "2026-09-06T12:05:00+00:00",
                "values": {
                    "a::temperature:0": 29.0,
                    "b::humidity:0": 88.0,
                },
                "source_times": {
                    "a::temperature:0": "2026-09-06T12:09:30+00:00",
                    "b::humidity:0": "2026-09-06T12:09:10+00:00",
                },
            },
            {
                "measured_at": "2026-09-06T12:10:00+00:00",
                "values": {
                    "a::temperature:0": 29.5,
                    "b::humidity:0": 89.0,
                },
                "source_times": {
                    "a::temperature:0": "2026-09-06T12:14:20+00:00",
                    "b::humidity:0": "2026-09-06T12:14:00+00:00",
                },
            },
        ]

        evaluation = _alert_evaluation(
            alert,
            rows,
            300,
            now=now,
            freshness_minutes=15,
        )

        self.assertTrue(evaluation["data_fresh"])
        self.assertTrue(evaluation["condition_a_met"])
        self.assertTrue(evaluation["condition_b_met"])
        self.assertTrue(evaluation["triggered_preview"])
        self.assertEqual(evaluation["sustained_minutes"], 10.0)

    def test_alert_preview_blocks_stale_variable(self):
        alert = AgronomicRelationshipAlert(
            variable_a_key="a::temperature:0",
            operator_a="gt",
            threshold_a=28.0,
            variable_b_key="b::humidity:0",
            operator_b="gt",
            threshold_b=85.0,
            logic="and",
            duration_minutes=5,
        )
        now = datetime(2026, 9, 6, 12, 30, tzinfo=UTC)
        rows = [
            {
                "measured_at": "2026-09-06T12:25:00+00:00",
                "values": {
                    "a::temperature:0": 30.0,
                    "b::humidity:0": 90.0,
                },
                "source_times": {
                    "a::temperature:0": "2026-09-06T12:29:00+00:00",
                    "b::humidity:0": "2026-09-06T12:00:00+00:00",
                },
            }
        ]

        evaluation = _alert_evaluation(
            alert,
            rows,
            300,
            now=now,
            freshness_minutes=15,
        )

        self.assertFalse(evaluation["data_fresh"])
        self.assertFalse(evaluation["triggered_preview"])
        self.assertIn("desactualizada", evaluation["stale_reason"])
