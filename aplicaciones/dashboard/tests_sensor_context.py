from __future__ import annotations

from decimal import Decimal

from django.contrib.auth import get_user_model
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
from aplicaciones.sensor_config.models import ClientSensor, SensorPlacement, Zone

from .osiris_sensor_context import build_osiris_sensor_context


class OsirisSensorContextTests(TestCase):
    def setUp(self):
        self.client_org = Client.objects.create(name="Vladimir", slug="vladimir")
        self.other_client = Client.objects.create(name="Other", slug="other")
        self.zone = Zone.objects.create(
            client=self.client_org,
            name="Sector A1",
            code="sector-a1-map",
            zone_type=Zone.ZoneType.SECTOR,
        )
        self.sensor = ClientSensor.objects.create(
            client=self.client_org,
            external_sensor_id="sensor-map-1",
            sensor_name="Aranet cultivo",
            activity_type=ClientSensor.ActivityType.CROP,
            product_name="Arándano",
        )
        SensorPlacement.objects.create(
            sensor=self.sensor,
            zone=self.zone,
            city="Bogotá",
            department="Cundinamarca",
            latitude=Decimal("4.6872531"),
            longitude=Decimal("-74.0628734"),
            altitude_m=Decimal("2630"),
            valid_from=timezone.now(),
        )
        ClientSensor.objects.create(
            client=self.client_org,
            external_sensor_id="hidden-map-2",
            sensor_name="Oculto",
            dashboard_enabled=False,
        )
        ClientSensor.objects.create(
            client=self.other_client,
            external_sensor_id="foreign-map-3",
            sensor_name="Foreign",
        )

    def test_context_contains_selected_productive_and_map_metadata(self):
        payload = build_osiris_sensor_context(self.client_org, "sensor-map-1")

        self.assertEqual(payload["visible_count"], 1)
        self.assertEqual(payload["mapped_count"], 1)
        self.assertEqual(payload["selected"]["activity_label"], "Cultivo")
        self.assertEqual(payload["selected"]["product_name"], "Arándano")
        self.assertEqual(payload["selected"]["city"], "Bogotá")
        self.assertEqual(payload["map_points"][0]["sensor_id"], "sensor-map-1")
        self.assertNotIn(
            "hidden-map-2",
            {point["sensor_id"] for point in payload["map_points"]},
        )
        self.assertNotIn(
            "foreign-map-3",
            {point["sensor_id"] for point in payload["map_points"]},
        )


class SensorContextApiTests(TestCase):
    def setUp(self):
        self.client_org = Client.objects.create(name="Vladimir API", slug="vladimir-api")
        self.user = get_user_model().objects.create_user(
            username="map-admin",
            password="test-password-123",
        )
        ClientMembership.objects.create(
            user=self.user,
            client=self.client_org,
            access_level=AccessLevel.CLIENT_ADMIN,
        )
        dashboard_module, _ = PlatformModule.objects.update_or_create(
            code="dashboard",
            defaults={
                "name": "Dashboard",
                "description": "Dashboard",
                "route_name": "s2",
                "category": "Monitoreo",
                "sort_order": 10,
                "is_active": True,
            },
        )
        ClientModule.objects.create(client=self.client_org, module=dashboard_module)
        config_module, _ = PlatformModule.objects.update_or_create(
            code="sensor_configuration",
            defaults={
                "name": "Configuración de sensores",
                "description": "Configuración",
                "route_name": "sensor_configuration",
                "category": "Configuración",
                "sort_order": 15,
                "is_active": True,
            },
        )
        ClientModule.objects.create(
            client=self.client_org,
            module=config_module,
            minimum_access_level=AccessLevel.CLIENT_ADMIN,
        )
        self.sensor = ClientSensor.objects.create(
            client=self.client_org,
            external_sensor_id="api-map-1",
            sensor_name="Aranet fresa",
            activity_type=ClientSensor.ActivityType.CROP,
            product_name="Fresa",
        )
        self.client.login(username="map-admin", password="test-password-123")

    def test_endpoint_returns_only_current_clients_local_context(self):
        response = self.client.get(
            reverse("sensor_context"),
            {"sensor": self.sensor.external_sensor_id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["selected"]["sensor_id"], "api-map-1")
        self.assertEqual(payload["selected"]["product_name"], "Fresa")
        self.assertIn(
            f"/sensor-config/{self.sensor.pk}/",
            payload["selected"]["configure_url"],
        )
