from decimal import Decimal
from datetime import timedelta

from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from aplicaciones.core.models import Client

from .models import ClientSensor, SensorPlacement, Zone
from .services import assign_sensor_location


class SensorConfigurationModelTests(TestCase):
    def setUp(self):
        self.client = Client.objects.create(name="Aranet Demo", slug="aranet-demo")
        self.other_client = Client.objects.create(name="Other Client", slug="other-client")
        self.greenhouse = Zone.objects.create(
            client=self.client,
            name="Invernadero A",
            code="invernadero-a",
            zone_type=Zone.ZoneType.GREENHOUSE,
        )
        self.sector = Zone.objects.create(
            client=self.client,
            name="Zona A1",
            code="zona-a1",
            zone_type=Zone.ZoneType.SECTOR,
            parent=self.greenhouse,
        )
        self.sensor = ClientSensor.objects.create(
            client=self.client,
            external_sensor_id="aranet-001",
            sensor_name="Cuarto frío",
            sensor_detail="Aranet4 · temperatura, humedad y CO2",
        )

    def test_zone_parent_must_belong_to_same_client(self):
        foreign_parent = Zone.objects.create(
            client=self.other_client,
            name="Foreign Greenhouse",
            code="foreign-greenhouse",
            zone_type=Zone.ZoneType.GREENHOUSE,
        )
        zone = Zone(
            client=self.client,
            name="Invalid child",
            code="invalid-child",
            parent=foreign_parent,
        )

        with self.assertRaises(ValidationError):
            zone.full_clean()

    def test_zone_hierarchy_resolves_farm_or_greenhouse(self):
        self.assertEqual(self.sector.nearest_facility(), self.greenhouse)
        self.assertEqual(self.sector.full_name, "Invernadero A / Zona A1")

    def test_coordinates_must_be_supplied_as_pair(self):
        placement = SensorPlacement(
            sensor=self.sensor,
            zone=self.sector,
            latitude=Decimal("4.6872531"),
            valid_from=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            placement.full_clean()

    def test_placement_zone_must_match_sensor_client(self):
        foreign_zone = Zone.objects.create(
            client=self.other_client,
            name="Foreign zone",
            code="foreign-zone",
        )
        placement = SensorPlacement(
            sensor=self.sensor,
            zone=foreign_zone,
            valid_from=timezone.now(),
        )

        with self.assertRaises(ValidationError):
            placement.full_clean()

    def test_assign_sensor_location_closes_previous_placement(self):
        first_time = timezone.now() - timedelta(hours=1)
        second_time = timezone.now()

        first = assign_sensor_location(
            sensor=self.sensor,
            zone=self.sector,
            city="Bogotá",
            department="Cundinamarca",
            latitude=Decimal("4.6872531"),
            longitude=Decimal("-74.0628734"),
            altitude_m=Decimal("2630.00"),
            effective_at=first_time,
        )
        second = assign_sensor_location(
            sensor=self.sensor,
            zone=self.greenhouse,
            city="Bogotá",
            department="Cundinamarca",
            latitude=Decimal("4.6873000"),
            longitude=Decimal("-74.0628000"),
            altitude_m=Decimal("2631.00"),
            effective_at=second_time,
        )

        first.refresh_from_db()
        self.assertEqual(first.valid_until, second_time)
        self.assertIsNone(second.valid_until)
        self.assertEqual(self.sensor.placements.count(), 2)
        self.assertEqual(second.farm_or_greenhouse, self.greenhouse)

    def test_assign_sensor_location_rejects_foreign_zone(self):
        foreign_zone = Zone.objects.create(
            client=self.other_client,
            name="Foreign zone",
            code="foreign-zone-service",
        )

        with self.assertRaises(ValidationError):
            assign_sensor_location(sensor=self.sensor, zone=foreign_zone)
