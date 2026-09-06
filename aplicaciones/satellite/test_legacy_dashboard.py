from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from aplicaciones.core.models import (
    AccessLevel,
    Client,
    ClientDataSource,
    ClientMembership,
    ClientModule,
    PlatformModule,
)


class LegacySatelliteModuleVisibilityTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.client_model = Client.objects.create(name="Telemetry Client", slug="telemetry-client")
        ClientDataSource.objects.create(
            client=self.client_model,
            database_alias="telemetry_test_db",
            adapter_key=ClientDataSource.Adapter.TELEMETRY,
            is_active=True,
        )
        self.user = user_model.objects.create_user(
            username="telemetry-user",
            password="test-password-123",
        )
        ClientMembership.objects.create(
            user=self.user,
            client=self.client_model,
            access_level=AccessLevel.CLIENT_ADMIN,
        )
        self.satellite_module = PlatformModule.objects.get(code="satellite")
        self.client.force_login(self.user)

    def test_legacy_dashboard_shows_satellite_when_enabled(self):
        ClientModule.objects.create(
            client=self.client_model,
            module=self.satellite_module,
            is_enabled=True,
            minimum_access_level=AccessLevel.VIEWER,
        )

        response = self.client.get(reverse("inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Monitoreo Satelital")
        self.assertContains(response, reverse("satellite:dashboard"))

    def test_legacy_dashboard_hides_satellite_when_disabled(self):
        ClientModule.objects.create(
            client=self.client_model,
            module=self.satellite_module,
            is_enabled=False,
            minimum_access_level=AccessLevel.VIEWER,
        )

        response = self.client.get(reverse("inicio"))

        self.assertEqual(response.status_code, 200)
        self.assertNotContains(response, "Monitoreo Satelital")
