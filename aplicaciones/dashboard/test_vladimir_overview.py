from datetime import timedelta

from django.template.loader import get_template
from django.test import SimpleTestCase
from django.utils import timezone

from .vladimir_overview import _enrich_health, _location_groups, _type_groups


class VladimirOverviewTests(SimpleTestCase):
    def test_health_groups_sensors_by_telemetry_freshness(self):
        now = timezone.now()
        sensors = [
            {"id": "fresh", "last_seen_at": now - timedelta(minutes=10)},
            {"id": "delayed", "last_seen_at": now - timedelta(minutes=90)},
            {"id": "offline", "last_seen_at": now - timedelta(hours=8)},
        ]

        health = _enrich_health(sensors, freshness_minutes=30)

        self.assertEqual(health["online"], 1)
        self.assertEqual(health["delayed"], 1)
        self.assertEqual(health["offline"], 1)
        self.assertEqual(health["total"], 3)
        self.assertAlmostEqual(health["reporting_pct"], 100 / 3)

    def test_location_groups_use_asset_when_location_is_missing(self):
        sensors = [
            {
                "id": "a",
                "name": "Sensor A",
                "location": "Greenhouse 1",
                "asset_name": "Tomatoes",
                "base_station_name": "Base north",
            },
            {
                "id": "b",
                "name": "Sensor B",
                "location": None,
                "asset_name": "Warehouse",
                "base_station_name": "Base north",
            },
            {
                "id": "c",
                "name": "Sensor C",
                "location": None,
                "asset_name": None,
                "base_station_name": None,
            },
        ]

        groups = _location_groups(sensors)
        names = {group["name"] for group in groups}

        self.assertEqual(names, {"Greenhouse 1", "Warehouse", "Sin ubicación asignada"})

    def test_sensor_type_mix_is_percentage_of_active_inventory(self):
        sensors = [
            {"type_name": "Aranet4"},
            {"type_name": "Aranet4"},
            {"type_name": "Soil"},
        ]

        groups = _type_groups(sensors)

        self.assertEqual(groups[0]["name"], "Aranet4")
        self.assertEqual(groups[0]["count"], 2)
        self.assertAlmostEqual(groups[0]["pct"], 200 / 3)

    def test_vladimir_template_compiles(self):
        template = get_template("dashboard/vladimir.html")
        self.assertIsNotNone(template)
