from types import SimpleNamespace

from django.contrib.auth import get_user_model
from django.test import TestCase

from aplicaciones.core.models import Client

from .models import SensorAutomationPolicy
from .views import _save_automation_policy


class SensorAutomationPolicyTests(TestCase):
    def setUp(self):
        self.client_a = Client.objects.create(name="Automation A", slug="automation-a")
        self.client_b = Client.objects.create(name="Automation B", slug="automation-b")
        self.user = get_user_model().objects.create_user(
            username="automation-user",
            password="test-password",
        )
        self.context = {
            "selected_sensor_id": "sensor-123",
            "selected_sensor": {"id": "sensor-123", "name": "Invernadero norte"},
            "metrics": [
                {"id": "temperature", "name": "Temperatura", "probe_no": 0},
                {"id": "humidity", "name": "Humedad", "probe_no": 0},
            ],
        }

    def _request(self, client, **overrides):
        payload = {
            "automation_metric": "temperature",
            "operator": "gt",
            "threshold_value": "30.5",
            "cooldown_minutes": "45",
            "is_enabled": "on",
            "email_enabled": "on",
            "email_recipients": "ops@example.com",
            "whatsapp_enabled": "on",
            "whatsapp_recipients": "+573000000000",
            "automation_level": "supervised",
            "requires_confirmation": "on",
            "ai_instruction": "Revisar humedad antes de proponer una acción.",
        }
        payload.update(overrides)
        return SimpleNamespace(POST=payload, client=client, user=self.user)

    def test_policy_is_saved_for_selected_client_and_sensor(self):
        policy = _save_automation_policy(
            self._request(self.client_a),
            self.context,
        )

        self.assertEqual(policy.client, self.client_a)
        self.assertEqual(policy.sensor_id, "sensor-123")
        self.assertEqual(policy.metric_id, "temperature")
        self.assertEqual(policy.metric_name, "Temperatura")
        self.assertEqual(policy.threshold_value, 30.5)
        self.assertEqual(policy.automation_level, "supervised")
        self.assertTrue(policy.requires_confirmation)
        self.assertTrue(policy.email_enabled)
        self.assertTrue(policy.whatsapp_enabled)

    def test_same_external_sensor_can_have_policy_for_another_client(self):
        _save_automation_policy(self._request(self.client_a), self.context)
        _save_automation_policy(self._request(self.client_b), self.context)

        self.assertEqual(
            SensorAutomationPolicy.objects.filter(sensor_id="sensor-123").count(),
            2,
        )

    def test_invalid_values_are_normalised(self):
        policy = _save_automation_policy(
            self._request(
                self.client_a,
                automation_metric="not-a-real-metric",
                automation_level="invalid",
                operator="invalid",
                threshold_value="not-a-number",
                cooldown_minutes="999999",
            ),
            self.context,
        )

        self.assertEqual(policy.metric_id, "")
        self.assertEqual(
            policy.automation_level,
            SensorAutomationPolicy.AutomationLevel.RECOMMEND,
        )
        self.assertEqual(policy.operator, SensorAutomationPolicy.Operator.GREATER_THAN)
        self.assertIsNone(policy.threshold_value)
        self.assertEqual(policy.cooldown_minutes, 10080)
