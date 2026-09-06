from django.test import SimpleTestCase

from .relationship_detail import (
    _align_series,
    _compare,
    _find_temperature_humidity_pair,
    _vpd_kpa,
)


class RelationshipDiagnosticsTests(SimpleTestCase):
    def test_align_series_groups_different_sensor_timestamps_into_same_bucket(self):
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

    def test_alert_operators(self):
        self.assertTrue(_compare(30.0, "gt", 28.0))
        self.assertTrue(_compare(28.0, "gte", 28.0))
        self.assertTrue(_compare(20.0, "lt", 21.0))
        self.assertTrue(_compare(20.0, "lte", 20.0))
        self.assertFalse(_compare(None, "gt", 1.0))
