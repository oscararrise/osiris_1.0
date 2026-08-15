from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from aplicaciones.core.models import (
    Client,
    ClientDataSource,
    ClientMembership,
    ClientModule,
    PlatformModule,
)

from .adapters.aranet import AranetAdapter, _rows
from .adapters.base import AdapterConfigurationError
from .adapters.registry import get_adapter
from .services import build_dashboard


class FakeAdapter:
    def __init__(self, sensor_id):
        self.sensor_id = sensor_id
        self.metric_sensor_calls = []

    def list_sensors(self):
        return [
            {
                "id": self.sensor_id,
                "name": f"Sensor {self.sensor_id}",
                "code": self.sensor_id,
                "type_name": "Test",
                "is_active": True,
                "last_seen_at": None,
                "rssi_dbm": None,
                "battery_value": None,
                "battery_unit": None,
            }
        ]

    def list_metrics(self, sensor_id):
        self.metric_sensor_calls.append(sensor_id)
        return [
            {
                "id": "temperature",
                "name": "Temperatura",
                "kind": "environmental",
                "probe_no": 0,
                "unit_id": "celsius",
                "unit": "°C",
                "precision_digits": 1,
            }
        ]

    def latest_values(self, sensor_id):
        return []

    def time_series(self, sensor_id, metric_id, probe_no, start, end, max_points):
        return [{"measured_at": end, "value": 21.5, "unit": "°C"}]

    def active_alarms(self, sensor_id=None):
        return []


class DashboardServiceTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client_a = Client.objects.create(name="A", slug="a")
        self.client_b = Client.objects.create(name="B", slug="b")
        ClientDataSource.objects.create(
            client=self.client_a, database_alias="client_a_db", adapter_key="aranet"
        )
        ClientDataSource.objects.create(
            client=self.client_b, database_alias="client_b_db", adapter_key="aranet"
        )

    def tearDown(self):
        cache.clear()

    @patch("aplicaciones.dashboard.services.get_adapter")
    def test_untrusted_sensor_parameter_cannot_switch_client_data(self, adapter_factory):
        adapter = FakeAdapter("sensor-a")
        adapter_factory.return_value = adapter
        context = build_dashboard(
            self.client_a,
            {"sensor": "sensor-from-another-client", "metric": "temperature"},
        )
        self.assertEqual(context["selected_sensor_id"], "sensor-a")
        self.assertEqual(adapter.metric_sensor_calls, ["sensor-a"])

    @patch("aplicaciones.dashboard.services.get_adapter")
    def test_cache_namespace_is_different_for_each_client(self, adapter_factory):
        adapter_a = FakeAdapter("sensor-a")
        adapter_b = FakeAdapter("sensor-b")
        adapter_factory.side_effect = [adapter_a, adapter_b]
        context_a = build_dashboard(self.client_a, {})
        context_b = build_dashboard(self.client_b, {})
        self.assertEqual(context_a["selected_sensor_id"], "sensor-a")
        self.assertEqual(context_b["selected_sensor_id"], "sensor-b")


class AdapterRegistryTests(TestCase):
    def test_missing_runtime_alias_is_reported_safely(self):
        client = Client.objects.create(name="No connection", slug="no-connection")
        source = ClientDataSource.objects.create(
            client=client, database_alias="not_configured", adapter_key="aranet"
        )
        with self.assertRaises(AdapterConfigurationError):
            get_adapter(source)


class AranetAdapterQueryTests(TestCase):
    def test_non_finite_database_values_are_safe_for_json(self):
        cursor = type("Cursor", (), {"description": [("value",)]})()
        self.assertEqual(
            _rows(cursor, [(float("nan"),), (float("inf"),), (12.5,)]),
            [{"value": None}, {"value": None}, {"value": 12.5}],
        )

    def test_time_series_uses_bound_parameters_for_sensor_and_metric(self):
        adapter = AranetAdapter("aranet_db")
        start = timezone.now() - timedelta(days=1)
        end = timezone.now()
        with patch.object(adapter, "_query", return_value=[]) as query:
            adapter.time_series(
                "sensor'; DROP TABLE aranet.sensor; --",
                "metric'; --",
                2,
                start,
                end,
                500,
            )
        sql, params = query.call_args.args
        self.assertNotIn("DROP TABLE", sql)
        self.assertEqual(params[1], "sensor'; DROP TABLE aranet.sensor; --")
        self.assertEqual(params[2], "metric'; --")
        self.assertEqual(params[3], 2)
        self.assertEqual(params[-1], 500)

    def test_list_metrics_is_scoped_by_sensor(self):
        adapter = AranetAdapter("aranet_db")
        with patch.object(adapter, "_query", return_value=[]) as query:
            adapter.list_metrics("sensor-123")
        self.assertEqual(query.call_args.args[1], ("sensor-123",))


class DashboardRenderingTests(TestCase):
    def test_complete_dynamic_dashboard_renders(self):
        client = Client.objects.create(name="Render client", slug="render-client")
        user = get_user_model().objects.create_user("render-user", password="test-password")
        ClientMembership.objects.create(user=user, client=client)
        ClientModule.objects.create(
            client=client, module=PlatformModule.objects.get(code="dashboard")
        )
        source = ClientDataSource.objects.create(
            client=client, database_alias="render_db", adapter_key="aranet"
        )
        now = timezone.now()
        sensor = {
            "id": "sensor-1",
            "name": "Invernadero norte",
            "code": "A-100",
            "type_name": "Aranet4",
            "is_active": True,
            "last_seen_at": now,
            "battery_value": 92,
            "battery_unit": "%",
            "rssi_dbm": -65,
        }
        metric = {
            "id": "temperature",
            "name": "Temperatura",
            "probe_no": 0,
            "unit": "°C",
        }
        context = {
            "source": source,
            "sensors": [sensor],
            "selected_sensor": sensor,
            "selected_sensor_id": "sensor-1",
            "metrics": [metric],
            "selected_metric": metric,
            "selected_metric_id": "temperature",
            "selected_probe_no": 0,
            "latest_values": [
                {
                    **metric,
                    "value": 22.4,
                    "precision_digits": 1,
                    "measured_at": now,
                }
            ],
            "alarms": [],
            "series": [{"measured_at": now, "value": 22.4, "unit": "°C"}],
            "statistics": {
                "average": 22.4,
                "minimum": 22.4,
                "maximum": 22.4,
                "points": 1,
                "samples": 1,
            },
            "ranges": {"24h": ("Últimas 24 horas", timedelta(hours=24))},
            "selected_range": "24h",
        }
        self.client.force_login(user)
        with patch("aplicaciones.dashboard.views.build_dashboard", return_value=context):
            response = self.client.get(reverse("s2"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Invernadero norte")
        self.assertContains(response, "trend-chart")
        self.assertContains(response, "Todo en orden")
