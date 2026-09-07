from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import RequestFactory, TestCase
from django.urls import reverse
from django.utils import timezone

from aplicaciones.core.models import (
    AccessLevel,
    Client,
    ClientDataSource,
    ClientMembership,
    ClientModule,
    PlatformModule,
)
from aplicaciones.sensor_config.models import ClientSensor, SensorPlacement, Zone

from .agronomy_api import _sensor_catalog
from .models import AgronomicVariableRelationship


class AgronomyRelationshipApiTests(TestCase):
    def setUp(self):
        self.client_org = Client.objects.create(name="Vladimir", slug="vladimir")
        self.other_client = Client.objects.create(name="Other", slug="other")
        ClientDataSource.objects.create(
            client=self.client_org,
            database_alias="aranet_db",
            adapter_key=ClientDataSource.Adapter.ARANET,
            is_active=True,
        )
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            username="agronomy-admin",
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
                "route_name": "s2",
                "category": "Monitoreo",
                "sort_order": 1,
                "is_active": True,
            },
        )
        config_module, _ = PlatformModule.objects.update_or_create(
            code="sensor_configuration",
            defaults={
                "name": "Configuración de sensores",
                "route_name": "sensor_configuration",
                "category": "Configuración",
                "sort_order": 15,
                "is_active": True,
            },
        )
        ClientModule.objects.create(
            client=self.client_org,
            module=dashboard_module,
            minimum_access_level=AccessLevel.VIEWER,
        )
        ClientModule.objects.create(
            client=self.client_org,
            module=config_module,
            minimum_access_level=AccessLevel.CLIENT_ADMIN,
        )
        self.sensor = ClientSensor.objects.create(
            client=self.client_org,
            external_sensor_id="sensor-1",
            sensor_name="Alstroemeria Norte",
            activity_type=ClientSensor.ActivityType.CROP,
            product_name="Astromelia",
        )
        self.soil_sensor = ClientSensor.objects.create(
            client=self.client_org,
            external_sensor_id="sensor-2",
            sensor_name="Suelo Sur",
            activity_type=ClientSensor.ActivityType.CROP,
            product_name="Astromelia",
            dashboard_enabled=False,
        )
        self.foreign_sensor = ClientSensor.objects.create(
            client=self.other_client,
            external_sensor_id="foreign-sensor",
            sensor_name="Foreign",
        )
        zone = Zone.objects.create(
            client=self.client_org,
            name="Invernadero 1",
            code="invernadero-1",
            zone_type=Zone.ZoneType.GREENHOUSE,
        )
        SensorPlacement.objects.create(
            sensor=self.soil_sensor,
            zone=zone,
            city="Bogotá",
            department="Cundinamarca",
            latitude="4.7110000",
            longitude="-74.0721000",
            altitude_m="2600.00",
            valid_from=timezone.now(),
        )
        self.catalog = [
            {
                "sensor_id": "sensor-1",
                "sensor_name": "Alstroemeria Norte",
                "sensor_detail": "Ambiente",
                "activity_label": "Cultivo",
                "product_name": "Astromelia",
                "productive_context": "Cultivo · Astromelia",
                "dashboard_enabled": True,
                "dashboard_label": "Visible en dashboard",
                "facility_name": "Invernadero 1",
                "zone_name": "Norte",
                "zone_path": "Invernadero 1 / Norte",
                "city": "Bogotá",
                "department": "Cundinamarca",
                "latitude": 4.71,
                "longitude": -74.07,
                "altitude_m": 2600,
                "metric_count": 2,
                "metrics_error": "",
                "metrics": [
                    {
                        "key": "sensor-1::temperature:0",
                        "local_key": "temperature:0",
                        "id": "temperature",
                        "name": "Temperatura",
                        "probe_no": 0,
                        "unit": "°C",
                        "sensor_id": "sensor-1",
                        "sensor_name": "Alstroemeria Norte",
                    },
                    {
                        "key": "sensor-1::co2:0",
                        "local_key": "co2:0",
                        "id": "co2",
                        "name": "CO2",
                        "probe_no": 0,
                        "unit": "ppm",
                        "sensor_id": "sensor-1",
                        "sensor_name": "Alstroemeria Norte",
                    },
                ],
            },
            {
                "sensor_id": "sensor-2",
                "sensor_name": "Suelo Sur",
                "sensor_detail": "Sonda radicular",
                "activity_label": "Cultivo",
                "product_name": "Astromelia",
                "productive_context": "Cultivo · Astromelia",
                "dashboard_enabled": False,
                "dashboard_label": "Oculto en dashboard",
                "facility_name": "Invernadero 1",
                "zone_name": "Sur",
                "zone_path": "Invernadero 1 / Sur",
                "city": "Bogotá",
                "department": "Cundinamarca",
                "latitude": 4.711,
                "longitude": -74.0721,
                "altitude_m": 2600,
                "metric_count": 2,
                "metrics_error": "",
                "metrics": [
                    {
                        "key": "sensor-2::humidity:0",
                        "local_key": "humidity:0",
                        "id": "humidity",
                        "name": "Humedad relativa",
                        "probe_no": 0,
                        "unit": "%",
                        "sensor_id": "sensor-2",
                        "sensor_name": "Suelo Sur",
                    },
                    {
                        "key": "sensor-2::soil_moisture:1",
                        "local_key": "soil_moisture:1",
                        "id": "soil_moisture",
                        "name": "Humedad de suelo",
                        "probe_no": 1,
                        "unit": "%",
                        "sensor_id": "sensor-2",
                        "sensor_name": "Suelo Sur",
                    },
                ],
            },
        ]
        self.client.login(username="agronomy-admin", password="test-password-123")

    @patch("aplicaciones.dashboard.agronomy_api._sensor_catalog")
    def test_get_returns_catalog_and_cross_sensor_suggestions(self, sensor_catalog):
        sensor_catalog.return_value = self.catalog

        response = self.client.get(
            reverse("agronomy_relationships"),
            {"sensor": self.sensor.external_sensor_id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["crop_name"], "Astromelia")
        self.assertEqual(len(payload["sensor_catalog"]), 2)
        self.assertEqual(len(payload["metrics"]), 4)
        self.assertFalse(payload["sensor_catalog"][1]["dashboard_enabled"])
        climate = next(
            item
            for item in payload["suggestions"]
            if item["name"] == "Balance climático y transpiración"
        )
        self.assertIn("sensor-1::temperature:0", climate["variable_keys"])
        self.assertIn("sensor-2::humidity:0", climate["variable_keys"])

    @patch("aplicaciones.dashboard.agronomy_api._sensor_catalog")
    def test_post_saves_variables_from_multiple_sensors(self, sensor_catalog):
        sensor_catalog.return_value = self.catalog

        response = self.client.post(
            reverse("agronomy_relationships"),
            {
                "sensor": self.sensor.external_sensor_id,
                "crop_name": "Astromelia",
                "name": "Clima y raíz cruzados",
                "relationship_type": "custom",
                "variable_ids": (
                    '["sensor-1::temperature:0", '
                    '"sensor-2::humidity:0", '
                    '"sensor-2::soil_moisture:1"]'
                ),
                "agronomic_goal": "Relacionar ambiente y zona radicular.",
                "expert_guidance": "Interpretar las tres señales en conjunto.",
                "is_enabled": "1",
            },
        )

        self.assertEqual(response.status_code, 200)
        relationship = AgronomicVariableRelationship.objects.get(
            client=self.client_org,
            sensor_id=self.sensor.external_sensor_id,
        )
        self.assertEqual(len(relationship.variable_ids), 3)
        self.assertEqual(
            relationship.variable_names,
            [
                "Alstroemeria Norte · Temperatura",
                "Suelo Sur · Humedad relativa",
                "Suelo Sur · Humedad de suelo",
            ],
        )
        details = response.json()["relationship"]["variable_details"]
        self.assertEqual({item["sensor_id"] for item in details}, {"sensor-1", "sensor-2"})

    @patch("aplicaciones.dashboard.agronomy_api._sensor_catalog")
    def test_post_rejects_unknown_cross_sensor_variable(self, sensor_catalog):
        sensor_catalog.return_value = self.catalog

        response = self.client.post(
            reverse("agronomy_relationships"),
            {
                "sensor": self.sensor.external_sensor_id,
                "crop_name": "Astromelia",
                "name": "Invalid",
                "variable_ids": (
                    '["sensor-1::temperature:0", "foreign-sensor::invented:0"]'
                ),
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AgronomicVariableRelationship.objects.count(), 0)

    @patch("aplicaciones.dashboard.agronomy_api._sensor_catalog")
    def test_existing_single_sensor_keys_remain_readable(self, sensor_catalog):
        sensor_catalog.return_value = self.catalog
        AgronomicVariableRelationship.objects.create(
            client=self.client_org,
            sensor_id="sensor-1",
            sensor_name="Alstroemeria Norte",
            crop_name="Astromelia",
            name="Relación histórica",
            variable_ids=["temperature:0", "co2:0"],
            variable_names=["Temperatura", "CO2"],
        )

        response = self.client.get(
            reverse("agronomy_relationships"),
            {"sensor": "sensor-1"},
        )

        self.assertEqual(response.status_code, 200)
        details = response.json()["relationships"][0]["variable_details"]
        self.assertTrue(all(item["available"] for item in details))
        self.assertEqual({item["sensor_id"] for item in details}, {"sensor-1"})

    @patch("aplicaciones.dashboard.agronomy_api._sensor_catalog")
    def test_foreign_client_sensor_is_not_available(self, sensor_catalog):
        sensor_catalog.return_value = self.catalog

        response = self.client.get(
            reverse("agronomy_relationships"),
            {"sensor": self.foreign_sensor.external_sensor_id},
        )

        self.assertEqual(response.status_code, 404)

    @patch("aplicaciones.dashboard.agronomy_api.get_adapter")
    def test_catalog_includes_hidden_sensor_context_but_excludes_foreign_client(
        self,
        get_adapter,
    ):
        adapter = get_adapter.return_value
        adapter.list_metrics.return_value = [
            {
                "id": "temperature",
                "name": "Temperatura",
                "probe_no": 0,
                "unit": "°C",
            }
        ]
        request = RequestFactory().get("/s2/agronomy")
        request.client = self.client_org

        catalog = _sensor_catalog(request)

        ids = {item["sensor_id"] for item in catalog}
        self.assertEqual(ids, {"sensor-1", "sensor-2"})
        hidden = next(item for item in catalog if item["sensor_id"] == "sensor-2")
        self.assertFalse(hidden["dashboard_enabled"])
        self.assertEqual(hidden["facility_name"], "Invernadero 1")
        self.assertEqual(hidden["city"], "Bogotá")
        self.assertEqual(hidden["metrics"][0]["key"], "sensor-2::temperature:0")
