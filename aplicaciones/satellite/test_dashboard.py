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
from aplicaciones.satellite.models import SatelliteField


class SatelliteDashboardTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.client_a = Client.objects.create(name="Cliente A", slug="cliente-a")
        self.client_b = Client.objects.create(name="Cliente B", slug="cliente-b")
        self.operator = user_model.objects.create_user("sat-operator", password="test-password-123")
        self.viewer = user_model.objects.create_user("sat-viewer", password="test-password-123")
        ClientMembership.objects.create(
            user=self.operator,
            client=self.client_a,
            access_level=AccessLevel.OPERATOR,
        )
        ClientMembership.objects.create(
            user=self.viewer,
            client=self.client_a,
            access_level=AccessLevel.VIEWER,
        )
        module = PlatformModule.objects.get(code="satellite")
        ClientModule.objects.create(
            client=self.client_a,
            module=module,
            is_enabled=True,
            minimum_access_level=AccessLevel.VIEWER,
        )

    def test_dashboard_lists_only_authenticated_client_fields(self):
        SatelliteField.objects.create(
            client=self.client_a,
            name="Lote A",
            geometry={
                "type": "Polygon",
                "coordinates": [[[-74.1, 4.6], [-74.09, 4.6], [-74.09, 4.59], [-74.1, 4.6]]],
            },
        )
        SatelliteField.objects.create(
            client=self.client_b,
            name="Lote B secreto",
            geometry={
                "type": "Polygon",
                "coordinates": [[[-73.1, 5.6], [-73.09, 5.6], [-73.09, 5.59], [-73.1, 5.6]]],
            },
        )
        self.client.force_login(self.operator)

        response = self.client.get(reverse("satellite:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lote A")
        self.assertNotContains(response, "Lote B secreto")

    @patch("aplicaciones.satellite.views.register_field_with_eosda")
    def test_operator_creates_field_for_membership_client(self, register_field):
        register_field.side_effect = lambda field: field
        self.client.force_login(self.operator)

        response = self.client.post(
            reverse("satellite:dashboard"),
            {
                "name": "Lote Nuevo",
                "crop_type": "Arándano",
                "sowing_date": "2026-08-20",
                "coordinates": "-74.1000,4.6000\n-74.0900,4.6000\n-74.0900,4.5900",
                "client": self.client_b.pk,
            },
        )

        self.assertRedirects(response, reverse("satellite:dashboard"))
        field = SatelliteField.objects.get(name="Lote Nuevo")
        self.assertEqual(field.client, self.client_a)
        self.assertEqual(field.geometry["coordinates"][0][0], [-74.1, 4.6])
        self.assertEqual(field.geometry["coordinates"][0][-1], [-74.1, 4.6])
        register_field.assert_called_once_with(field)

    def test_viewer_cannot_create_fields(self):
        self.client.force_login(self.viewer)

        response = self.client.post(
            reverse("satellite:dashboard"),
            {
                "name": "No permitido",
                "coordinates": "-74.1,4.6\n-74.09,4.6\n-74.09,4.59",
            },
        )

        self.assertEqual(response.status_code, 403)
        self.assertFalse(SatelliteField.objects.filter(name="No permitido").exists())
