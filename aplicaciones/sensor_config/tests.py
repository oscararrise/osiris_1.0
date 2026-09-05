from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from aplicaciones.core.models import (
    AccessLevel,
    Client,
    ClientMembership,
    ClientModule,
    PlatformModule,
)

from .models import ClientSensor, SensorPlacement, Zone
from .services import (
    assign_sensor_location,
    save_sensor_location_configuration,
    sync_sensor_snapshot,
)


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

    def test_simple_configuration_creates_facility_zone_and_avoids_duplicate_history(self):
        placement, changed = save_sensor_location_configuration(
            sensor=self.sensor,
            facility_name="Finca La Esperanza",
            facility_type=Zone.ZoneType.FARM,
            zone_name="Sector Norte",
            city="Bogotá",
            department="Cundinamarca",
            latitude=Decimal("4.6872531"),
            longitude=Decimal("-74.0628734"),
            altitude_m=Decimal("2630.00"),
        )

        self.assertTrue(changed)
        self.assertEqual(placement.zone.parent.name, "Finca La Esperanza")
        self.assertEqual(placement.zone.name, "Sector Norte")
        self.assertEqual(self.sensor.placements.count(), 1)

        repeated, changed = save_sensor_location_configuration(
            sensor=self.sensor,
            facility_name="Finca La Esperanza",
            facility_type=Zone.ZoneType.FARM,
            zone_name="Sector Norte",
            city="Bogotá",
            department="Cundinamarca",
            latitude=Decimal("4.6872531"),
            longitude=Decimal("-74.0628734"),
            altitude_m=Decimal("2630.00"),
        )

        self.assertFalse(changed)
        self.assertEqual(repeated.pk, placement.pk)
        self.assertEqual(self.sensor.placements.count(), 1)

    def test_sync_sensor_snapshot_creates_updates_and_deactivates(self):
        obsolete = ClientSensor.objects.create(
            client=self.client,
            external_sensor_id="aranet-old",
            sensor_name="Sensor antiguo",
        )
        rows = [
            {
                "id": "aranet-001",
                "name": "Cuarto frío actualizado",
                "code": "A001",
                "type_name": "Aranet4",
                "is_active": True,
            },
            {
                "id": "aranet-002",
                "name": "Invernadero norte",
                "code": "A002",
                "type_name": "Aranet2",
                "is_active": True,
            },
        ]

        result = sync_sensor_snapshot(client=self.client, sensor_rows=rows)

        self.assertEqual(result.created, 1)
        self.assertEqual(result.updated, 1)
        self.assertEqual(result.deactivated, 1)
        self.assertEqual(result.unchanged, 0)
        self.sensor.refresh_from_db()
        obsolete.refresh_from_db()
        self.assertEqual(self.sensor.sensor_name, "Cuarto frío actualizado")
        self.assertEqual(self.sensor.sensor_detail, "Aranet4 · Código A001")
        self.assertFalse(obsolete.is_active)
        self.assertTrue(
            ClientSensor.objects.filter(
                client=self.client,
                external_sensor_id="aranet-002",
                sensor_detail="Aranet2 · Código A002",
            ).exists()
        )

        repeated = sync_sensor_snapshot(client=self.client, sensor_rows=rows)
        self.assertEqual(repeated.created, 0)
        self.assertEqual(repeated.updated, 0)
        self.assertEqual(repeated.unchanged, 2)
        self.assertEqual(repeated.deactivated, 0)

    def test_sync_does_not_override_local_dashboard_visibility(self):
        self.sensor.dashboard_enabled = False
        self.sensor.save(update_fields=("dashboard_enabled", "updated_at"))

        sync_sensor_snapshot(
            client=self.client,
            sensor_rows=[
                {
                    "id": "aranet-001",
                    "name": "Cuarto frío",
                    "type_name": "Aranet4",
                    "is_active": True,
                }
            ],
        )

        self.sensor.refresh_from_db()
        self.assertTrue(self.sensor.is_active)
        self.assertFalse(self.sensor.dashboard_enabled)
        self.assertFalse(self.sensor.is_dashboard_visible)

    def test_sync_sensor_snapshot_dry_run_does_not_write(self):
        result = sync_sensor_snapshot(
            client=self.client,
            sensor_rows=[
                {
                    "id": "aranet-002",
                    "name": "Sensor nuevo",
                    "type_name": "Aranet4",
                    "is_active": True,
                }
            ],
            dry_run=True,
        )

        self.assertEqual(result.created, 1)
        self.assertEqual(result.deactivated, 1)
        self.assertEqual(ClientSensor.objects.filter(client=self.client).count(), 1)
        self.sensor.refresh_from_db()
        self.assertTrue(self.sensor.is_active)


class SensorConfigurationViewTests(TestCase):
    def setUp(self):
        self.client_org = Client.objects.create(name="Vladimir Test", slug="vladimir-test")
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="config-admin",
            password="test-password-123",
        )
        ClientMembership.objects.create(
            user=self.user,
            client=self.client_org,
            access_level=AccessLevel.CLIENT_ADMIN,
        )
        module, _ = PlatformModule.objects.update_or_create(
            code="sensor_configuration",
            defaults={
                "name": "Configuración de sensores",
                "description": "Ubicación física de sensores",
                "route_name": "sensor_configuration",
                "category": "Configuración",
                "sort_order": 15,
                "is_active": True,
            },
        )
        ClientModule.objects.create(
            client=self.client_org,
            module=module,
            minimum_access_level=AccessLevel.CLIENT_ADMIN,
        )
        self.sensor = ClientSensor.objects.create(
            client=self.client_org,
            external_sensor_id="sensor-23",
            sensor_name="Aranet 23",
            sensor_detail="Aranet4 · Código A23",
        )
        self.client.login(username="config-admin", password="test-password-123")

    def test_sensor_list_shows_unconfigured_sensor(self):
        response = self.client.get(reverse("sensor_configuration"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "sensor-23")
        self.assertContains(response, "Sin ubicación")
        self.assertContains(response, "En dashboard")

    def test_toggle_hides_and_reenables_sensor_for_dashboard(self):
        toggle_url = reverse("sensor_configuration_toggle", args=(self.sensor.pk,))

        response = self.client.post(toggle_url, {"enabled": "0"})
        self.assertEqual(response.status_code, 302)
        self.sensor.refresh_from_db()
        self.assertFalse(self.sensor.dashboard_enabled)

        response = self.client.post(toggle_url, {"enabled": "1"})
        self.assertEqual(response.status_code, 302)
        self.sensor.refresh_from_db()
        self.assertTrue(self.sensor.dashboard_enabled)

    def test_inactive_source_sensor_cannot_be_enabled_for_dashboard(self):
        self.sensor.is_active = False
        self.sensor.dashboard_enabled = False
        self.sensor.save(update_fields=("is_active", "dashboard_enabled", "updated_at"))

        response = self.client.post(
            reverse("sensor_configuration_toggle", args=(self.sensor.pk,)),
            {"enabled": "1"},
        )

        self.assertEqual(response.status_code, 302)
        self.sensor.refresh_from_db()
        self.assertFalse(self.sensor.dashboard_enabled)

    def test_detail_post_creates_current_location(self):
        response = self.client.post(
            reverse("sensor_configuration_detail", args=(self.sensor.pk,)),
            {
                "facility_type": Zone.ZoneType.GREENHOUSE,
                "facility_name": "Invernadero Principal",
                "zone_name": "Sector A1",
                "city": "Bogotá",
                "department": "Cundinamarca",
                "latitude": "4.6872531",
                "longitude": "-74.0628734",
                "altitude_m": "2630",
                "notes": "Instalado sobre la línea central.",
            },
        )

        self.assertEqual(response.status_code, 302)
        placement = self.sensor.placements.get(valid_until__isnull=True)
        self.assertEqual(placement.zone.name, "Sector A1")
        self.assertEqual(placement.zone.parent.name, "Invernadero Principal")
        self.assertEqual(placement.city, "Bogotá")
        self.assertEqual(placement.latitude, Decimal("4.6872531"))
