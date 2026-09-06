from datetime import UTC, datetime

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
from aplicaciones.satellite.models import SatelliteField, SatelliteScene

POLYGON = {
    "type": "Polygon",
    "coordinates": [
        [
            [-72.992797, 5.775136],
            [-72.992397, 5.775136],
            [-72.992397, 5.774736],
            [-72.992797, 5.774736],
            [-72.992797, 5.775136],
        ]
    ],
}


class SceneDetailViewTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.client_a = Client.objects.create(name="Cliente A", slug="cliente-a")
        self.client_b = Client.objects.create(name="Cliente B", slug="cliente-b")
        self.viewer = user_model.objects.create_user(
            "scene-detail-viewer",
            password="test-password-123",
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
        self.field_a = SatelliteField.objects.create(
            client=self.client_a,
            name="Lote A",
            geometry=POLYGON,
            eosda_field_id=1001,
        )
        self.field_b = SatelliteField.objects.create(
            client=self.client_b,
            name="Lote B secreto",
            geometry=POLYGON,
            eosda_field_id=2001,
        )
        self.scene_a = SatelliteScene.objects.create(
            field=self.field_a,
            dataset="sentinel2",
            view_id="S2/18/N/XM/2026/6/23/0",
            captured_at=datetime(2026, 6, 23, 12, tzinfo=UTC),
            cloud_cover=8.3,
            metadata={
                "sceneID": "S2A_scene_cliente_a",
                "dataCoveragePercentage": 100.0,
            },
        )
        SatelliteScene.objects.create(
            field=self.field_b,
            dataset="sentinel2",
            view_id="S2/18/N/XM/2026/6/20/0",
            captured_at=datetime(2026, 6, 20, 12, tzinfo=UTC),
            cloud_cover=5.0,
            metadata={"sceneID": "S2B_scene_secreta"},
        )
        self.client.force_login(self.viewer)

    def test_viewer_can_open_own_field_scene_history(self):
        response = self.client.get(
            reverse("satellite:field_scenes", args=[self.field_a.pk])
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Lote A")
        self.assertContains(response, "23/06/2026")
        self.assertContains(response, "8,3% nubes")
        self.assertContains(response, "S2A_scene_cliente_a")
        self.assertContains(response, self.scene_a.view_id)
        self.assertContains(response, "Imagen satelital")
        self.assertNotContains(response, "S2B_scene_secreta")

    def test_viewer_cannot_open_another_client_field_scene_history(self):
        response = self.client.get(
            reverse("satellite:field_scenes", args=[self.field_b.pk])
        )

        self.assertEqual(response.status_code, 404)

    def test_dashboard_links_to_existing_scene_history(self):
        response = self.client.get(reverse("satellite:dashboard"))

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Ver escenas (1)")
        self.assertContains(
            response,
            reverse("satellite:field_scenes", args=[self.field_a.pk]),
        )
