from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from aplicaciones.core.models import (
    AccessLevel,
    Client,
    ClientMembership,
    ClientModule,
    PlatformModule,
)
from aplicaciones.sensor_config.models import ClientSensor

from .models import AgronomicVariableRelationship


class AgronomyRelationshipApiTests(TestCase):
    def setUp(self):
        self.client_org = Client.objects.create(name="Vladimir", slug="vladimir")
        self.other_client = Client.objects.create(name="Other", slug="other")
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
        self.foreign_sensor = ClientSensor.objects.create(
            client=self.other_client,
            external_sensor_id="foreign-sensor",
            sensor_name="Foreign",
        )
        self.metrics = [
            {
                "key": "temperature:0",
                "id": "temperature",
                "name": "Temperatura",
                "probe_no": 0,
                "unit": "°C",
            },
            {
                "key": "humidity:0",
                "id": "humidity",
                "name": "Humedad relativa",
                "probe_no": 0,
                "unit": "%",
            },
            {
                "key": "co2:0",
                "id": "co2",
                "name": "CO2",
                "probe_no": 0,
                "unit": "ppm",
            },
        ]
        self.client.login(username="agronomy-admin", password="test-password-123")

    @patch("aplicaciones.dashboard.agronomy_api._available_metrics")
    def test_get_returns_multivariable_suggestions(self, available_metrics):
        available_metrics.return_value = self.metrics

        response = self.client.get(
            reverse("agronomy_relationships"),
            {"sensor": self.sensor.external_sensor_id},
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["crop_name"], "Astromelia")
        self.assertEqual(len(payload["metrics"]), 3)
        self.assertTrue(
            any(
                item["name"] == "Balance climático y transpiración"
                for item in payload["suggestions"]
            )
        )
        self.assertTrue(
            all(len(item["variable_keys"]) >= 2 for item in payload["suggestions"])
        )

    @patch("aplicaciones.dashboard.agronomy_api._available_metrics")
    def test_post_saves_three_variable_relationship(self, available_metrics):
        available_metrics.return_value = self.metrics

        response = self.client.post(
            reverse("agronomy_relationships"),
            {
                "sensor": self.sensor.external_sensor_id,
                "crop_name": "Astromelia",
                "name": "Ambiente fotosintético",
                "relationship_type": "photosynthesis",
                "variable_ids": '["temperature:0", "humidity:0", "co2:0"]',
                "agronomic_goal": "Relacionar clima y disponibilidad de CO2.",
                "expert_guidance": "Interpretar las variables en conjunto.",
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
            ["Temperatura", "Humedad relativa", "CO2"],
        )
        self.assertTrue(relationship.is_enabled)

    @patch("aplicaciones.dashboard.agronomy_api._available_metrics")
    def test_post_rejects_single_or_unknown_variable(self, available_metrics):
        available_metrics.return_value = self.metrics

        response = self.client.post(
            reverse("agronomy_relationships"),
            {
                "sensor": self.sensor.external_sensor_id,
                "crop_name": "Astromelia",
                "name": "Invalid",
                "variable_ids": '["temperature:0", "invented:0"]',
            },
        )

        self.assertEqual(response.status_code, 400)
        self.assertEqual(AgronomicVariableRelationship.objects.count(), 0)

    @patch("aplicaciones.dashboard.agronomy_api._available_metrics")
    def test_foreign_client_sensor_is_not_available(self, available_metrics):
        available_metrics.return_value = self.metrics

        response = self.client.get(
            reverse("agronomy_relationships"),
            {"sensor": self.foreign_sensor.external_sensor_id},
        )

        self.assertEqual(response.status_code, 404)
